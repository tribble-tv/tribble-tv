# Porgs TV

Painel central e engine HLS para distribuição de vídeos com suporte a multiplos servidores de midia e integracao nativa com Jellyfin.

## Arquitetura

```
client (Flask :5000)  --JWT-->  go-engine (Go :8080)
        |
        +-- API Xtream/M3U/player publico

panel-admin (Flask :5001)
        |
        +-- rotas /admin/*

Jellyfin :8096 (opcional)
```

- **client** - app Flask publico com `/client/*`, `/playlist.m3u`, `/player_api.php`, `/get.php`, `/movie/*` e `/live/*`.
- **panel-admin** - painel Flask administrativo com rotas `/admin/*`, separado do consumo publico.
- **go-engine** - engine leve em Go que valida JWTs e serve HLS local ou faz proxy de streams Jellyfin.
- **jellyfin** - servidor Jellyfin opcional, gerenciado pelo painel via API.
- **kodi-headless** - runtime Kodi isolado para executar add-ons.
- **kodi-resolver** - ponte HTTP usada pelo admin para resolver fontes Repo/add-on em URLs tocaveis.

## Inicio rapido

### Docker Compose (recomendado)

```bash
docker compose up --build
```

Acesse o catalogo em `http://localhost:5000/client/` e o painel admin em `http://localhost:5001/admin/`.

### Desenvolvimento local

```bash
python -m venv .venv
# Linux/macOS
. .venv/bin/activate
# Windows PowerShell
.\.venv\Scripts\Activate.ps1

pip install -r requirements.txt
flask --app backend.client_app:app run --host=0.0.0.0 --port=5000
flask --app backend.admin_app:app run --host=0.0.0.0 --port=5001
```

Se `flask` não for reconhecido no Windows PowerShell, execute o módulo pelo Python do ambiente virtual, a partir da raiz do projeto:

```powershell
.\.venv\Scripts\python.exe -m flask --app backend.client_app:app run --host=0.0.0.0 --port=5000
.\.venv\Scripts\python.exe -m flask --app backend.admin_app:app run --host=0.0.0.0 --port=5001
```

Engine Go separada:

```bash
cd go-engine
go run main.go
```

## Acessos

| Servico | URL | Descricao |
|---|---|---|
| Cliente/catalogo | `http://localhost:5000/client/` | Interface publica de consumo |
| Xtream API | `http://localhost:5000/player_api.php` | API publica para players IPTV |
| Playlist M3U | `http://localhost:5000/playlist.m3u` | Playlist publica |
| Painel admin | `http://localhost:5001/admin/` | Interface de administracao |
| go-engine | `http://localhost:8080` | Status da engine (JSON) |
| go-engine health | `http://localhost:8080/health` | Health check (requer `X-API-Key`) |
| Jellyfin | `http://localhost:8096` | Interface web do Jellyfin |
| ngrok panel inspector | `http://localhost:4040` | Inspecao de requests do tunel do painel (quando ativo) |
| ngrok engine inspector | `http://localhost:4041` | Inspecao de requests do tunel da engine (quando ativo) |

## ngrok (acesso externo)

Os servicos `ngrok-panel` e `ngrok-engine` expoem o admin e a engine publicamente via tuneis HTTPS. Eles usam o perfil `ngrok` do Compose, portanto **nao sobem por padrao**. O consumo publico principal fica no servico `client` em `:5000`; configure `CLIENT_PUBLIC_URL` para a URL publica usada por catalogo, M3U e Xtream.

### Configuracao

1. Crie uma conta gratuita em https://ngrok.com e copie seu authtoken
2. Preencha no `.env`:

```env
NGROK_AUTHTOKEN=seu_token_aqui
```

### Subir com ngrok

```bash
docker compose --profile ngrok up -d
```

### Subir sem ngrok (padrao)

```bash
docker compose up -d
```

A URL publica do admin aparece em `http://localhost:4040` e a URL publica da engine aparece em `http://localhost:4041`, ou nos logs:

```bash
docker compose logs ngrok-panel ngrok-engine
```

