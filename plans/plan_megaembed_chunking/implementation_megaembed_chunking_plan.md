# Plano de Implementação - Importação em Partes do MegaEmbed

## Contexto

A importação em massa de séries via `MegaEmbed -> TMDB` pode envolver centenas de séries
e milhares de episódios. O fluxo atual roda tudo de uma vez em uma thread, fazendo a UI
ficar "carregando infinitamente" e gerando muitas requisições seguidas para
`mgeb.top` e `api.themoviedb.org`, aumentando o risco de banimento.

## Objetivos

- Processar a fila de séries em **lotes (chunks) configuráveis**.
- Permitir **offset / continuar de onde parou** sem reimportar tudo.
- Exibir **progresso em tempo real** (séries processadas, total, etapa atual).
- Adicionar **atraso configurável entre requisições** TMDB / MegaEmbed.
- Manter compatibilidade com o fluxo atual de filmes.

## Mudanças

### `backend/services/megaembed_service.py`
- Adicionar parâmetros em `import_available_ids`:
  - `series_offset` (int, default 0)
  - `series_limit` (int|None, default None = todos)
  - `request_delay` (float, default 0.5s) - aplicado em chamadas TMDB reais (sem cache)
  - `progress_callback` (callable opcional) - recebe um dict de progresso a cada série/temporada
- Fatiar a lista de séries com `series_offset:series_offset+series_limit`.
- Incluir no `stats`: `series_offset`, `series_limit`, `series_total_available`,
  `series_processed`, `next_offset`, `has_more`.
- Em `_request_tmdb_json`, opcionalmente aplicar `time.sleep(request_delay)` quando o
  caller solicitar (passar via parâmetro `delay`).
- Encaminhar `request_delay` e `progress_callback` para `_import_series_episode_batch`.

### `backend/routes/admin.py`
- `megaembed_run`: aceitar campos do form `chunk_size`, `chunk_offset`, `request_delay`.
- Job worker mantém `progress` no `_megaembed_jobs[job_id]` e atualiza via callback.
- `megaembed_status` retorna também `progress`.

### `backend/templates/admin/megaembed/index.html`
- Novos campos no form de bulk import: tamanho do lote, offset inicial, atraso (s).
- Exibir barra de progresso (X/Y séries) e a série atual.
- Quando `has_more=true` ao terminar, mostrar botão "Continuar do índice N".

### Documentação
- Atualizar `README.md` (seção MegaEmbed / Roadmap) com as novas opções de chunking.

## Impacto

- Diretório `plans/plan_megaembed_chunking/` criado para artefatos.
- Sem migração de banco; mudanças apenas em serviço, rota e template.
- Cache TMDB existente continua sendo aproveitado entre lotes.
