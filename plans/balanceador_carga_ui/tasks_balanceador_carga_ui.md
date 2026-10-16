# Tasks: Configuração Visual do Balanceador de Carga

- [x] **T1**: Criar `backend/models/app_setting.py` e exportar em `models/__init__.py`.
- [x] **T2**: Bootstrap da tabela `app_settings` em `_ensure_lightweight_schema_updates`.
- [x] **T3**: Criar `backend/services/settings_service.py` com `get_setting`/`set_setting` e cache simples.
- [x] **T4**: Adicionar rotas `GET/POST /admin/load-balancer` em `backend/routes/admin.py`.
- [x] **T5**: Criar template `backend/templates/admin/load_balancer/index.html`.
- [x] **T6**: Integrar leitura do setting em `playlist_service` e `load_balancer_service`.
- [x] **T7**: Adicionar link "Balanceador" na sidebar em `templates/base.html`.
- [x] **T8**: Atualizar `README.md` com a nova página e ajustar Roadmap.