> **Nota:** planos gratuitos do ngrok geram URLs aleatorias a cada reinicio. Para URL fixa, use um plano pago com `--url https://seu-dominio.ngrok.app` no `command` do servico.

---

## Configurando URLs no .env

> Estado atual: o consumo publico fica no servico `client` em `http://localhost:5000`, e o admin fica separado no servico `panel-admin` em `http://localhost:5001/admin/`. Para links mostrados no admin, use `CLIENT_PUBLIC_URL`; para acesso ao painel, use `PANEL_PUBLIC_URL`. A go-engine encaminha Xtream/M3U internamente para `CLIENT_INTERNAL_URL=http://client:5000`.

Ao subir os tuneis ngrok voce obtem enderecos publicos separados para admin, engine e, se exposto, cliente/API. Veja exatamente onde cada um vai:

```
http://localhost:4040  →  URL publica do admin    ex: https://<tunel-painel>.ngrok-free.app
http://localhost:4041  →  URL publica da engine   ex: https://<tunel-engine>.ngrok-free.app
client :5000           →  URL publica do consumo  ex: https://cliente.exemplo.com
```

### Mapa visual

```
┌─────────────────────────────────────────────────────────────────────────┐
│                            .env                                         │
│                                                                         │
│  CLIENT_PUBLIC_URL         ←── URL publica do cliente/API (:5000)        │
│  PANEL_PUBLIC_URL          ←── URL do admin (4040 ou :5001)              │
│  ENGINE_PUBLIC_URL         ←── URL da engine (4041)                     │
│  STREAM_PUBLIC_URL         ←── mesma URL da engine (4041)               │
│                                                                         │
│  MEDIA_SERVER_SEED_PUBLIC_URLS = <URL cliente/API>, <URL engine>        │
│  MEDIA_SEED_PUBLIC_URLS        = <URL engine>                           │
└─────────────────────────────────────────────────────────────────────────┘
```

### Exemplo preenchido

Suponha que o ngrok gerou:
- Admin → `https://<tunel-painel>.ngrok-free.app`  (porta 4040)
- Engine → `https://<tunel-engine>.ngrok-free.app`  (porta 4041)
- Cliente/API → `https://cliente.exemplo.com`  (porta 5000)

```env
# ── URLs publicas dos tuneis ────────────────────────────────────────────
CLIENT_PUBLIC_URL=https://cliente.exemplo.com               # URL publica do consumo: /client, M3U e Xtream
PANEL_PUBLIC_URL=https://<tunel-painel>.ngrok-free.app   # URL do admin (4040)
ENGINE_PUBLIC_URL=https://<tunel-engine>.ngrok-free.app  # URL da engine (4041)
STREAM_PUBLIC_URL=https://<tunel-engine>.ngrok-free.app  # alias da engine (4041)

# ── URLs internas (comunicacao entre containers — nao mudam) ────────────
ENGINE_INTERNAL_URL=http://go-engine:8080
CLIENT_INTERNAL_URL=http://client:5000

# ── Registros MediaServer criados automaticamente no boot ───────────────
# Formato: valor-cliente/API, valor-engine  (mesma ordem nos tres campos abaixo)
MEDIA_SERVER_SEED_NAMES=client api,go-engine stream
MEDIA_SERVER_SEED_TYPES=panel,go-engine
MEDIA_SERVER_SEED_PUBLIC_URLS=https://cliente.exemplo.com,https://<tunel-engine>.ngrok-free.app
#                              ^── URL cliente/API (:5000)                ^── URL engine (4041)
MEDIA_SERVER_SEED_INTERNAL_URLS=http://client:5000,http://go-engine:8080
MEDIA_SERVER_SEED_API_KEYS=,dev-engine-key    # client nao tem key; engine tem
MEDIA_SERVER_SEED_PRIORITIES=10,100

# ── Registro legado MEDIA_SEED (so a engine) ────────────────────────────
MEDIA_SEED_PUBLIC_URLS=https://<tunel-engine>.ngrok-free.app  # URL engine (4041)
MEDIA_SEED_INTERNAL_URLS=http://go-engine:8080
MEDIA_SEED_API_KEYS=dev-engine-key
```

### Resumo rapido

