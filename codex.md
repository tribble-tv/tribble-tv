Implemente suporte a multi-servidores de mídia.

Crie os modelos SQLAlchemy:

MediaServer:
- id
- name
- public_url
- internal_url
- region
- provider
- server_type
- api_key
- priority
- weight
- max_connections
- current_connections
- is_active
- health_status
- last_health_check
- created_at

VideoLocation:
- id
- video_id
- media_server_id
- storage_path
- source_type
- is_primary
- is_active
- created_at

Atualize Video para se relacionar com VideoLocation.

Crie rotas admin:
- /admin/media-servers
- /admin/media-servers/create
- /admin/media-servers/<id>/edit
- /admin/media-servers/<id>/health
- /admin/videos/<id>/locations
- /admin/videos/<id>/locations/create
- /admin/video-locations/<id>/edit
- /admin/video-locations/<id>/delete

Crie templates Jinja2 para essas telas.

Crie service:
backend/services/server_selector.py

Implemente estratégias:
- primary_first
- priority_fallback
- weighted_random
- lowest_connections

Use priority_fallback como padrão.

Ao gerar link de vídeo, não usar mais source_url diretamente.
Usar VideoLocation + MediaServer.

Fluxo:
1. Recebe video_id.
2. Busca locations ativas do vídeo.
3. Filtra servidores ativos.
4. Ordena por is_primary desc, priority asc.
5. Escolhe servidor.
6. Gera JWT com:
   client_id
   video_id
   server_id
   storage_path
   exp
7. Retorna:
   {server.public_url}/hls/{token}/{video_id}/master.m3u8

Atualize:
- playlist_service.py
- xtream_service.py
- client/player.html
- rota /client/player/<video_id>

Crie endpoint:
- /play/<video_id>

Esse endpoint deve verificar login do cliente e redirecionar para o melhor servidor.

Atualize a engine Go:

JWT claims:
- client_id
- video_id
- server_id
- storage_path
- exp

Endpoints:
- GET /hls/{token}/{video_id}/master.m3u8
- GET /hls/{token}/{video_id}/{segment}
- GET /health

O /health deve exigir header:
X-API-Key

A API key deve vir de variável:
ENGINE_API_KEY

O storage_path deve ser usado para localizar o master.m3u8.
Não permitir:
- ..
- caminhos absolutos
- path traversal
- URLs externas não autorizadas no MVP

Para HLS local:
MEDIA_ROOT/hls/{storage_path}

Se storage_path for:
joao-maria/master.m3u8

Então arquivo real:
MEDIA_ROOT/hls/joao-maria/master.m3u8

Ao reescrever playlist:
- preservar comentários #EXT
- reescrever segmentos relativos para:
  /hls/{token}/{video_id}/{segment}

Atualize docker-compose para permitir rodar:
- painel central
- engine local

Atualize README com seção:
Multi-servidores

Explique como subir uma segunda VPS apenas com:
- go-engine
- nginx
- pasta /media/hls
- domínio próprio