# Torrent Indexer

Indexer de torrents próprio, embutido no painel (sem container ou serviço externo).
Código em `backend/services/torrent_index/`, fachada em `backend/services/torrent_indexer_service.py`.

```
Painel admin -> /admin/torrent-indexer -> Engine -> fontes (config/torrent_sources.json)
                        |                              |
                        |                              +-> magnet + seeds/leech (scrape UDP BEP 15)
                        +-> "Importar" -> /admin/videos/torrent/create (magnet pré-preenchido)
                                                 |
                                                 +-> torrent-node (WebTorrent) faz o streaming
```

## Módulos

| Módulo | Função |
|---|---|
| `magnet.py` | parse/build de magnets (hex e base32), extração de magnets de HTML |
| `trackers.py` | scrape de seeds/leechers em trackers UDP (BEP 15) |
| `text.py` | normalização (acentos, pontuação), pontuação de relevância, ano, qualidade, tamanho |
| `sources.py` | leitura e validação das fontes em JSON |
| `engine.py` | busca paralela, resolução de magnets, deduplicação por info_hash, ranking |

## Fontes

O projeto **não traz fontes prontas**: o indexer fica inativo até você criar
`config/torrent_sources.json` (ou apontar `TORRENT_SOURCES_FILE`). Escolha apenas
fontes que você tem direito de consultar.

```json
{
  "sources": [
    {
      "id": "meusite",
      "name": "Meu Site",
      "type": "html",
      "search_url": "https://exemplo.test/busca?q={query}",
      "item_pattern": "<a href=\"(?P<url>/t/[^\"]+)\"[^>]*>(?P<title>[^<]+)</a>",
      "fetch_detail": true
    },
    {
      "id": "minhaapi",
      "name": "Minha API",
      "type": "json",
      "search_url": "https://api.exemplo.test/s?q={query}",
      "results_path": "data.items",
      "fields": {"title": "name", "info_hash": "hash", "seeds": "seeders", "leech": "leechers", "size": "size"}
    }
  ]
}
```

- `id`: slug `[a-z0-9_-]`, único. `search_url` deve ser http(s) e conter `{query}`.
- **html**: `item_pattern` é uma regex com grupos nomeados `title` e `url` ou `magnet`
  (opcionais: `size`, `seeds`, `leech`, `year`). Com `url`, a página de detalhe é aberta
  (até 10 por busca) e o primeiro magnet dela é usado; `fetch_detail: false` desativa isso.
- **json**: `results_path` com pontos até a lista e `fields` mapeando `title`, `magnet` ou
  `info_hash`, e opcionalmente `size`, `seeds`, `leech`, `url`, `year`.
- `enabled: false` desliga uma fonte; `headers` adiciona cabeçalhos HTTP.
- Fonte inválida faz a busca falhar com mensagem explicando o erro de configuração.

## Variáveis

| Variável | Padrão | Descrição |
|---|---|---|
| `TORRENT_SOURCES_FILE` | `config/torrent_sources.json` | Caminho do JSON de fontes |
| `TORRENT_INDEXER_TIMEOUT_SECONDS` | `15` | Timeout HTTP por requisição |
| `TORRENT_INDEXER_TRACKER_SCRAPE` | `1` | `0` desliga o scrape UDP de seeds/leechers |

## Comportamento da busca

- Resultados cujo título contém menos da metade dos termos buscados são descartados.
- Magnets repetidos (mesmo info_hash) são unidos, ficando o de mais seeds.
- Seeds ausentes são consultados nos trackers `udp://` do próprio magnet (até 3 por item).
- Ordenação: relevância do título, depois seeds. Falhas por fonte vão em `errors`, sem
  derrubar as demais.

## Uso no painel

1. Menu **Vídeos > Torrent Indexer**.
2. Busque por título (todas as fontes ou uma).
3. **Importar** abre o formulário de vídeo torrent com título e magnet preenchidos.

Rotas: `GET /admin/torrent-indexer` e `GET /admin/torrent-indexer/search?q=&indexer=&limit=`.

## Responsabilidade

Use apenas com conteúdo que você tem direito de distribuir ou assistir. As fontes
configuradas são de terceiros e este projeto não as controla.
