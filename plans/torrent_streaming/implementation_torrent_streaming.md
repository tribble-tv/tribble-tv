# Plano de Implementação — Streaming via Torrent

## Objetivo

Adicionar suporte a streaming de vídeos via protocolo BitTorrent usando **WebTorrent** como sidecar Node.js, integrado ao painel Flask existente.

## Arquitetura

```
Cliente → Flask :5000/torrent/stream/<video_id>
              ↓ proxy HTTP range requests
         torrent-node :9119/stream?magnet=<magnet_link>
              ↓
         WebTorrent (BitTorrent + WebRTC peers)
```

- `source_type = "torrent"` no modelo `Video`
- `source_url` armazena o magnet link ou URL do `.torrent`
- Microserviço `torrent-service` (Node.js + Express + webtorrent) no Docker Compose
- Flask faz proxy transparente com suporte a `Range` headers (seek funciona)
- Player HTML5 nativo com fallback para HLS player existente

## Componentes

| Componente | Arquivo | Descrição |
|---|---|---|
| Microserviço Node.js | `torrent-service/` | Express + webtorrent, porta 9119 |
| Migration DB | `migrations/add_torrent_support.sql` | Nenhuma coluna nova necessária (source_url já existe) |
| Serviço Python | `backend/services/torrent_service.py` | Proxy e integração com torrent-node |
| Rotas cliente | `backend/routes/client.py` | `/torrent/stream/<id>`, `/torrent/info/<id>` |
| Rotas admin | `backend/routes/admin.py` | Cadastro de vídeos torrent |
| Docker Compose | `docker-compose.yml` | Serviço `torrent-node` |

## Impacto em Documentação

- `README.md`: Atualizar tabela de `source_type`, serviços e rotas
- `CHANGELOG.md`: Entrada da feature

## Riscos

- Torrents com poucos seeds podem ter alta latência inicial de buffering
- Conteúdo legal somente — a plataforma não valida o conteúdo dos magnets
