package main

import (
	"crypto/hmac"
	"crypto/sha256"
	"encoding/base64"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"io/fs"
	"log"
	"net"
	"net/http"
	"net/url"
	"os"
	"path"
	"path/filepath"
	"strconv"
	"strings"
	"sync"
	"time"
)

type Claims struct {
	ClientID            any    `json:"client_id"`
	VideoID             any    `json:"video_id"`
	ServerID            any    `json:"server_id"`
	StoragePath         string `json:"storage_path"`
	Provider            string `json:"provider"`
	JellyfinServerID    any    `json:"jellyfin_server_id"`
	JellyfinItemID      string `json:"jellyfin_item_id"`
	JellyfinInternalURL string `json:"jellyfin_internal_url"`
	Exp                 int64  `json:"exp"`
}

type Engine struct {
	mediaRoot        string
	jwtSecret        []byte
	apiKey           string
	panelInternalURL string
	allowedJellyfin map[string]struct{}
	jellyfinAPIKeys map[string]string
	httpClient       *http.Client
	rateLimit        *RateLimiter
	metrics          *ConnectionMetrics
}

type ConnectionMetrics struct {
	mu               sync.RWMutex
	activeConns      int64
	totalConns       int64
	bytesTransferred int64
	startTime        time.Time
}

type RateLimiter struct {
	mu       sync.Mutex
	window   time.Duration
	limit    int
	requests map[string][]time.Time
}

func main() {
	engine := Engine{
		mediaRoot:       getenv("MEDIA_ROOT", "/media"),
		jwtSecret:       []byte(getenv("JWT_SECRET", "dev-jwt-secret")),
		apiKey:          getenv("ENGINE_API_KEY", "dev-engine-key"),
		panelInternalURL: strings.TrimRight(getenv("PANEL_INTERNAL_URL", ""), "/"),
		allowedJellyfin: parseAllowedURLs(getenv("JELLYFIN_ALLOWED_INTERNAL_URLS", "")),
		jellyfinAPIKeys: parseKeyMap(getenv("JELLYFIN_API_KEYS", "")),
		httpClient: &http.Client{
			Timeout: 30 * time.Second,
		},
		rateLimit: NewRateLimiter(envInt("RATE_LIMIT_REQUESTS", 240), time.Minute),
		metrics: &ConnectionMetrics{
			startTime: time.Now(),
		},
	}

	mux := http.NewServeMux()
	mux.HandleFunc("/", engine.root)
	mux.HandleFunc("/health", engine.health)
	mux.HandleFunc("/player_api.php", engine.panelProxy)
	mux.HandleFunc("/panel_api.php", engine.panelProxy)
	mux.HandleFunc("/get.php", engine.panelProxy)
	mux.HandleFunc("/movie/", engine.panelProxy)
	mux.HandleFunc("/live/", engine.panelProxy)
	mux.HandleFunc("/hls/", engine.hls)
	mux.HandleFunc("/jellyfin/", engine.jellyfin)

	handler := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("ngrok-skip-browser-warning", "true")
		w.Header().Set("Access-Control-Allow-Origin", "*")
		mux.ServeHTTP(w, r)
	})

	addr := getenv("ENGINE_ADDR", ":8080")
	log.Printf("go-engine listening on %s", addr)
	log.Fatal(http.ListenAndServe(addr, handler))
}

func getenv(key, fallback string) string {
	if value := os.Getenv(key); value != "" {
		return value
	}
	return fallback
}

func envInt(key string, fallback int) int {
	value, err := strconv.Atoi(getenv(key, ""))
	if err != nil || value <= 0 {
		return fallback
	}
	return value
}

func NewRateLimiter(limit int, window time.Duration) *RateLimiter {
	return &RateLimiter{limit: limit, window: window, requests: map[string][]time.Time{}}
}

func (r *RateLimiter) Allow(key string) bool {
	r.mu.Lock()
	defer r.mu.Unlock()
	now := time.Now()
	cutoff := now.Add(-r.window)
	items := r.requests[key]
	kept := items[:0]
	for _, ts := range items {
		if ts.After(cutoff) {
			kept = append(kept, ts)
		}
	}
	if len(kept) >= r.limit {
		r.requests[key] = kept
		return false
	}
	r.requests[key] = append(kept, now)
	return true
}