| Variavel | Qual URL usar |
|---|---|
| `PANEL_PUBLIC_URL` | URL do painel — `http://localhost:4040` mostra o endereco |
| `ENGINE_PUBLIC_URL` | URL da engine — `http://localhost:4041` mostra o endereco |
| `STREAM_PUBLIC_URL` | Igual a `ENGINE_PUBLIC_URL` (alias legado) |
| `ENGINE_INTERNAL_URL` | **Nunca muda** → `http://go-engine:8080` |
| `CLIENT_INTERNAL_URL` | **Nunca muda** → `http://client:5000` |
| `MEDIA_SERVER_SEED_PUBLIC_URLS` | `<URL cliente/API>,<URL engine>` (nessa ordem) |
| `MEDIA_SEED_PUBLIC_URLS` | Apenas `<URL engine>` |

> **Dica:** Apos alterar o `.env` basta reiniciar sem rebuild:
> ```bash
> docker compose up client panel-admin go-engine -d --force-recreate
> ```

## Variaveis de ambiente

### panel

| Variavel | Padrao | Descricao |
|---|---|---|
| `SECRET_KEY` | `dev-secret` | Chave Flask para sessoes |
| `JWT_SECRET` | `dev-jwt-secret` | Segredo compartilhado com a engine |
| `DATABASE_URL` | `sqlite:////data/porgs_tv.db` | URL do banco SQLAlchemy |
| `SERVER_SELECTION_STRATEGY` | `priority_fallback` | Estrategia de selecao de servidor |
| `CLIENT_PUBLIC_URL` | `http://localhost:5000` | URL publica do cliente/API, usada pelo admin para exibir links de player, M3U e Xtream |
| `PANEL_PUBLIC_URL` | `http://localhost:5001` | URL publica do painel admin, usada para referencia operacional |
| `ENGINE_PUBLIC_URL` | `STREAM_PUBLIC_URL` ou `http://localhost:8080` | URL publica da engine para links Jellyfin e Xtream |
| `ENGINE_INTERNAL_URL` | `http://go-engine:8080` | URL interna da engine usada pelo painel para servir `/movie/...` sem redirect |
| `STREAM_PUBLIC_URL` | `http://localhost:8080` | Alias legado para `ENGINE_PUBLIC_URL` |
| `KODI_RESOLVER_URL` | `http://kodi-resolver:8090` | URL interna do resolver usado pelo admin para fontes Repo/add-on Kodi |
| `VIDEO_TOKEN_TTL_SECONDS` | `3600` | Tempo de vida dos tokens JWT |
| `MEDIA_SERVER_SEED_NAMES` | _(vazio)_ | Nomes dos registros `MediaServer` iniciais, separados por virgula |
| `MEDIA_SERVER_SEED_TYPES` | _(vazio)_ | Tipos dos registros iniciais (`panel`, `go-engine`), na mesma ordem das URLs |
| `MEDIA_SERVER_SEED_PUBLIC_URLS` | _(vazio)_ | URLs publicas dos registros iniciais, separadas por virgula |
| `MEDIA_SERVER_SEED_INTERNAL_URLS` | _(vazio)_ | URLs internas opcionais dos registros iniciais, na mesma ordem das URLs publicas |
| `MEDIA_SERVER_SEED_API_KEYS` | _(vazio)_ | API keys dos registros iniciais; obrigatoria para `go-engine`, opcional para `panel` |
| `MEDIA_SERVER_SEED_PRIORITIES` | _(vazio)_ | Prioridades dos registros iniciais, na mesma ordem das URLs |
| `JELLYFIN_SEED_URLS` | _(vazio)_ | URLs dos servidores Jellyfin a cadastrar no boot (separadas por virgula) |
| `JELLYFIN_SEED_USERNAMES` | _(vazio)_ | Usuarios admin de cada servidor (mesma ordem que URLS) |
| `JELLYFIN_SEED_PASSWORDS` | _(vazio)_ | Senhas de cada servidor (mesma ordem que URLS) |
| `JELLYFIN_SEED_API_KEYS` | _(vazio)_ | API keys de cada servidor (mesma ordem que URLS) |
| `XTREAM_SEED_USERS` | _(vazio)_ | Usuarios Xtream iniciais (formato: `user1:pass1,user2:pass2`) |

