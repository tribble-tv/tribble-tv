# ReidosCanais API e Xtream Live Streams

## Objetivo

Registrar o trabalho feito para integrar a API do ReidosCanais ao painel e tratar seus itens como Live Streams nas plataformas Xtream, com foco em converter `embed_url` para stream direto sempre que a origem disponibilizar um HLS valido.

## Implementado

- Criada uma area administrativa nova e separada para ReidosCanais API em `/admin/reidoscanais`.
- Mantido o scraper antigo de redecanais separado, sem substitui-lo.
- Criado o servico `backend/services/reidoscanais_api_service.py` para consumir `https://api.reidoscanais.ooo` com headers de navegador.
- Adicionadas rotas administrativas:
  - `GET /admin/reidoscanais`
  - `POST /admin/reidoscanais/fetch`
  - `POST /admin/reidoscanais/import`
  - `POST /admin/reidoscanais/convert`
- Adicionado item de menu `ReidosCanais API`.
- A importacao agora tenta converter `embed_url` para uma URL direta `.m3u8` antes de salvar.
- Itens ReidosCanais sem stream direto valido sao ignorados na importacao, evitando cadastrar Live Streams quebrados.
- Adicionada acao para converter registros ReidosCanais ja existentes no banco para stream direto quando possivel.
- ReidosCanais passou a ser tratado como Live Stream no Xtream:
  - `action=get_live_categories`
  - `action=get_live_streams`
  - `action=get_live_info`
  - rota `/live/<username>/<password>/<stream_id>.m3u8`
- ReidosCanais foi removido defensivamente do VOD:
  - nao aparece em `get_vod_streams`
  - `get_vod_info` retorna `404` para esses IDs.
- `go-engine` passou a encaminhar `/live/` para o painel.

## Conversao de Embed Para Stream Direto

O resolvedor tenta:

1. Detectar se a propria URL ja e `.m3u8`.
2. Baixar o HTML da `embed_url` com headers de navegador.
3. Procurar iframes ou referencias contendo `.m3u8`.
4. Validar se a URL encontrada responde com uma playlist HLS (`#EXTM3U`).
5. Salvar somente o stream direto validado.

Se a pagina ReidosCanais possuir apenas embed HTML ou apontar para uma playlist morta, o item nao e salvo como Live Stream direto.

## Observacao Sobre a Imagem do Erro

No caso mostrado do Smart IPTV, o canal era listado como Live Stream, mas a reproducao falhava porque a URL cadastrada era uma pagina HTML (`https://rdcanais.com/...`) e nao um stream HLS direto.

Exemplo inspecionado:

- `https://rdcanais.com/cnnbrasil` retornava HTML com iframe.
- Dentro do HTML foi encontrada uma referencia para `.m3u8`.
- A URL HLS encontrada retornou `404` no teste feito dentro do container.

Por isso, apenas listar a `embed_url` como Live Stream nao resolve; e necessario converter e validar a playlist direta.

## Validacoes Feitas

- `python -m py_compile` nos arquivos alterados.
- Rebuild/recreate do `panel` e `go-engine` via Docker Compose.
- Validado que `/health` do painel responde `200`.
- Teste controlado confirmou que a importacao salva a URL direta resolvida, nao a `embed_url`.
- Testado que ReidosCanais entra no fluxo Xtream Live e sai do fluxo VOD.

## Pontos de Atencao

- A conversao em massa dos registros reais foi iniciada, mas foi interrompida manualmente antes de concluir.
- Algumas fontes do ReidosCanais podem nao expor HLS valido no momento da importacao.
- O sistema agora deve preferir nao importar itens sem stream direto valido, em vez de cadastrar canais que aparecem no player mas falham ao tocar.
- Existem mudancas paralelas relacionadas a YouTube no workspace; foi adicionada protecao para o seed YouTube nao derrubar o boot quando a tabela ainda nao existir.

## Proximo Passo Recomendado

Rodar novamente a conversao dos registros existentes pelo botao `Converter existentes` em `/admin/reidoscanais`, ou via servico, e depois conferir quantos itens foram convertidos, ignorados ou permaneceram sem stream direto valido.
