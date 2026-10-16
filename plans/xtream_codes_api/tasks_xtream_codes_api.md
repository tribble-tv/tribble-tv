# Tasks: Xtream Codes API Completa

## Task 0: Criar ferramenta database.py (inspirado em resoluta_pront)
**Status**: completed
**Priority**: high

Criar `backend/database.py` com:
- Setup SQLAlchemy (engine, session, base)
- Detecção de dialecto (SQLite)
- Funções utilitárias (`_column_exists`, `_index_exists`, `_table_exists`)
- Migrations automáticas (`ensure_xtream_users_table`)
- Seed de dados (`seed_default_xtream_user`)
- Inicialização automática (`init_database`)

## Task 1: Criar Modelo XtreamUser
**Status**: pending
**Priority**: high

Criar `backend/models/xtream_user.py`:
```python
from backend.extensions import db
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash

class XtreamUser(db.Model):
    __tablename__ = "xtream_users"
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(120), nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    max_connections = db.Column(db.Integer, default=1)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
```

Atualizar `backend/models/__init__.py` para exportar.

---

## Task 2: Criar Service de Autenticação
**Status**: pending
**Priority**: high

Criar `backend/services/xtream_auth_service.py`:
- `authenticate(username, password)` - retorna XtreamUser ou None
- `generate_user_info(user)` - formata user_info para API
- `generate_server_info()` - formata server_info para API

---

## Task 3: Atualizar Endpoints Xtream
**Status**: pending
**Priority**: high

Modificar `backend/routes/xtream.py`:
- Adicionar validação de username/password em todos os endpoints
- Atualizar `player_api.php` para retornar dados reais do usuário
- Garantir compatibilidade com formato XCIPTV

---

## Task 4: Admin Interface
**Status**: pending
**Priority**: medium

Criar em `backend/routes/admin.py`:
- Listar usuários Xtream
- Criar novo usuário (form)
- Editar usuário
- Ativar/desativar

Templates HTML correspondentes.

---

## Task 5: Seed de Usuário Padrão
**Status**: pending
**Priority**: medium

Em `backend/app.py`, adicionar:
- `_seed_xtream_users()` que lê de `XTREAM_SEED_USERS` env var
- Formato: `username1:password1,username2:password2`

---

## Task 6: Testes e Validação
**Status**: pending
**Priority**: high

- Testar autenticação no XCIPTV
- Verificar formato JSON de todas as respostas
- Validar URLs de streams
- Testar playlist M3U