### go-engine

| Variavel | Padrao | Descricao |
|---|---|---|
| `JWT_SECRET` | `dev-jwt-secret` | Deve ser igual ao do painel |
| `ENGINE_API_KEY` | `dev-engine-key` | Chave para o endpoint `/health` |
| `MEDIA_ROOT` | `/media` | Raiz dos arquivos de midia |
| `ENGINE_ADDR` | `:8080` | Endereco de escuta |
| `PANEL_INTERNAL_URL` | `http://client:5000` | URL interna do servico publico para proxy dos endpoints Xtream (`/player_api.php`, `/panel_api.php`, `/get.php`, `/movie/...`) |
| `JELLYFIN_ALLOWED_INTERNAL_URLS` | _(vazio)_ | URLs internas Jellyfin permitidas no proxy (separadas por virgula) |
| `JELLYFIN_API_KEYS` | _(vazio)_ | Mapa `server_id=key,url=key` de API keys do Jellyfin |
| `RATE_LIMIT_REQUESTS` | `240` | Maximo de requisicoes por minuto por cliente+token |

## Modelos de dados

| Modelo | Tabela | Descricao |
|---|---|---|
| `Video` | `videos` | Video catalogado; `source_type` pode ser `hls`, `jellyfin`, `embed` ou `torrent` |
| `VideoLocation` | `video_locations` | Associa um video a um `MediaServer` com `storage_path` |
| `MediaServer` | `media_servers` | Engine de midia com URL, prioridade, peso e status |
| `JellyfinServer` | `jellyfin_servers` | Instancia Jellyfin gerenciada pelo painel |
| `JellyfinLibrary` | `jellyfin_libraries` | Biblioteca sincronizada de um servidor Jellyfin |
| `JellyfinItem` | `jellyfin_items` | Item individual de uma biblioteca Jellyfin |
| `XtreamUser` | `xtream_users` | Usuario para autenticacao API Xtream Codes |
| `StreamingServer` | `streaming_servers` | Servidor de streaming para balanceamento de carga |
| `Connection` | `connections` | Conexao ativa de cliente (tracking de viewers) |
| `LiveStream` | `live_streams` | Transmissao ao vivo (Live Streaming) - Em breve |
| `KodiSource` | `kodi_sources` | Fonte Kodi M3U/HLS ou Repo/add-on sincronizada para `Video` |

## Rotas admin

| Rota | Descricao |
|---|---|
| `GET /admin/media-servers` | Lista servidores de midia |
| `GET/POST /admin/media-servers/create` | Cadastra servidor |
| `GET/POST /admin/media-servers/<id>/edit` | Edita servidor |
| `POST /admin/media-servers/<id>/health` | Health check manual |
| `GET/POST /admin/load-balancer` | Configuracao visual do balanceador (estrategias VOD e Live) |
| `GET /admin/videos/<id>/locations` | Lista localizacoes do video |
| `GET/POST /admin/videos/<id>/locations/create` | Cria localizacao |
| `GET/POST /admin/video-locations/<id>/edit` | Edita localizacao |
| `POST /admin/video-locations/<id>/delete` | Remove localizacao |
| `GET /admin/jellyfin-servers` | Lista servidores Jellyfin |
| `GET/POST /admin/jellyfin-servers/create` | Cadastra servidor Jellyfin |
| `GET/POST /admin/jellyfin-servers/<id>/edit` | Edita servidor Jellyfin |
| `POST /admin/jellyfin-servers/<id>/health` | Health check Jellyfin |
| `POST /admin/jellyfin-servers/<id>/sync-libraries` | Sincroniza bibliotecas |
| `POST /admin/jellyfin-servers/<id>/sync-items` | Sincroniza itens |
| `GET /admin/jellyfin-items` | Lista itens Jellyfin com toggle ativo/inativo |
| `POST /admin/jellyfin-items/<id>/toggle` | Ativa ou desativa um item Jellyfin |
| `GET /admin/xtream` | Lista usuarios Xtream Codes |
| `GET/POST /admin/xtream/new` | Cria novo usuario Xtream |
| `GET/POST /admin/xtream/<id>/edit` | Edita usuario Xtream |
| `POST /admin/xtream/<id>/toggle` | Ativa/desativa usuario |
| `POST /admin/xtream/<id>/delete` | Remove usuario Xtream |
| `GET /admin/kodi-sources` | Lista fontes Kodi M3U/HLS e Repo/add-on |
| `POST /admin/kodi-sources/create` | Cria fonte Kodi e tenta sincronizar automaticamente |
| `POST /admin/kodi-sources/<id>/sync` | Sincroniza uma fonte Kodi existente |

