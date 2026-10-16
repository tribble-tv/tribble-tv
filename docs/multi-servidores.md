# Porgs TV

Painel central e engine HLS para distribuição de vídeos com suporte a múltiplos servidores de mídia.

## Desenvolvimento local

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
flask --app backend.app:app run
```

Com Docker:

```bash
docker compose up --build
```

O `docker-compose.yml` sobe dois serviços:

- `panel`: painel Flask central com modelos SQLAlchemy, rotas admin e player do cliente.
- `go-engine`: engine local de HLS que valida JWTs e serve arquivos em `MEDIA_ROOT/hls`.

## Multi-servidores

O suporte a multi-servidores separa o cadastro do vídeo do local físico do HLS:

- `MediaServer` representa uma engine de mídia com URL pública, URL interna, região, provider, chave de API, prioridade, peso, limite de conexões e status de saúde.
- `VideoLocation` liga um vídeo a um servidor e informa o `storage_path` do HLS, por exemplo `joao-maria/master.m3u8`.
- A geração de link não usa mais `Video.source_url` diretamente. O painel seleciona uma localização ativa em servidor ativo e cria uma URL assinada no formato `{server.public_url}/hls/{token}/{video_id}/master.m3u8`.

Registros `MediaServer` com `server_type=panel` aparecem no inventario de infraestrutura, mas nao entram no seletor de `VideoLocation` nem geram links HLS.

### Seed de infraestrutura

Cadastre painel e engine no boot com listas separadas por virgula:

```bash
PANEL_PUBLIC_URL=https://painel.example.com
ENGINE_PUBLIC_URL=https://stream.example.com
MEDIA_SERVER_SEED_NAMES=panel admin,go-engine stream
MEDIA_SERVER_SEED_TYPES=panel,go-engine
MEDIA_SERVER_SEED_PUBLIC_URLS=https://painel.example.com,https://stream.example.com
MEDIA_SERVER_SEED_INTERNAL_URLS=http://panel:5000,http://go-engine:8080
MEDIA_SERVER_SEED_API_KEYS=,dev-engine-key
MEDIA_SERVER_SEED_PRIORITIES=10,100
```

As variaveis legadas `MEDIA_SEED_*` continuam aceitas como fallback.

### Estratégias de seleção

O serviço `backend/services/server_selector.py` implementa:

- `primary_first`: prefere localizações marcadas como primárias.
- `priority_fallback`: estratégia padrão; ordena por primária, menor prioridade e fallback determinístico.
- `weighted_random`: escolhe por peso entre os servidores elegíveis.
- `lowest_connections`: prefere o servidor com menor número de conexões atuais.

Configure a estratégia com:

```bash
SERVER_SELECTION_STRATEGY=priority_fallback
```

### URLs e JWT

O JWT emitido pelo painel contém:

- `client_id`
- `video_id`
- `server_id`
- `storage_path`
- `exp`

A engine Go expõe:

- `GET /hls/{token}/{video_id}/master.m3u8`
- `GET /hls/{token}/{video_id}/{segment}`
- `GET /health`

O endpoint `/health` exige o header `X-API-Key` e compara com `ENGINE_API_KEY`.

### Layout de arquivos HLS

Para HLS local, a engine sempre resolve arquivos dentro de:

```text
MEDIA_ROOT/hls/{storage_path}
```

Exemplo:

```text
storage_path: joao-maria/master.m3u8
arquivo real: MEDIA_ROOT/hls/joao-maria/master.m3u8
```

A engine bloqueia caminhos absolutos, `..`, path traversal, barras invertidas e URLs externas no MVP. Ao reescrever playlists, comentários `#EXT` são preservados e segmentos relativos passam a apontar para `/hls/{token}/{video_id}/{segment}`.

### Subindo uma segunda VPS de mídia

Uma VPS adicional não precisa rodar o painel central. Ela precisa apenas de:

1. Binário/container `go-engine`.
2. `nginx` como proxy reverso com TLS e domínio próprio, por exemplo `https://media-2.example.com`.
3. Pasta `/media/hls` contendo os HLS segmentados.
4. As mesmas variáveis `JWT_SECRET` do painel e uma `ENGINE_API_KEY` própria.

Exemplo de execução da engine na VPS:

```bash
docker run -d --name porgs-go-engine \
  -e JWT_SECRET='mesmo-segredo-do-painel' \
  -e ENGINE_API_KEY='chave-da-vps-2' \
  -e MEDIA_ROOT=/media \
  -p 127.0.0.1:8080:8080 \
  -v /media:/media:ro \
  porgs-tv/go-engine:latest
```

No painel, cadastre um `MediaServer` com:

- `public_url`: domínio público servido pelo nginx, como `https://media-2.example.com`.
- `internal_url`: URL interna opcional para health check, como `http://10.0.0.x:8080`.
- `api_key`: valor de `ENGINE_API_KEY` da VPS.
- `priority`, `weight` e `max_connections` conforme a política de fallback e balanceamento.

Depois, crie `VideoLocation` para cada vídeo apontando para o `storage_path` existente na VPS.
