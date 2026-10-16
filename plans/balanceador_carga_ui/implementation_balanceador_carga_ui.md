# Implementation Plan: Configuração Visual do Balanceador de Carga

## Objetivo

Adicionar uma página de administração visual em `/admin/load-balancer` para configurar a estratégia de balanceamento de carga atualmente usada pelo `server_selector` (HLS/VOD) e pelo `LoadBalancerService` (live streaming), substituindo a configuração apenas por variável de ambiente.

## Contexto Atual

- `backend/services/server_selector.py` define 4 estratégias (`primary_first`, `priority_fallback`, `weighted_random`, `lowest_connections`) usadas em `playlist_service.build_video_playback_url`.
- `backend/services/load_balancer_service.py` define 5 estratégias (`round_robin`, `weighted`, `least_connections`, `random`, `health_based`) para `StreamingServer` (live).
- Ambas só podem ser alteradas via `SERVER_SELECTION_STRATEGY` env var; não há UI.

## Escopo

1. **Modelo `AppSetting`**: tabela simples `app_settings (key, value, updated_at)` em SQLite/Postgres.
2. **Service `settings_service`**: helpers `get_setting(key, default)` e `set_setting(key, value)`.
3. **Schema bootstrap**: criar a tabela em `_ensure_lightweight_schema_updates` em `backend/app.py`.
4. **Rota admin**: `GET/POST /admin/load-balancer` em `backend/routes/admin.py` com formulário visual.
5. **Template**: `backend/templates/admin/load_balancer/index.html` com cards de cada estratégia (radio + descrição + ícone).
6. **Integração**:
   - `playlist_service.build_video_playback_url` lê a estratégia VOD do `AppSetting` antes de cair no env/default.
   - `LoadBalancerService` exposto via `get_load_balancer()` lê estratégia Live do `AppSetting`.
7. **Sidebar/UI**: adicionar item "Balanceador" em Infraestrutura (`base.html`).
8. **Documentação**: atualizar `README.md` (seção Roadmap/Arquitetura) com a nova página.

## Não Escopo

- Editar pesos/prioridades dos servidores individualmente (já existe na tela de Media Servers).
- Persistir histórico de mudanças.
- Métricas em tempo real (apenas exibir contadores atuais do cluster).

## Impacto em Diretórios

- `plans/balanceador_carga_ui/` (novo).
- `backend/models/app_setting.py` (novo) + export em `backend/models/__init__.py`.
- `backend/services/settings_service.py` (novo) + export em `backend/services/__init__.py`.
- `backend/routes/admin.py` (rotas novas).
- `backend/templates/admin/load_balancer/index.html` (novo).
- `backend/templates/base.html` (link sidebar).
- `backend/services/playlist_service.py`, `backend/services/load_balancer_service.py` (leitura do setting).
- `README.md` (Roadmap/Arquitetura).

## Riscos

- Tabela ausente em deploys antigos: mitigado pelo `_ensure_lightweight_schema_updates`.
- Estratégia inválida persistida: validar contra `STRATEGIES` antes de salvar.
