# Integracao MegaEmbed

MegaEmbed entra no Tribble TV como video `source_type="embed"`, usando iframe no player web existente.

## Admin

Acesse `/admin/megaembed` para cadastrar um item por ID externo:

- Filme dublado por TMDB ou IMDB: `https://mgeb.top/embed/{id}`
- Serie dublada por TMDB ou IMDB: `https://mgeb.top/embed/{id}/{temporada}/{episodio}`
- Filme legendado por TMDB: `https://nhdapi.com/embed/movie/{tmdbId}`
- Serie legendada por TMDB: `https://nhdapi.com/embed/tv/{tmdbId}/{temporada}/{episodio}`

O cadastro cria ou atualiza um `Video` com:

- `source_type="embed"`
- `external_provider="megaembed"`
- `source_url` igual a URL gerada

Na mesma tela, a acao `Importar todos da API JSON` busca:

- `https://mgeb.top/api/movie`
- `https://mgeb.top/api/series`

Esses endpoints retornam listas de TMDB IDs. Filmes sao importados como embeds dublados de filme. Series sao expandidas pelo TMDB: o painel consulta os detalhes da serie, ignora especiais (`season_number=0`), busca cada temporada regular e cria um video por episodio usando `https://mgeb.top/embed/{tmdb_id}/{temporada}/{episodio}`.

Se `TMDB_API_KEY` ou `TMDB_BEARER_TOKEN` estiver configurado no ambiente do `panel`, a importacao consulta o TMDB e troca titulos genericos como `MegaEmbed Filme 11886` pelo nome real da midia. Quando houver poster no TMDB, `thumbnail_url` tambem e preenchido.

Para evitar excesso de chamadas ao TMDB, detalhes de filmes, series e temporadas sao salvos em cache JSON. Por padrao:

- `TMDB_CACHE_PATH=/data/tmdb_cache.json`
- `TMDB_CACHE_TTL_SECONDS=2592000` (30 dias)

O caminho `/data` fica no volume persistente `panel-data` do Docker Compose.

## Player

`/client/player/<video_id>` renderiza embeds diretamente pelo `source_url`, sem tentar gerar URL HLS assinada no go-engine.

## Observacao Xtream/M3U

Players Xtream/IPTV geralmente esperam stream direto. Para MegaEmbed, a URL exportada e a propria URL de embed, entao o uso principal e pelo player web do painel.