## Rotas cliente

| Rota | Descricao |
|---|---|
| `GET /` | Redireciona para `/client/` no servico publico |
| `GET /client/player/<video_id>` | Player HTML com URL assinada |
| `GET /play/<video_id>` | Redirect direto para stream (IPTV/M3U) |
| `GET /playlist.m3u` | Playlist M3U com todos os itens Jellyfin ativos |
| `GET /open-jellyfin/<video_id>` | Abre o item na UI web do Jellyfin |

## API Xtream Codes (XCIPTV)

Implementacao completa da API Xtream Codes para compatibilidade com players IPTV como XCIPTV, TiviMate, e similares.

### Endpoints Xtream

| Endpoint | Parametros | Descricao |
|---|---|---|
| `GET /player_api.php` | `username`, `password` | Informacoes do usuario e servidor |
| `GET /player_api.php?action=get_vod_categories` | `username`, `password` | Lista categorias VOD |
| `GET /player_api.php?action=get_vod_streams` | `username`, `password`, `category_id` | Lista streams VOD |
| `GET /player_api.php?action=get_vod_info` | `username`, `password`, `vod_id` | Info detalhada VOD |
| `GET /get.php` | `username`, `password` | Playlist M3U completa |

### Configuracao XCIPTV com Xtream Codes

1. **Modo**: Xtream Codes API (nao M3U URL)
2. **XC API URL**: `http://seu-servidor:5000/player_api.php`
3. **Username**: (criar em `http://localhost:5001/admin/xtream/`)
4. **Password**: (definir ao criar usuario)

Usuario padrao: `admin` / `admin123`

### Resposta exemplo (player_api.php)

```json
{
  "user_info": {
    "username": "admin",
    "auth": 1,
    "status": "Active",
    "max_connections": "1",
    "message": "Bem-vindo ao Tribble TV"
  },
  "server_info": {
    "url": "seu-servidor.com",
    "port": "80",
    "https_port": "443",
    "server_protocol": "https"
  }
}
```

## Balanceamento de Carga

Sistema de balanceamento de carga entre multiplos servidores de streaming com health check automatico e varios algoritmos de distribuicao.

### Arquitetura

```
Cliente (XCIPTV)
      |
      v
Load Balancer (client:5000)
      |
      |---> go-engine-1 (VPS 1)
      |---> go-engine-2 (VPS 2)
      +---> go-engine-N (VPS N)
```

### Algoritmos de Balanceamento

| Estrategia | Descricao | Uso recomendado |
|---|---|---|
| `round_robin` (padrao) | Distribui igualmente em ordem circular | Carga uniforme |
| `weighted` | Considera peso (priority) de cada servidor | VPS com capacidades diferentes |
| `least_connections` | Direciona para servidor com menos conexoes | Evitar sobrecarga |
| `random` | Selecao aleatoria | Simplicidade |
| `health_based` | Considera latencia + carga | Maxima performance |

### Gerenciamento de Servidores

Acesse `http://localhost:5001/admin/xtream/` para gerenciar usuarios Xtream e visualizar status.

### Health Check

- Checagem automatica a cada 30 segundos
- Endpoint: `GET /health` em cada go-engine
- 3 falhas consecutivas = servidor marcado como `unreachable`
- Metricas: latencia, conexoes ativas, uptime

### Modelos de Balanceamento

| Modelo | Tabela | Descricao |
|---|---|---|
| `StreamingServer` | `streaming_servers` | Servidor de streaming com capacidade e status |
| `Connection` | `connections` | Conexao ativa de cliente (tracking) |

