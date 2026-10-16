# Integração Jellyfin

A integração permite usar Jellyfin como servidor de mídia, biblioteca e origem de vídeos no wedding-iptv/Porgs TV. O painel sincroniza bibliotecas e itens do Jellyfin, vincula itens a registros `Video` e entrega streams via proxy assinado na engine Go.

## Serviços Docker

Suba todos os serviços com:

```bash
docker compose up --build
```

Serviços principais:

- `panel`: painel Flask em `http://localhost:5000`.
- `go-engine`: proxy de streaming em `http://localhost:8080`.
- `jellyfin`: servidor Jellyfin em `http://localhost:8096`.

## Variáveis de ambiente

- `JWT_SECRET`: segredo compartilhado entre painel e engine para validar tokens de streaming.
- `STREAM_PUBLIC_URL`: URL pública da engine usada pelo painel ao gerar links, por exemplo `https://stream.example.com`.
- `JELLYFIN_ALLOWED_INTERNAL_URLS`: lista separada por vírgulas de URLs internas Jellyfin permitidas pela engine, por exemplo `http://jellyfin:8096`.
- `JELLYFIN_API_KEYS`: mapa opcional de API keys para a engine autenticar chamadas internas ao Jellyfin. Aceita entradas separadas por vírgula no formato `server_id=api_key` ou `internal_url=api_key`.
- `RATE_LIMIT_REQUESTS`: limite por minuto aplicado pela engine ao proxy Jellyfin.

## Cadastro do servidor Jellyfin

1. Suba o Jellyfin com `docker compose up jellyfin` ou use um servidor Jellyfin externo.
2. No Jellyfin, gere uma API key administrativa.
3. Acesse `/admin/jellyfin-servers/create` no painel.
4. Preencha:
   - `base_url`: URL pública do Jellyfin usada para abrir a interface web.
   - `internal_url`: URL interna usada pelo painel/engine para acessar o Jellyfin, por exemplo `http://jellyfin:8096`.
   - `api_key`: chave Jellyfin usada apenas no backend com header `X-Emby-Token`.
5. Execute `Health` para validar `/System/Info`.

> A API key do Jellyfin nunca deve ser renderizada em listagens nem enviada ao frontend. O backend usa `X-Emby-Token` e a engine recebe chaves apenas por variável de ambiente quando precisa autenticar o proxy interno.

## Sincronização

Na tela `/admin/jellyfin-servers`:

1. Clique em `Sync bibliotecas` para importar bibliotecas do Jellyfin.
2. Clique em `Sync itens` para importar filmes/vídeos/episódios das bibliotecas ativas.
3. Acesse `/admin/jellyfin-items` para ver os itens sincronizados.
4. Use `Vincular vídeo` para associar um `JellyfinItem` a um `Video` existente.

Ao vincular, o vídeo passa a ter:

- `source_type = "jellyfin"`
- `external_provider = "jellyfin"`
- `jellyfin_server_id`
- `jellyfin_item_id`

## Reprodução

Para vídeos Jellyfin, o painel gera URLs assinadas pelo proxy Go:

```text
{STREAM_PUBLIC_URL}/jellyfin/{token}/{jellyfin_item_id}/master.m3u8
```

O JWT contém:

- `client_id`
- `video_id`
- `provider = "jellyfin"`
- `jellyfin_server_id`
- `jellyfin_item_id`
- `jellyfin_internal_url`
- `exp`

A engine Go valida assinatura, expiração, provider, item, rate limit e allowlist de URLs internas antes de consultar o Jellyfin. Playlists HLS retornadas pelo Jellyfin são reescritas para que segmentos também passem pelo proxy:

```text
/jellyfin/{token}/{item_id}/{segment}
```

## Abrir item no Jellyfin

Clientes autenticados podem abrir a página do item no Jellyfin pelo endpoint:

```text
GET /open-jellyfin/<video_id>
```

O endpoint valida o cliente, confirma que o vídeo é Jellyfin e redireciona para:

```text
{jellyfin_server.base_url}/web/index.html#!/details?id={jellyfin_item_id}
```

## M3U e Xtream Codes

Vídeos Jellyfin são incluídos nas playlists M3U com `#EXTINF` e URL proxy assinada. Nas funções Xtream Codes, vídeos Jellyfin aparecem em:

- `get_vod_categories`
- `get_vod_streams`
- `get_vod_info`

A categoria Jellyfin é gerada quando há vídeos com `source_type` ou `external_provider` igual a `jellyfin`.

## Multi-servidores HLS

O fluxo HLS existente continua disponível. Cada `VideoLocation` aponta para um `MediaServer` e para um `storage_path`. Ao reproduzir, o painel seleciona uma localização ativa por estratégia e gera:

```text
{server.public_url}/hls/{token}/{video_id}/master.m3u8
```

A engine lê os arquivos em:

```text
MEDIA_ROOT/hls/{storage_path}
```

A engine bloqueia caminhos absolutos, `..`, path traversal, barras invertidas e URLs externas no fluxo HLS local.
