# Tasks — Torrent Streaming

## Status: Concluído

- [x] Criar plano de implementação
- [x] Microserviço torrent-node (Node.js + Express + webtorrent)
  - [x] `torrent-service/package.json`
  - [x] `torrent-service/server.js`
  - [x] `torrent-service/Dockerfile`
- [x] `backend/services/torrent_service.py` — proxy Python
- [x] Rotas Flask cliente: `/torrent/stream/<id>`, `/torrent/info/<id>`, `/torrent/status`
- [x] Admin CRUD: `videos/torrent/create`, `edit`, `delete`
- [x] Admin API: `/torrent-node/status`, `/torrent-node/remove`
- [x] Template `admin/videos/torrent_form.html`
- [x] `admin/videos/index.html` — badge torrent + botão "Novo Torrent" + ações
- [x] `client/player.html` — badge BitTorrent, overlay de buffering, peer polling, src direto
- [x] `backend/routes/client.py` — player torrent usa `url_for('client.torrent_stream')`, filtro `provider=torrent`
- [x] `docker-compose.yml` — serviço torrent-node + volume torrent-cache + TORRENT_NODE_URL
- [x] `migrations/add_torrent_support.sql` — índice source_type=torrent
- [x] Atualizar `README.md` — seção Torrent Streaming completa