## Torrent Streaming (WebTorrent)

Suporte a streaming progressivo de vídeos via BitTorrent usando o microserviço **torrent-node** (Node.js + WebTorrent).

### Arquitetura

```
Cliente → Flask :5000/torrent/stream/<video_id>
              ↓ proxy HTTP range requests
         torrent-node :9119/stream?magnet=...
              ↓
         WebTorrent (peers BitTorrent)
```

### Cadastro via painel admin

1. Acesse `http://localhost:5001/admin/videos`
2. Clique em **Novo Torrent**
3. Cole o **magnet link** (`magnet:?xt=urn:btih:...`) ou URL de um `.torrent`
4. Preencha título, categoria e thumbnail (opcionais)
5. O vídeo aparecerá no catálogo com badge **BitTorrent**

### Variáveis de ambiente

| Variável | Padrão | Descrição |
|---|---|---|
| `TORRENT_NODE_URL` | `http://torrent-node:9119` | URL interna do microserviço torrent |
| `MAX_TORRENTS` | `10` | Máximo de torrents ativos simultâneos |

### Rotas cliente

| Rota | Descrição |
|---|---|
| `GET /torrent/stream/<video_id>` | Proxy de streaming com Range requests |
| `GET /torrent/info/<video_id>` | Metadados e progresso do torrent |
| `GET /torrent/status` | Status de todos os torrents ativos |

### Rotas admin

| Rota | Descrição |
|---|---|
| `GET/POST /admin/videos/torrent/create` | Cadastra vídeo torrent |
| `GET/POST /admin/videos/torrent/<id>/edit` | Edita vídeo torrent |
| `POST /admin/videos/torrent/<id>/delete` | Remove vídeo torrent |
| `GET /admin/torrent-node/status` | Status do torrent-node (JSON) |
| `POST /admin/torrent-node/remove` | Remove torrent ativo da memória |

### Observações

- O streaming começa enquanto o download ainda está em andamento (progressivo)
- O player exibe overlay com status de peers e % baixado
- Torrents são mantidos em cache em `/tmp/torrents` no volume `torrent-cache`
- Use **somente conteúdo de domínio público ou com licença permissiva**

## Live Streaming (Em Breve)

Transmissao ao vivo com suporte a ingest RTMP e playback HLS.

### Fluxo Planejado

```
OBS/FFmpeg --RTMP--> go-engine --HLS--> Viewers
```

### Endpoints Futuros

| Endpoint | Descricao |
|---|---|
| `POST /ingest/{stream_key}` | Ingest RTMP para streamers |
| `GET /live/{stream_key}/playlist.m3u8` | Playback HLS para viewers |
| `GET /live/{stream_key}/stats` | Estatisticas da live |

## Endpoints da go-engine

| Endpoint | Auth | Descricao |
|---|---|---|
| `GET /` | Publico | Status basico |
| `GET /health` | Publico/Auth | Status da engine (metricas detalhadas com `X-API-Key`) |
| `GET /hls/{token}/{video_id}/master.m3u8` | JWT no path | Playlist HLS reescrita |
| `GET /hls/{token}/{video_id}/{segment}` | JWT no path | Segmento `.ts` local |
| `GET /jellyfin/{token}/{item_id}/master.m3u8` | JWT no path | Playlist via proxy Jellyfin |
| `GET /jellyfin/{token}/{item_id}/{segment_b64}` | JWT no path | Segmento via proxy Jellyfin |

### Resposta Health Check (com X-API-Key)

```json
{
  "status": "healthy",
  "timestamp": 1718234567,
  "uptime_seconds": 3600,
  "active_connections": 42,
  "total_connections": 150,
  "bytes_transferred": 1073741824,
  "rate_limit_requests": 240
}
```

## Kodi Sources

O painel aceita fontes Kodi em `http://localhost:5001/admin/kodi-sources`.

### M3U/HLS

1. Tipo: `M3U/HLS`
2. URL da fonte: playlist HTTP/HTTPS `.m3u` ou `.m3u8`
3. Clique em `Salvar`; o painel tenta sincronizar automaticamente.

