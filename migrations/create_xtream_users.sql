-- Migration: Cria tabela de usuários Xtream Codes
-- Executar se a tabela não existir

CREATE TABLE IF NOT EXISTS xtream_users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username VARCHAR(80) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    is_active BOOLEAN DEFAULT 1 NOT NULL,
    max_connections INTEGER DEFAULT 1 NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_xtream_users_username ON xtream_users(username);

-- Inserir usuário de exemplo (altere/remova antes de usar em produção)
-- Senha: pbkdf2:sha256:600000$... (hash gerado pelo werkzeug)
INSERT OR IGNORE INTO xtream_users (username, password_hash, is_active, max_connections)
VALUES (
    'usuario_exemplo', 
    'pbkdf2:sha256:600000$teste$1234567890abcdef', 
    1, 
    1
);