func parseAllowedURLs(raw string) map[string]struct{} {
	allowed := map[string]struct{}{}
	for _, part := range strings.Split(raw, ",") {
		normalized, err := normalizeBaseURL(part)
		if err == nil && normalized != "" {
			allowed[normalized] = struct{}{}
		}
	}
	return allowed
}

func parseKeyMap(raw string) map[string]string {
	keys := map[string]string{}
	for _, part := range strings.Split(raw, ",") {
		left, right, ok := strings.Cut(strings.TrimSpace(part), "=")
		if ok && strings.TrimSpace(left) != "" {
			keys[strings.TrimSpace(left)] = strings.TrimSpace(right)
		}
	}
	return keys
}

func normalizeBaseURL(raw string) (string, error) {
	raw = strings.TrimRight(strings.TrimSpace(raw), "/")
	if raw == "" {
		return "", errors.New("empty URL")
	}
	u, err := url.Parse(raw)
	if err != nil {
		return "", err
	}
	if err := validateJellyfinBaseURL(u); err != nil {
		return "", err
	}
	u.Path = strings.TrimRight(u.EscapedPath(), "/")
	u.RawQuery = ""
	u.Fragment = ""
	return u.String(), nil
}

func (e Engine) root(w http.ResponseWriter, r *http.Request) {
	if r.URL.Path != "/" {
		http.NotFound(w, r)
		return
	}
	w.Header().Set("Content-Type", "application/json")
	_, _ = w.Write([]byte(`{"status":"ok","service":"go-engine"}`))
}

func (e Engine) health(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "application/json")
	
	// Métricas básicas sempre disponíveis
	status := "healthy"
	
	// Se API key fornecida, retorna métricas detalhadas
	if r.Header.Get("X-API-Key") == e.apiKey {
		e.metrics.mu.RLock()
		response := map[string]interface{}{
			"status":              status,
			"timestamp":           time.Now().Unix(),
			"uptime_seconds":      int(time.Since(e.metrics.startTime).Seconds()),
			"active_connections":  e.metrics.activeConns,
			"total_connections":   e.metrics.totalConns,
			"bytes_transferred":   e.metrics.bytesTransferred,
			"rate_limit_window":   e.rateLimit.window.Seconds(),
			"rate_limit_requests": e.rateLimit.limit,
		}
		e.metrics.mu.RUnlock()
		
		data, _ := json.Marshal(response)
		_, _ = w.Write(data)
		return
	}
	
	// Resposta pública (sem métricas sensíveis)
	_, _ = w.Write([]byte(`{"status":"healthy"}`))
}

// trackConnection inicia tracking de uma conexão
func (e Engine) panelProxy(w http.ResponseWriter, r *http.Request) {
	if e.panelInternalURL == "" {
		http.Error(w, "panel proxy not configured", http.StatusBadGateway)
		return
	}
	target, err := url.Parse(e.panelInternalURL)
	if err != nil || target.Scheme == "" || target.Host == "" {
		http.Error(w, "invalid panel proxy target", http.StatusBadGateway)
		return
	}
	target.Path = r.URL.Path
	target.RawQuery = r.URL.RawQuery

	req, err := http.NewRequestWithContext(r.Context(), r.Method, target.String(), r.Body)
	if err != nil {
		http.Error(w, "proxy request failed", http.StatusBadGateway)
		return
	}
	copyProxyHeaders(req.Header, r.Header)
	req.Header.Set("X-Forwarded-Host", r.Host)
	req.Header.Set("X-Forwarded-Proto", forwardedProto(r))
	req.Header.Set("X-Forwarded-For", clientIP(r))

	resp, err := e.httpClient.Do(req)
	if err != nil {
		http.Error(w, "panel proxy failed", http.StatusBadGateway)
		return
	}
	defer resp.Body.Close()

	copySafeHeaders(w.Header(), resp.Header)
	w.WriteHeader(resp.StatusCode)
	_, _ = io.Copy(w, resp.Body)
}

