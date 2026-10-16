# Plano de Implementação de Segurança - Tribble TV

## Objetivo
Melhorar a segurança do projeto Tribble TV baseando-se nas melhores práticas implementadas no projeto u82ja, prevenindo intrusões e vazamento de dados sensíveis.

## Contexto
Análise comparativa entre u82ja (projeto de referência com boas práticas de segurança) e tribble_tv (projeto atual com vulnerabilidades identificadas).

## Vulnerabilidades Identificadas

### 1. Secrets Expostos (CRÍTICO)
- **SECRET_KEY=dev-secret** - Chave Flask muito fraca e previsível
- **JWT_SECRET=dev-jwt-secret** - Segredo JWT muito fraco
- **NGROK_AUTHTOKEN** exposto no .env
- **Senhas Jellyfin** em texto plano no .env
- **API keys** expostas (TMDB, Jellyfin)
- **ENGINE_API_KEY=dev-engine-key** - Chave de API muito fraca

### 2. Dockerfile Inseguro
- Container roda como **root** (sem usuário não-root)
- Sem **healthcheck**
- Sem variáveis de segurança (PYTHONDONTWRITEBYTECODE, PYTHONUNBUFFERED)
- Sem limpeza adequada de cache apt
- Sem multi-stage build para reduzir tamanho e superfície de ataque

### 3. Docker Compose Inseguro
- Portas expostas sem restrição (5000, 5001, 8080, 8096, 9119, 8090)
- Sem **healthcheck** nos serviços
- Sem **redes isoladas** (todos na rede default)
- Sem **DNS configurado** (pode falhar em redes Docker bugadas)
- Sem **limites de recursos** (CPU, memória)
- Jellyfin exposto diretamente na porta 8096 sem autenticação adicional

### 4. Ausência de .gitignore
- .env não está no .gitignore (risco de vazar secrets no git)
- tribble_tv.db não está no .gitignore (risco de vazar dados)

### 5. Ausência de .env.example
- Não há template de configuração segura
- Novos desenvolvedores não sabem quais variáveis são necessárias

### 6. Autenticação Fraca
- JWT com secret fraco permite falsificação de tokens
- Sem rate limiting configurado (apenas ENGINE_API_KEY)
- Sem proteção contra brute force
- Sem CSRF protection

### 7. Banco de Dados
- SQLite em produção (não ideal para segurança e concorrência)
- Sem criptografia do banco de dados

### 8. Logs e Monitoramento
- Sem centralização de logs
- Sem alertas de segurança
- Sem auditoria de acessos

## Melhorias Propostas

### Fase 1: Secrets e Configuração (IMEDIATO)
1. Gerar secrets fortes usando `secrets.token_hex(32)`
2. Criar .env.example com valores placeholder seguros
3. Adicionar .env ao .gitignore
4. Adicionar tribble_tv.db ao .gitignore
5. Remover secrets reais do .env atual
6. Documentar geração de secrets no README

### Fase 2: Dockerfile (ALTA PRIORIDADE)
1. Adicionar usuário não-root (appuser)
2. Adicionar healthcheck
3. Adicionar variáveis de segurança (PYTHONDONTWRITEBYTECODE, PYTHONUNBUFFERED)
4. Implementar multi-stage build
5. Limpar cache apt adequadamente
6. Reduzir número de camadas

### Fase 3: Docker Compose (ALTA PRIORIDADE)
1. Adicionar healthcheck em todos os serviços
2. Criar redes isoladas (frontend, backend, media)
3. Configurar DNS público (8.8.8.8, 1.1.1.1)
4. Adicionar limites de recursos (CPU, memória)
5. Restringir exposição de portas (Jellyfin apenas na rede interna)
6. Adicionar restart policy unless-stopped
7. Separar serviços sensíveis em rede dedicada

### Fase 4: Autenticação e Autorização (MÉDIA PRIORIDADE)
1. Implementar rate limiting global
2. Adicionar proteção CSRF
3. Implementar bloqueio após tentativas falhas
4. Adicionar validação de força de senha
5. Implementar refresh tokens JWT
6. Adicionar auditoria de login

### Fase 5: Monitoramento e Logs (MÉDIA PRIORIDADE)
1. Centralizar logs em volume dedicado
2. Implementar rotação de logs
3. Adicionar alertas para eventos suspeitos
4. Implementar métricas de segurança
5. Adicionar dashboard de monitoramento

### Fase 6: Hardening Adicional (BAIXA PRIORIDADE)
1. Migrar para PostgreSQL (opcional, depende de escala)
2. Implementar criptografia do banco de dados
3. Adicionar WAF (Web Application Firewall)
4. Implementar backup automatizado
5. Adicionar scan de vulnerabilidades nas dependências

## Impacto na Estrutura de Arquivos

### Novos Arquivos
- `.env.example` - Template de configuração segura
- `.dockerignore` - Arquivos a ignorar no build
- `docs/seguranca.md` - Documentação de segurança

### Arquivos Modificados
- `.env` - Remover secrets reais, usar placeholders
- `.gitignore` - Adicionar .env, *.db, logs
- `Dockerfile` - Adicionar segurança e multi-stage
- `docker-compose.yml` - Adicionar healthchecks, redes, limites
- `README.md` - Adicionar seção de segurança

## Riscos e Mitigações

### Risco: Downtime durante migração
**Mitigação**: Implementar mudanças incrementalmente, testar em ambiente de staging

### Risco: Quebra de integrações existentes
**Mitigação**: Manter compatibilidade com configurações antigas via defaults

### Risco: Perda de dados durante migração de banco
**Mitigação**: Backup completo antes de qualquer migração de banco

## Critérios de Sucesso

- [ ] Todos os secrets são fortes e únicos
- [ ] .env está no .gitignore
- [ ] .env.example existe e está documentado
- [ ] Dockerfile usa usuário não-root
- [ ] Todos os serviços têm healthcheck
- [ ] Redes Docker estão isoladas
- [ ] Rate limiting está ativo
- [ ] Logs são centralizados
- [ ] Não há secrets expostos no código

## Cronograma Estimado

- **Fase 1**: 2 horas (IMEDIATO)
- **Fase 2**: 3 horas (ALTA PRIORIDADE)
- **Fase 3**: 4 horas (ALTA PRIORIDADE)
- **Fase 4**: 6 horas (MÉDIA PRIORIDADE)
- **Fase 5**: 4 horas (MÉDIA PRIORIDADE)
- **Fase 6**: 8 horas (BAIXA PRIORIDADE)

**Total estimado**: ~27 horas de trabalho

## Referências

- Projeto u82ja (d:\2026\projetos\u82ja) - Implementação de referência
- OWASP Top 10 - Principais vulnerabilidades web
- Docker Security Best Practices
- Flask Security Documentation