### Repo/add-on

1. Tipo: `Repo/add-on`
2. URL da fonte: URL do repositorio/ZIP do add-on
3. Add-on ID: exemplo `plugin.video.exemplo`
4. Caminho inicial opcional: exemplo `plugin://plugin.video.exemplo/`
5. Clique em `Salvar`; o admin chama `KODI_RESOLVER_URL` e importa apenas URLs HTTP/HTTPS resolvidas.

O resolver roda isolado no Compose:

```env
KODI_RESOLVER_URL=http://kodi-resolver:8090
KODI_JSONRPC_URL=http://kodi-headless:8080/jsonrpc
```

Itens `plugin://...` crus nao entram no catalogo. Se o add-on exigir login ou configuracao manual, a fonte fica com status `needs_config` e o erro aparece na tela. Itens resolvidos entram como `Video(source_type="embed", external_provider="kodi_addon")` e aparecem no catalogo, `/playlist.m3u`, `/get.php` e `/player_api.php`.

## Usando com players IPTV (XCIPTV, TiviMate, VLC)

O servico publico `client` expoe uma playlist M3U com videos ativos do catalogo. Itens HLS/Jellyfin usam streams autenticados via JWT; embeds e fontes Kodi resolvidas usam a URL HTTP/HTTPS cadastrada.

### URL da playlist

```
http://localhost:5000/playlist.m3u
```

### Configurar no XCIPTV

1. Abra o XCIPTV → **Adicionar lista** → tipo **M3U**
2. Cole a URL da playlist
3. Salve — os filmes e series aparecem organizados por grupo (`jellyfin` ou `hls`)

### Fluxo do stream

```
XCIPTV abre /playlist.m3u
    → baixa lista com URLs /play/<id>
    → cada /play/<id> redireciona para URL JWT da go-engine
    → go-engine faz proxy do Jellyfin e entrega o HLS
```

### Controle do catalogo

Em `http://localhost:5001/admin/jellyfin-items`:

- **Desativar** um item o remove da playlist (sem apagar do Jellyfin)
- **Ativar** o devolve para a lista
- O sync automatico (Sync Items) importa novos itens ja ativados

### Acesso externo (ngrok)

O ngrok atual aponta para a **go-engine** (porta 8080). Para expor a playlist externamente adicione um segundo tunel no `docker-compose.yml`:

```yaml
  ngrok-panel:
    image: ngrok/ngrok:latest
    command: http client:5000
    environment:
      NGROK_AUTHTOKEN: ${NGROK_AUTHTOKEN:-}
    ports:
      - "4041:4040"
    profiles:
      - ngrok
```

E use a URL `https://<tunel-client>.ngrok-free.app/playlist.m3u` no XCIPTV.

## Multi-servidores

O painel separa o cadastro do video da localizacao fisica do HLS:

- **`MediaServer`** - representa uma engine de midia. Cada instancia tem `public_url`, `internal_url` opcional, `priority`, `weight` e `max_connections`.
- **`VideoLocation`** - associa um `Video` a um `MediaServer` com o `storage_path` do HLS (ex.: `filmes/film-a/master.m3u8`).

### Estrategias de selecao

Configuradas com `SERVER_SELECTION_STRATEGY`:

| Estrategia | Comportamento |
|---|---|
| `priority_fallback` (padrao) | Primarias primeiro, depois menor prioridade numerica |
| `primary_first` | Apenas localizacoes marcadas como primarias |
| `weighted_random` | Sorteio ponderado pelo campo `weight` |
| `lowest_connections` | Prefere o servidor com menor `current_connections` |

### JWT - HLS local

```json
{
  "client_id": "...",
  "video_id": 42,
  "server_id": 1,
  "storage_path": "filmes/film-a/master.m3u8",
  "exp": 1716000000
}
```

### JWT - Jellyfin

```json
{
  "client_id": "...",
  "video_id": 42,
  "provider": "jellyfin",
  "jellyfin_server_id": 1,
  "jellyfin_item_id": "abc123",
  "jellyfin_internal_url": "http://jellyfin:8096",
  "exp": 1716000000
}
```

### Layout de arquivos HLS