func copyProxyHeaders(dst, src http.Header) {
	for key, values := range src {
		lower := strings.ToLower(key)
		if lower == "host" || strings.HasPrefix(lower, "x-forwarded-") {
			continue
		}
		for _, value := range values {
			dst.Add(key, value)
		}
	}
}

func forwardedProto(r *http.Request) string {
	if proto := r.Header.Get("X-Forwarded-Proto"); proto != "" {
		return proto
	}
	if r.TLS != nil {
		return "https"
	}
	return "http"
}

func clientIP(r *http.Request) string {
	host, _, err := net.SplitHostPort(r.RemoteAddr)
	if err == nil {
		return host
	}
	return r.RemoteAddr
}

func (e Engine) trackConnection() func(bytes int64) {
	e.metrics.mu.Lock()
	e.metrics.activeConns++
	e.metrics.totalConns++
	e.metrics.mu.Unlock()
	
	return func(bytes int64) {
		e.metrics.mu.Lock()
		e.metrics.activeConns--
		e.metrics.bytesTransferred += bytes
		e.metrics.mu.Unlock()
	}
}

func (e Engine) hls(w http.ResponseWriter, r *http.Request) {
	token, videoID, asset, ok := parseHLSPath(r.URL.Path)
	if !ok {
		http.NotFound(w, r)
		return
	}

	claims, err := e.verifyToken(token)
	if err != nil {
		http.Error(w, "invalid token", http.StatusUnauthorized)
		return
	}
	if fmt.Sprint(claims.VideoID) != videoID {
		http.Error(w, "video mismatch", http.StatusForbidden)
		return
	}
	if err := validateStoragePath(claims.StoragePath); err != nil {
		http.Error(w, "invalid storage path", http.StatusBadRequest)
		return
	}

	switch asset {
	case "master.m3u8":
		e.master(w, r, token, videoID, claims.StoragePath)
	default:
		e.segment(w, r, claims.StoragePath, asset)
	}
}

func parseHLSPath(urlPath string) (token, videoID, asset string, ok bool) {
	trimmed := strings.TrimPrefix(urlPath, "/hls/")
	parts := strings.SplitN(trimmed, "/", 3)
	if len(parts) != 3 || parts[0] == "" || parts[1] == "" || parts[2] == "" {
		return "", "", "", false
	}
	return parts[0], parts[1], parts[2], true
}

func (e Engine) verifyToken(token string) (Claims, error) {
	var claims Claims
	parts := strings.Split(token, ".")
	if len(parts) != 3 {
		return claims, errors.New("invalid jwt format")
	}
	signed := parts[0] + "." + parts[1]
	mac := hmac.New(sha256.New, e.jwtSecret)
	_, _ = mac.Write([]byte(signed))
	expected := base64.RawURLEncoding.EncodeToString(mac.Sum(nil))
	if !hmac.Equal([]byte(expected), []byte(parts[2])) {
		return claims, errors.New("invalid signature")
	}
	payload, err := base64.RawURLEncoding.DecodeString(parts[1])
	if err != nil {
		return claims, err
	}
	if err := json.Unmarshal(payload, &claims); err != nil {
		return claims, err
	}
	if claims.Exp <= time.Now().Unix() {
		return claims, errors.New("expired")
	}
	return claims, nil
}

func validateStoragePath(storagePath string) error {
	if storagePath == "" || strings.Contains(storagePath, "://") || strings.Contains(storagePath, "\\") {
		return errors.New("external or empty path")
	}
	if path.IsAbs(storagePath) || filepath.IsAbs(storagePath) {
		return errors.New("absolute path")
	}
	clean := path.Clean(storagePath)
	if clean == "." || clean != storagePath || strings.HasPrefix(clean, "../") || strings.Contains(clean, "/../") || clean == ".." {
		return errors.New("path traversal")
	}
	return nil
}

func (e Engine) hlsRoot() string {
	return filepath.Join(e.mediaRoot, "hls")
}

