# Implementation Plan: Xtream Codes API Completa

## 1. Visão Geral
Implementar API Xtream Codes completa com autenticação por username/password para compatibilidade total com XCIPTV Player e outros players IPTV.

## 2. Estrutura de Dados

### 2.1 Novo Modelo: XtreamUser
```python
- id: Integer (PK)
- username: String(80) (unique, not null)
- password: String(120) (not null, hash)
- is_active: Boolean (default True)
- max_connections: Integer (default 1)
- created_at: DateTime
- updated_at: DateTime
```

### 2.2 Relacionamentos
- Um usuário pode acessar todos os vídeos ativos do sistema
- Filtragem por categorias (HLS, Jellyfin)

## 3. Endpoints Xtream Codes

### 3.1 Autenticação
| Endpoint | Descrição |
|----------|-----------|
| `/player_api.php?username=X&password=Y` | Info do usuário + server |
| `/panel_api.php?username=X&password=Y` | Info do painel (admin) |

### 3.2 Conteúdo
| Endpoint | Descrição |
|----------|-----------|
| `/player_api.php?action=get_vod_categories` | Lista categorias VOD |
| `/player_api.php?action=get_vod_streams` | Lista streams VOD |
| `/player_api.php?action=get_vod_info&vod_id=X` | Info detalhada VOD |
| `/get.php?username=X&password=Y` | Playlist M3U completa |

## 4. Formato de Resposta

### 4.1 User Info (player_api.php)
```json
{
  "user_info": {
    "username": "usuario",
    "password": "senha",
    "message": "Bem-vindo",
    "auth": 1,
    "status": "Active",
    "exp_date": "null",
    "is_trial": "0",
    "active_cons": "0",
    "max_connections": "1"
  },
  "server_info": {
    "url": "iptv.exemplo.com",
    "port": "80",
    "https_port": "443",
    "server_protocol": "https",
    "rtmp_port": "25462",
    "timezone": "America/Sao_Paulo",
    "timestamp_now": 171...
  }
}
```

### 4.2 VOD Streams
```json
{
  "stream_id": 123,
  "name": "Nome do Filme",
  "stream_type": "movie",
  "stream_url": "https://...",
  "container_extension": "mp4",
  "category_id": "jellyfin",
  "thumbnail": "https://..."
}
```

## 5. Tarefas

### Backend
- [ ] Criar modelo `XtreamUser` em `backend/models/xtream_user.py`
- [ ] Criar service `xtream_auth_service.py` para autenticação
- [ ] Atualizar `xtream_service.py` com dados reais do usuário
- [ ] Atualizar `xtream.py` routes com validação de credenciais
- [ ] Criar admin interface para gerenciar usuários Xtream
- [ ] Adicionar seed de usuário padrão via env vars

### Banco de Dados
- [ ] Migration para criar tabela `xtream_users`

### Admin Panel
- [ ] Listar usuários Xtream
- [ ] Criar/editar usuário
- [ ] Ativar/desativar usuário

## 6. Configuração XCIPTV

Usuário configura no XCIPTV:
- **XC API URL**: `http://<host>:5000/player_api.php`
- **Username**: (usuário criado no admin)
- **Password**: (senha do usuário)

## 7. Testes

- [ ] Autenticação válida retorna user_info correto
- [ ] Autenticação inválida retorna auth: 0
- [ ] get_vod_categories retorna categorias
- [ ] get_vod_streams retorna streams com URLs válidas
- [ ] Playlist M3U acessível via /get.php