```
MEDIA_ROOT/
  hls/
    filmes/
      film-a/
        master.m3u8
        seg000.ts
        seg001.ts
```

`storage_path = filmes/film-a/master.m3u8` => arquivo real em `MEDIA_ROOT/hls/filmes/film-a/master.m3u8`.

A engine bloqueia caminhos absolutos, `..`, path traversal, barras invertidas e URLs externas.

## Subindo uma segunda VPS de midia

Uma VPS adicional nao precisa rodar o painel. Precisa apenas de:

1. Container ou binario `go-engine`
2. `nginx` como proxy reverso com TLS (ex.: `https://media-2.example.com`)
3. Pasta `/media/hls` com os segmentos HLS
4. As mesmas variaveis `JWT_SECRET` do painel e uma `ENGINE_API_KEY` propria

```bash
docker run -d --name go-engine \
  -e JWT_SECRET='mesmo-segredo-do-painel' \
  -e ENGINE_API_KEY='chave-da-vps-2' \
  -e MEDIA_ROOT=/media \
  -p 127.0.0.1:8080:8080 \
  -v /media:/media:ro \
  tribble_tv-go-engine:latest
```

No painel, cadastre um `MediaServer` com:

- `public_url`: `https://media-2.example.com`
- `internal_url`: `http://10.0.0.x:8080` (opcional, para health check interno)
- `api_key`: valor de `ENGINE_API_KEY` da VPS
- `priority`, `weight` e `max_connections` conforme a politica de balanceamento

Depois crie `VideoLocation` para cada video apontando para o `storage_path` existente na VPS.

## Stack

| Camada | Tecnologia |
|---|---|
| Painel | Python 3.12, Flask 3, Flask-SQLAlchemy, PyJWT |
| Engine | Go 1.22 (zero dependencias externas) |
| Banco | SQLite (padrao) |
| Container | Docker Compose v2 |
| Media server opcional | Jellyfin 10.x |

## Segurança

### Configuração de Secrets

Antes de colocar em produção, **é obrigatório** alterar os secrets padrão:

```bash
# Gerar SECRET_KEY forte
python -c "import secrets; print(secrets.token_hex(32))"

# Gerar JWT_SECRET forte
python -c "import secrets; print(secrets.token_hex(32))"

# Gerar ENGINE_API_KEY forte
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Atualize o `.env` com os valores gerados:

```env
SECRET_KEY=<valor-gerado-acima>
JWT_SECRET=<valor-gerado-acima>
ENGINE_API_KEY=<valor-gerado-acima>
```

### Checklist de Segurança Pós-Instalação

- [ ] Alterar todos os secrets padrão (SECRET_KEY, JWT_SECRET, ENGINE_API_KEY)
- [ ] Remover ou proteger o ngrok em produção (usar domínio próprio com HTTPS)
- [ ] Configurar firewall para restringir acesso ao painel admin
- [ ] Usar senhas fortes para usuários Xtream e Jellyfin
- [ ] Não commitar o arquivo `.env` (já está no .gitignore)
- [ ] Implementar rate limiting em produção
- [ ] Configurar backup automatizado do banco de dados
- [ ] Monitorar logs de segurança regularmente

### Boas Práticas

- **Nunca** exponha o `.env` em repositórios públicos
- **Sempre** use HTTPS em produção
- **Mantenha** as dependências atualizadas
- **Use** usuários dedicados para cada serviço (evite root)
- **Implemente** health checks para detectar falhas
- **Isole** redes Docker para reduzir superfície de ataque
- **Configure** limites de recursos para evitar DoS

### Melhorias de Segurança Planejadas

Para detalhes completos das melhorias de segurança planejadas, consulte:
- `plans/plan_seguranca/implementation_seguranca_plan.md` - Plano de implementação
- `plans/plan_seguranca/tasks_seguranca_plan.md` - Lista de tarefas detalhada

Principais melhorias:
- Multi-stage build no Dockerfile
- Usuário não-root nos containers
- Health checks em todos os serviços
- Redes Docker isoladas
- Rate limiting global
- Proteção CSRF
- Auditoria de acessos
- Centralização de logs