func (e Engine) realPath(storagePath string) (string, error) {
	if err := validateStoragePath(storagePath); err != nil {
		return "", err
	}
	root := e.hlsRoot()
	full := filepath.Join(root, filepath.FromSlash(storagePath))
	rel, err := filepath.Rel(root, full)
	if err != nil || strings.HasPrefix(rel, "..") || filepath.IsAbs(rel) {
		return "", errors.New("path escaped media root")
	}
	return full, nil
}

func (e Engine) master(w http.ResponseWriter, r *http.Request, token, videoID, storagePath string) {
	full, err := e.realPath(storagePath)
	if err != nil {
		http.Error(w, "invalid path", http.StatusBadRequest)
		return
	}
	data, err := os.ReadFile(full)
	if err != nil {
		if errors.Is(err, fs.ErrNotExist) {
			http.NotFound(w, r)
			return
		}
		http.Error(w, "read failed", http.StatusInternalServerError)
		return
	}
	rewritten, err := rewritePlaylist(string(data), token, videoID)
	if err != nil {
		http.Error(w, err.Error(), http.StatusBadRequest)
		return
	}
	w.Header().Set("Content-Type", "application/vnd.apple.mpegurl")
	_, _ = w.Write([]byte(rewritten))
}

func rewritePlaylist(input, token, videoID string) (string, error) {
	lines := strings.Split(input, "\n")
	for i, line := range lines {
		trimmed := strings.TrimSpace(line)
		if trimmed == "" || strings.HasPrefix(trimmed, "#") {
			continue
		}
		if strings.Contains(trimmed, "://") || path.IsAbs(trimmed) || strings.Contains(trimmed, "..") || strings.Contains(trimmed, "\\") {
			return "", fmt.Errorf("unsupported segment path: %s", trimmed)
		}
		escaped := path.Clean(trimmed)
		if escaped == "." || strings.HasPrefix(escaped, "../") {
			return "", fmt.Errorf("invalid segment path: %s", trimmed)
		}
		lines[i] = "/hls/" + token + "/" + url.PathEscape(videoID) + "/" + escaped
	}
	return strings.Join(lines, "\n"), nil
}

func (e Engine) segment(w http.ResponseWriter, r *http.Request, storagePath, segment string) {
	if strings.Contains(segment, "://") || path.IsAbs(segment) || strings.Contains(segment, "..") || strings.Contains(segment, "\\") {
		http.Error(w, "invalid segment", http.StatusBadRequest)
		return
	}
	
	// Track connection
	endTrack := e.trackConnection()
	defer endTrack(0) // Tamanho será estimado pelo response writer
	
	base := path.Dir(storagePath)
	full, err := e.realPath(path.Join(base, segment))
	if err != nil {
		http.Error(w, "invalid path", http.StatusBadRequest)
		return
	}
	http.ServeFile(w, r, full)
}

func (e Engine) jellyfin(w http.ResponseWriter, r *http.Request) {
	token, itemID, asset, ok := parseJellyfinPath(r.URL.Path)
	if !ok {
		http.NotFound(w, r)
		return
	}
	claims, err := e.verifyToken(token)
	if err != nil {
		http.Error(w, "invalid token", http.StatusUnauthorized)
		return
	}
	if claims.Provider != "jellyfin" {
		http.Error(w, "invalid provider", http.StatusForbidden)
		return
	}
	if claims.JellyfinItemID != itemID {
		http.Error(w, "item mismatch", http.StatusForbidden)
		return
	}
	base, err := e.allowedJellyfinBase(claims.JellyfinInternalURL)
	if err != nil {
		http.Error(w, "jellyfin url not allowed", http.StatusForbidden)
		return
	}
	if !e.rateLimit.Allow(r.RemoteAddr + ":" + token) {
		http.Error(w, "rate limit exceeded", http.StatusTooManyRequests)
		return
	}

	if asset == "master.m3u8" {
		e.proxyJellyfinMaster(w, r, token, itemID, claims, base)
		return
	}
	e.proxyJellyfinSegment(w, r, token, itemID, asset, claims, base)
}

func parseJellyfinPath(urlPath string) (token, itemID, asset string, ok bool) {
	trimmed := strings.TrimPrefix(urlPath, "/jellyfin/")
	parts := strings.SplitN(trimmed, "/", 3)
	if len(parts) != 3 || parts[0] == "" || parts[1] == "" || parts[2] == "" {
		return "", "", "", false
	}
	return parts[0], parts[1], parts[2], true
}

