# Plano de Implementação — Suporte a Embed Externo (redecanais.ph)

## Contexto

O sistema Tribble TV suporta HLS local (go-engine) e Jellyfin. Foi solicitada a integração com embeds externos, cujo modelo foi estudado a partir do site **redecanais.ph**.

### Como funciona o embed do redecanais.ph

- URL de exemplo: `https://redecanaistv.ph/player3/embed.api?embed=BASE64`
- O valor base64 decodifica para: `player3/ch.php?canal=ID_DO_CANAL`
- O iframe final renderizado: `//redecanaistv.ph/player3/ch.php?canal=ID_DO_CANAL`
- Padrão: `{base}/player3/ch.php?canal={canal_id}`
- Atributos do iframe: `frameborder="0"`, `scrolling="no"`, `allow="encrypted-media"`, `allowfullscreen`

---

## Mudanças Propostas

### 1. `source_type = "embed"` no modelo Video
- Campo `source_url` (já existente no modelo) armazena a URL do iframe src
- Campo `external_provider = "embed"` para identificação

### 2. `server_selector.py`
- Nova função `_build_embed_url(video)` que retorna `video.source_url` diretamente
- Sem JWT, sem go-engine, sem VideoLocation

### 3. `routes/client.py`
- `/client/player/<video_id>`: passa `is_embed=True` ao template
- `/play/<video_id>`: se embed, redireciona para página do player (não para a URL direta)

### 4. `templates/client/player.html`
- Renderiza `<iframe>` quando `is_embed=True`
- Renderiza `<video>` com HLS.js quando não é embed
- Badge `badge-warning` para embed

### 5. `routes/admin.py`
- `GET/POST /admin/videos/embed/create` — criar vídeo embed
- `GET/POST /admin/videos/embed/<id>/edit` — editar
- `POST /admin/videos/embed/<id>/delete` — deletar

### 6. `templates/admin/videos/embed_form.html` (novo)
- Formulário com título e URL do embed
- Instrução de como obter a URL do redecanais.ph

### 7. `templates/admin/videos/index.html`
- Botão "Novo Embed" no page-header
- Badge amarelo para embeds
- Ações de editar e remover para vídeos embed

### 8. `app.py`
- Migração SQLite para garantir coluna `source_url` em deployments existentes

### 9. `templates/base.html`
- Adicionado `.badge-warning` (fundo amarelo)

---

## Arquivos Modificados

| Arquivo | Tipo de alteração |
|---|---|
| `backend/services/server_selector.py` | Adição |
| `backend/routes/client.py` | Modificação |
| `backend/routes/admin.py` | Adição de rotas |
| `backend/templates/client/player.html` | Modificação |
| `backend/templates/admin/videos/index.html` | Modificação |
| `backend/templates/admin/videos/embed_form.html` | Novo arquivo |
| `backend/templates/base.html` | Adição de estilo |
| `backend/app.py` | Migração SQLite |
