# Implementation Plan: Balanceamento de Carga + Live/VOD Streaming

## 1. Visão Geral

Implementar arquitetura de balanceamento de carga entre múltiplos servidores de streaming e suporte para transmissão ao vivo (Live) e sob demanda (VOD).

## 2. Arquitetura Proposta

### 2.1 Componentes

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│   Cliente       │────▶│  Load Balancer   │────▶│  Go-Engine 1    │
│  (XCIPTV/VLC)   │     │  (Round Robin/   │     │  (Streaming)    │
└─────────────────┘     │  Least Conns)    │────▶├─────────────────┤
                        │                  │     │  Go-Engine 2    │
                        │  + Health Check  │────▶│  (Streaming)    │
                        └──────────────────┘     ├─────────────────┤
                                                   │  Go-Engine N    │
                                                   └─────────────────┘
```

### 2.2 Fluxo Live Streaming

```
┌──────────────┐    ┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│  Fonte Live  │───▶│  RTMP/HLS    │───▶│  Go-Engine   │───▶│  Clientes    │
│  (OBS/FFmpeg)│    │  Ingest      │    │  (Distribui) │    │  ( viewers)  │
└──────────────┘    └──────────────┘    └──────────────┘    └──────────────┘
```

## 3. Estrutura de Dados

### 3.1 Novo Modelo: StreamingServer
```python
- id: Integer (PK)
- name: String(100)
- host: String(255) - IP/hostname
- port: Integer (default 8080)
- protocol: String(10) - http/https
- is_active: Boolean
- max_connections: Integer
- current_connections: Integer
- priority: Integer (para weighted round robin)
- region: String(50) - para geo-routing
- health_status: String(20) - healthy/unreachable/maintenance
- last_health_check: DateTime
- created_at: DateTime
```

### 3.2 Novo Modelo: LiveStream
```python
- id: Integer (PK)
- name: String(200)
- stream_key: String(100) - único para ingest
- status: Enum - offline/starting/live/ended
- server_id: FK → StreamingServer
- started_at: DateTime
- ended_at: DateTime
- viewer_count: Integer
- ingest_url: String(500) - RTMP endpoint
- playback_url: String(500) - HLS endpoint
```

### 3.3 Novo Modelo: Connection
```python
- id: Integer (PK)
- client_id: String(100)
- server_id: FK → StreamingServer
- video_id: Integer (para VOD)
- live_stream_id: Integer (para Live)
- started_at: DateTime
- bytes_transferred: BigInteger
- user_agent: String(255)
- ip_address: String(45)
```

## 4. Algoritmos de Balanceamento

### 4.1 Round Robin Simples
```python
servers = get_active_servers()
next_server = servers[connection_count % len(servers)]
```

### 4.2 Weighted Round Robin
```python
# Baseado em capacity/priority de cada servidor
weights = [s.priority for s in servers]
total_weight = sum(weights)
# Seleciona proporcionalmente ao peso
```

### 4.3 Least Connections
```python
# Direciona para servidor com menos conexões ativas
server = min(servers, key=lambda s: s.current_connections)
```

### 4.4 Health Check
- Ping a cada 30 segundos
- HTTP GET `/health` espera 200
- Timeout de 5 segundos
- 3 falhas consecutivas = servidor marcado como unhealthy

## 5. Endpoints API

### 5.1 Administração
| Endpoint | Descrição |
|----------|-----------|
| `POST /admin/streaming-servers` | Adicionar servidor |
| `GET /admin/streaming-servers` | Listar servidores |
| `POST /admin/streaming-servers/:id/health` | Health check manual |
| `POST /admin/live-streams` | Criar stream live |
| `GET /admin/live-streams` | Listar streams |
| `POST /admin/live-streams/:id/start` | Iniciar transmissão |
| `POST /admin/live-streams/:id/stop` | Parar transmissão |

### 5.2 Streaming
| Endpoint | Descrição |
|----------|-----------|
| `GET /live/:stream_key/playlist.m3u8` | Playlist HLS live |
| `GET /live/:stream_key/:segment.ts` | Segmento TS live |
| `POST /ingest/:stream_key` | Ingest RTMP/WebRTC |
| `GET /vod/:video_id/playlist.m3u8` | Playlist HLS VOD |
| `GET /stats/connections` | Métricas de conexões |

## 6. Implementação Go-Engine

### 6.1 Modificações no main.go
- Adicionar suporte a RTMP ingest
- Proxy para live streams
- Métricas de conexões em tempo real
- Health check endpoint

### 6.2 Estrutura
```go
type LoadBalancer struct {
    servers []Server
    current int
    mu sync.RWMutex
}

func (lb *LoadBalancer) GetServer(strategy string) *Server
func (lb *LoadBalancer) HealthCheck()
func (lb *LoadBalancer) UpdateMetrics()
```

## 7. Dashboard de Monitoramento

### 7.1 Métricas em Tempo Real
- Conexões ativas por servidor
- Bandwidth por servidor
- Latência média
- Taxa de erro

### 7.2 Visualização
- Mapa de servidores
- Gráficos de load
- Alertas de saúde

## 8. Tarefas

### Fase 1: Backend Database
- [ ] Criar modelos `StreamingServer`, `LiveStream`, `Connection`
- [ ] Migrations para novas tabelas
- [ ] Seed de servidores padrão

### Fase 2: Load Balancer Service
- [ ] Implementar `load_balancer_service.py`
- [ ] Algoritmos: Round Robin, Weighted, Least Connections
- [ ] Health check automático

### Fase 3: Go-Engine Modificações
- [ ] Adicionar endpoint `/health`
- [ ] Métricas de conexões
- [ ] Suporte a proxy de live streams

### Fase 4: Admin Interface
- [ ] CRUD de servidores de streaming
- [ ] CRUD de streams live
- [ ] Dashboard de métricas
- [ ] Visualização de conexões ativas

### Fase 5: Live Streaming
- [ ] Endpoint de ingest RTMP
- [ ] Endpoint de playback HLS
- [ ] Gestão de stream keys
- [ ] Transcodificação (opcional)

### Fase 6: Testes e Documentação
- [ ] Testes de carga
- [ ] Documentação de API
- [ ] README de configuração