func (e Engine) allowedJellyfinBase(raw string) (*url.URL, error) {
	normalized, err := normalizeBaseURL(raw)
	if err != nil {
		return nil, err
	}
	if len(e.allowedJellyfin) == 0 {
		return nil, errors.New("no jellyfin allowlist configured")
	}
	if _, ok := e.allowedJellyfin[normalized]; !ok {
		return nil, errors.New("not allowed")
	}
	return url.Parse(normalized)
}

func validateJellyfinBaseURL(u *url.URL) error {
	if u.Scheme != "http" && u.Scheme != "https" {
		return errors.New("unsupported scheme")
	}
	if u.User != nil || u.Hostname() == "" {
		return errors.New("invalid host")
	}
	if ip := net.ParseIP(u.Hostname()); ip != nil && ip.IsUnspecified() {
		return errors.New("invalid ip")
	}
	return nil
}

func (e Engine) jellyfinAPIKey(claims Claims, base *url.URL) string {
	if key := e.jellyfinAPIKeys[fmt.Sprint(claims.JellyfinServerID)]; key != "" {
		return key
	}
	if key := e.jellyfinAPIKeys[strings.TrimRight(base.String(), "/")]; key != "" {
		return key
	}
	return ""
}

func (e Engine) proxyJellyfinMaster(w http.ResponseWriter, r *http.Request, token, itemID string, claims Claims, base *url.URL) {
	target := *base
	target.Path = strings.TrimRight(target.Path, "/") + "/Videos/" + url.PathEscape(itemID) + "/master.m3u8"
	query := target.Query()
	query.Set("MediaSourceId", itemID)
	query.Set("VideoCodec", "h264")
	query.Set("AudioCodec", "aac")
	target.RawQuery = query.Encode()

	data, contentType, err := e.fetchJellyfin(r, target.String(), claims, base)
	if err != nil {
		http.Error(w, "jellyfin fetch failed", http.StatusBadGateway)
		return
	}
	rewritten, err := e.rewriteJellyfinPlaylist(string(data), token, itemID, target.String(), base)
	if err != nil {
		http.Error(w, err.Error(), http.StatusBadGateway)
		return
	}
	if contentType == "" {
		contentType = "application/vnd.apple.mpegurl"
	}
	w.Header().Set("Content-Type", contentType)
	_, _ = w.Write([]byte(rewritten))
}

func (e Engine) proxyJellyfinSegment(w http.ResponseWriter, r *http.Request, token, itemID, encodedSegment string, claims Claims, base *url.URL) {
	decoded, err := base64.RawURLEncoding.DecodeString(encodedSegment)
	if err != nil {
		http.Error(w, "invalid segment", http.StatusBadRequest)
		return
	}
	target, err := e.resolveJellyfinAsset(string(decoded), base.String()+"/")
	if err != nil {
		http.Error(w, "invalid segment target", http.StatusBadRequest)
		return
	}
	if isHLSPlaylist(target) {
		data, contentType, err := e.fetchJellyfin(r, target, claims, base)
		if err != nil {
			http.Error(w, "jellyfin fetch failed", http.StatusBadGateway)
			return
		}
		rewritten, err := e.rewriteJellyfinPlaylist(string(data), token, itemID, target, base)
		if err != nil {
			http.Error(w, err.Error(), http.StatusBadGateway)
			return
		}
		if contentType == "" {
			contentType = "application/vnd.apple.mpegurl"
		}
		w.Header().Set("Content-Type", contentType)
		_, _ = w.Write([]byte(rewritten))
		return
	}
	e.streamJellyfin(w, r, target, claims, base)
}

func isHLSPlaylist(target string) bool {
	u, err := url.Parse(target)
	if err != nil {
		return false
	}
	return strings.HasSuffix(strings.ToLower(u.Path), ".m3u8")
}

