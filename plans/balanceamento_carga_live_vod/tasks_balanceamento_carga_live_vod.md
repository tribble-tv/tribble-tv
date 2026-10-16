# Tasks: Balanceamento de Carga + Live/VOD Streaming

## Task 1: Criar Modelos Database
**Status**: pending
**Priority**: high

### 1.1 StreamingServer Model
```python
# backend/models/streaming_server.py
class StreamingServer(Base):
    __tablename__ = "streaming_servers"
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    host = db.Column(db.String(255), nullable=False)
    port = db.Column(db.Integer, default=8080)
    protocol = db.Column(db.String(10), default="http")
    is_active = db.Column(db.Boolean, default=True)
    max_connections = db.Column(db.Integer, default=100)
    current_connections = db.Column(db.Integer, default=0)
    priority = db.Column(db.Integer, default=100)
    region = db.Column(db.String(50))
    health_status = db.Column(db.String(20), default="unknown")
    last_health_check = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
```

### 1.2 LiveStream Model
```python
# backend/models/live_stream.py
class LiveStream(Base):
    __tablename__ = "live_streams"
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    stream_key = db.Column(db.String(100), unique=True, nullable=False)
    status = db.Column(db.String(20), default="offline")  # offline/starting/live/ended
    server_id = db.Column(db.Integer, db.ForeignKey("streaming_servers.id"))
    started_at = db.Column(db.DateTime)
    ended_at = db.Column(db.DateTime)
    viewer_count = db.Column(db.Integer, default=0)
    ingest_url = db.Column(db.String(500))
    playback_url = db.Column(db.String(500))
    is_active = db.Column(db.Boolean, default=True)
```

### 1.3 Connection Model
```python
# backend/models/connection.py
class Connection(Base):
    __tablename__ = "connections"
    
    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.String(100), nullable=False)
    server_id = db.Column(db.Integer, db.ForeignKey("streaming_servers.id"))
    video_id = db.Column(db.Integer, db.ForeignKey("videos.id"), nullable=True)
    live_stream_id = db.Column(db.Integer, db.ForeignKey("live_streams.id"), nullable=True)
    started_at = db.Column(db.DateTime, default=datetime.utcnow)
    ended_at = db.Column(db.DateTime)
    bytes_transferred = db.Column(db.BigInteger, default=0)
    user_agent = db.Column(db.String(255))
    ip_address = db.Column(db.String(45))
```

### 1.4 Atualizar Models __init__.py
- [ ] Exportar novos modelos

---

## Task 2: Criar Load Balancer Service
**Status**: pending
**Priority**: high

### 2.1 Algoritmos de Balanceamento
```python
# backend/services/load_balancer_service.py

class LoadBalancerService:
    STRATEGIES = ["round_robin", "weighted", "least_connections", "health_based"]
    
    def __init__(self, strategy="round_robin"):
        self.strategy = strategy
        self._counter = 0
    
    def get_server(self, client_id=None):
        """Retorna o melhor servidor baseado na estratégia."""
        if self.strategy == "round_robin":
            return self._round_robin()
        elif self.strategy == "least_connections":
            return self._least_connections()
        elif self.strategy == "weighted":
            return self._weighted_round_robin()
        else:
            return self._health_based()
    
    def _round_robin(self):
        servers = self._get_active_servers()
        if not servers:
            return None
        idx = self._counter % len(servers)
        self._counter += 1
        return servers[idx]
    
    def _least_connections(self):
        servers = self._get_active_servers()
        if not servers:
            return None
        return min(servers, key=lambda s: s.current_connections)
```

### 2.2 Health Check Service
```python
# backend/services/server_health_service.py

class ServerHealthService:
    CHECK_INTERVAL = 30  # segundos
    TIMEOUT = 5
    MAX_FAILURES = 3
    
    def check_server(self, server):
        """Verifica saúde de um servidor."""
        url = f"{server.protocol}://{server.host}:{server.port}/health"
        try:
            response = requests.get(url, timeout=self.TIMEOUT)
            healthy = response.status_code == 200
            return {
                "healthy": healthy,
                "latency_ms": response.elapsed.total_seconds() * 1000,
                "status_code": response.status_code
            }
        except Exception as e:
            return {"healthy": False, "error": str(e)}
```

---

## Task 3: Modificar Go-Engine
**Status**: pending
**Priority**: high

### 3.1 Health Endpoint
```go
// Adicionar em main.go
func (e Engine) health(w http.ResponseWriter, r *http.Request) {
    metrics := map[string]interface{}{
        "status": "healthy",
        "timestamp": time.Now().Unix(),
        "active_connections": e.getActiveConnections(),
        "load_average": getLoadAverage(),
    }
    json.NewEncoder(w).Encode(metrics)
}
```

### 3.2 Métricas de Conexão
```go
type ConnectionMetrics struct {
    mu sync.RWMutex
    active int64
    total  int64
    bytesTransferred int64
}

func (cm *ConnectionMetrics) Increment() {
    cm.mu.Lock()
    defer cm.mu.Unlock()
    cm.active++
    cm.total++
}

func (cm *ConnectionMetrics) Decrement(bytes int64) {
    cm.mu.Lock()
    defer cm.mu.Unlock()
    cm.active--
    cm.bytesTransferred += bytes
}
```

---

## Task 4: Admin Interface
**Status**: pending
**Priority**: medium

### 4.1 Servidores de Streaming
- [ ] Listar servidores com status
- [ ] Adicionar/editar servidor
- [ ] Botão de health check manual
- [ ] Visualização de conexões ativas

### 4.2 Streams Live
- [ ] Listar streams
- [ ] Criar stream (gerar stream key)
- [ ] Iniciar/parar stream
- [ ] Visualização de espectadores

### 4.3 Dashboard de Métricas
- [ ] Gráfico de conexões por servidor
- [ ] Mapa de distribuição geográfica
- [ ] Alertas de servidores unhealthy

---

## Task 5: Live Streaming Endpoints
**Status**: pending
**Priority**: medium

### 5.1 Ingest (OBS/FFmpeg)
```
RTMP: rtmp://server:1935/live/{stream_key}
```

### 5.2 Playback HLS
```
GET /live/{stream_key}/playlist.m3u8
GET /live/{stream_key}/{segment}.ts
```

### 5.3 WebRTC (opcional futuro)
```
WebSocket: wss://server/ws/{stream_key}
```

---

## Task 6: Testes
**Status**: pending
**Priority**: medium

- [ ] Teste de carga com múltiplos clientes
- [ ] Teste de failover (quando servidor cai)
- [ ] Teste de ingest RTMP
- [ ] Teste de playback HLS live

---

## Task 7: Documentação
**Status**: pending
**Priority**: low

- [ ] README de configuração de servidores
- [ ] Guia de ingest com OBS
- [ ] API documentation
- [ ] Troubleshooting guide