func (e Engine) rewriteJellyfinPlaylist(input, token, itemID, playlistURL string, base *url.URL) (string, error) {
	lines := strings.Split(input, "\n")
	for i, line := range lines {
		trimmed := strings.TrimSpace(line)
		if trimmed == "" || strings.HasPrefix(trimmed, "#") {
			continue
		}
		assetURL, err := e.resolveJellyfinAsset(trimmed, playlistURL)
		if err != nil {
			return "", err
		}
		if err := ensureSameBase(assetURL, base); err != nil {
			return "", err
		}
		encoded := base64.RawURLEncoding.EncodeToString([]byte(assetURL))
		lines[i] = "/jellyfin/" + token + "/" + url.PathEscape(itemID) + "/" + encoded
	}
	return strings.Join(lines, "\n"), nil
}

func (e Engine) resolveJellyfinAsset(asset, baseURL string) (string, error) {
	if strings.Contains(asset, "\\") || strings.Contains(asset, "..") {
		return "", errors.New("invalid asset path")
	}
	base, err := url.Parse(baseURL)
	if err != nil {
		return "", err
	}
	ref, err := url.Parse(asset)
	if err != nil {
		return "", err
	}
	resolved := base.ResolveReference(ref)
	if err := validateJellyfinBaseURL(resolved); err != nil {
		return "", err
	}
	return resolved.String(), nil
}

func ensureSameBase(target string, base *url.URL) error {
	u, err := url.Parse(target)
	if err != nil {
		return err
	}
	if !strings.EqualFold(u.Scheme, base.Scheme) || !strings.EqualFold(u.Host, base.Host) {
		return errors.New("asset points outside configured jellyfin")
	}
	return nil
}

func (e Engine) fetchJellyfin(r *http.Request, target string, claims Claims, base *url.URL) ([]byte, string, error) {
	u, err := url.Parse(target)
	if err != nil {
		return nil, "", err
	}
	if key := e.jellyfinAPIKey(claims, base); key != "" {
		query := u.Query()
		query.Set("api_key", key)
		u.RawQuery = query.Encode()
	}
	req, err := http.NewRequestWithContext(r.Context(), http.MethodGet, u.String(), nil)
	if err != nil {
		return nil, "", err
	}
	if key := e.jellyfinAPIKey(claims, base); key != "" {
		req.Header.Set("X-Emby-Token", key)
	}
	req.Header.Set("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
	resp, err := e.httpClient.Do(req)
	if err != nil {
		return nil, "", err
	}
	defer resp.Body.Close()
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return nil, "", fmt.Errorf("jellyfin status %d", resp.StatusCode)
	}
	data, err := io.ReadAll(resp.Body)
	return data, resp.Header.Get("Content-Type"), err
}

func (e Engine) streamJellyfin(w http.ResponseWriter, r *http.Request, target string, claims Claims, base *url.URL) {
	// Track connection
	endTrack := e.trackConnection()
	
	u, err := url.Parse(target)
	if err != nil {
		endTrack(0)
		http.Error(w, "bad request", http.StatusBadRequest)
		return
	}
	if key := e.jellyfinAPIKey(claims, base); key != "" {
		query := u.Query()
		query.Set("api_key", key)
		u.RawQuery = query.Encode()
	}
	req, err := http.NewRequestWithContext(r.Context(), http.MethodGet, u.String(), nil)
	if err != nil {
		endTrack(0)
		http.Error(w, "bad request", http.StatusBadRequest)
		return
	}
	if key := e.jellyfinAPIKey(claims, base); key != "" {
		req.Header.Set("X-Emby-Token", key)
	}
	req.Header.Set("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
	resp, err := e.httpClient.Do(req)
	if err != nil {
		endTrack(0)
		http.Error(w, "jellyfin fetch failed", http.StatusBadGateway)
		return
	}
	defer resp.Body.Close()
	copySafeHeaders(w.Header(), resp.Header)
	w.WriteHeader(resp.StatusCode)
	written, _ := io.Copy(w, resp.Body)
	endTrack(written)
}

func copySafeHeaders(dst, src http.Header) {
	for _, key := range []string{"Content-Type", "Content-Length", "Cache-Control", "Last-Modified", "ETag"} {
		if value := src.Get(key); value != "" {
			dst.Set(key, value)
		}
	}
}
