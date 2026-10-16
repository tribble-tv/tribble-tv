# Lista de Tarefas - Plano de Segurança Tribble TV

## Fase 1: Secrets e Configuração (IMEDIATO)

### Tarefa 1.1: Gerar secrets fortes
- [ ] Gerar SECRET_KEY forte usando `python -c "import secrets; print(secrets.token_hex(32))"`
- [ ] Gerar JWT_SECRET forte usando `python -c "import secrets; print(secrets.token_hex(32))"`
- [ ] Gerar ENGINE_API_KEY forte usando `python -c "import secrets; print(secrets.token_urlsafe(32))"`
- [ ] Documentar comando de geração no README

### Tarefa 1.2: Criar .env.example
- [ ] Criar arquivo .env.example com valores placeholder seguros
- [ ] Adicionar todas as variáveis de ambiente necessárias
- [ ] Usar placeholders como `sua-chave-secreta-aqui` em vez de valores reais
- [ ] Adicionar comentários explicando cada variável

### Tarefa 1.3: Atualizar .gitignore
- [ ] Adicionar .env ao .gitignore
- [ ] Adicionar *.db ao .gitignore
- [ ] Adicionar __pycache__/ ao .gitignore
- [ ] Adicionar *.pyc ao .gitignore
- [ ] Adicionar logs/ ao .gitignore
- [ ] Adicionar .pytest_cache/ ao .gitignore

### Tarefa 1.4: Limpar .env atual
- [ ] Remover secrets reais do .env
- [ ] Substituir por placeholders seguros
- [ ] Manter apenas estrutura e comentários
- [ ] Documentar que usuário deve preencher com valores reais

### Tarefa 1.5: Documentar configuração no README
- [ ] Adicionar seção "Configuração de Segurança" no README
- [ ] Explicar como gerar secrets fortes
- [ ] Explicar importância de não commitar .env
- [ ] Adicionar checklist de segurança pós-instalação

## Fase 2: Dockerfile (ALTA PRIORIDADE)

### Tarefa 2.1: Adicionar usuário não-root
- [ ] Criar usuário appuser no Dockerfile
- [ ] Configurar WORKDIR com permissões adequadas
- [ ] Rodar aplicação como appuser
- [ ] Ajustar permissões de volumes

### Tarefa 2.2: Adicionar healthcheck
- [ ] Implementar endpoint /health no backend
- [ ] Adicionar HEALTHCHECK no Dockerfile
- [ ] Configurar intervalo, timeout e retries
- [ ] Testar healthcheck localmente

### Tarefa 2.3: Adicionar variáveis de segurança
- [ ] Adicionar PYTHONDONTWRITEBYTECODE=1
- [ ] Adicionar PYTHONUNBUFFERED=1
- [ ] Adicionar TZ=America/Sao_Paulo
- [ ] Documentar propósito de cada variável

### Tarefa 2.4: Implementar multi-stage build
- [ ] Criar stage builder para dependências
- [ ] Criar stage runtime mínimo
- [ ] Copiar apenas artefatos necessários
- [ ] Reduzir tamanho final da imagem

### Tarefa 2.5: Otimizar limpeza de cache
- [ ] Comandos RUN combinados em uma camada
- [ ] Limpar apt-cache após instalação
- [ ] Remover arquivos temporários
- [ ] Usar --no-cache-dir no pip

## Fase 3: Docker Compose (ALTA PRIORIDADE)

### Tarefa 3.1: Adicionar healthcheck em todos os serviços
- [ ] Adicionar healthcheck no serviço client
- [ ] Adicionar healthcheck no serviço panel-admin
- [ ] Adicionar healthcheck no serviço go-engine
- [ ] Adicionar healthcheck no serviço torrent-node
- [ ] Adicionar healthcheck no serviço jellyfin
- [ ] Adicionar healthcheck no serviço kodi-resolver

### Tarefa 3.2: Criar redes isoladas
- [ ] Criar rede frontend para serviços públicos
- [ ] Criar rede backend para serviços internos
- [ ] Criar rede media para servidores de mídia
- [ ] Conectar serviços às redes apropriadas
- [ ] Remover serviços da rede default

### Tarefa 3.3: Configurar DNS público
- [ ] Adicionar DNS 8.8.8.8 em todos os serviços
- [ ] Adicionar DNS 1.1.1.1 em todos os serviços
- [ ] Documentar motivo (evitar DNS Docker bugado)

### Tarefa 3.4: Adicionar limites de recursos
- [ ] Configurar limite de CPU para client
- [ ] Configurar limite de memória para client
- [ ] Configurar limite de CPU para panel-admin
- [ ] Configurar limite de memória para panel-admin
- [ ] Configurar limite de CPU para go-engine
- [ ] Configurar limite de memória para go-engine

### Tarefa 3.5: Restringir exposição de portas
- [ ] Remover exposição direta do Jellyfin (manter apenas rede interna)
- [ ] Verificar necessidade de porta 8090 (kodi-resolver)
- [ ] Documentar quais portas são públicas vs internas
- [ ] Adicionar comentário no docker-compose explicando restrições

### Tarefa 3.6: Adicionar restart policy
- [ ] Configurar restart: unless-stopped em todos os serviços
- [ ] Remover restart: no se existir
- [ ] Documentar política de restart

### Tarefa 3.7: Separar serviços sensíveis
- [ ] Mover banco de dados para rede dedicada (se PostgreSQL)
- [ ] Isolar serviços de administração
- [ ] Restringir acesso ao painel admin
- [ ] Documentar topologia de redes

## Fase 4: Autenticação e Autorização (MÉDIA PRIORIDADE)

### Tarefa 4.1: Implementar rate limiting global
- [ ] Instalar Flask-Limiter
- [ ] Configurar rate limiting por IP
- [ ] Configurar rate limiting por endpoint
- [ ] Adicionar headers de rate limit
- [ ] Testar rate limiting

### Tarefa 4.2: Adicionar proteção CSRF
- [ ] Habilitar CSRF protection no Flask
- [ ] Adicionar tokens CSRF em formulários
- [ ] Configurar exceções para APIs públicas
- [ ] Documentar uso de CSRF tokens

### Tarefa 4.3: Implementar bloqueio após tentativas falhas
- [ ] Rastrear tentativas de login por IP
- [ ] Bloquear IP após N tentativas falhas
- [ ] Implementar cooldown automático
- [ ] Adicionar log de bloqueios
- [ ] Criar endpoint para desbloqueio manual

### Tarefa 4.4: Adicionar validação de força de senha
- [ ] Implementar validação de complexidade
- [ ] Exigir mínimo de 8 caracteres
- [ ] Exigir maiúsculas, minúsculas, números e símbolos
- [ ] Bloquear senhas comuns
- [ ] Documentar requisitos de senha

### Tarefa 4.5: Implementar refresh tokens JWT
- [ ] Implementar geração de refresh token
- [ ] Implementar rota de refresh
- [ ] Configurar TTL diferente para access vs refresh
- [ ] Implementar revogação de tokens
- [ ] Documentar fluxo de refresh

### Tarefa 4.6: Adicionar auditoria de login
- [ ] Registrar todos os logins bem-sucedidos
- [ ] Registrar todas as tentativas falhas
- [ ] Registrar IP, user-agent e timestamp
- [ ] Criar dashboard de auditoria
- [ ] Implementar alertas para atividades suspeitas

## Fase 5: Monitoramento e Logs (MÉDIA PRIORIDADE)

### Tarefa 5.1: Centralizar logs em volume dedicado
- [ ] Criar volume logs no docker-compose
- [ ] Configurar todos os serviços para escrever no volume
- [ ] Usar formato estruturado (JSON)
- [ ] Configurar rotação de logs

### Tarefa 5.2: Implementar rotação de logs
- [ ] Configurar logrotate no Docker
- [ ] Definir tamanho máximo de log
- [ ] Definir retenção de logs
- [ ] Comprimir logs antigos
- [ ] Testar rotação

### Tarefa 5.3: Adicionar alertas para eventos suspeitos
- [ ] Configurar alerta para múltiplogins falhos
- [ ] Configurar alerta para acesso de IPs desconhecidos
- [ ] Configurar alerta para uso excessivo de API
- [ ] Configurar alerta para erros de autenticação
- [ ] Integrar com notificações (email/Telegram)

### Tarefa 5.4: Implementar métricas de segurança
- [ ] Coletar métricas de tentativas de login
- [ ] Coletar métricas de requisições bloqueadas
- [ ] Coletar métricas de IPs bloqueados
- [ ] Expor métricas em endpoint /metrics
- [ ] Integrar com Prometheus (opcional)

### Tarefa 5.5: Adicionar dashboard de monitoramento
- [ ] Criar dashboard simples de segurança
- [ ] Mostrar tentativas de login recentes
- [ ] Mostrar IPs bloqueados
- [ ] Mostrar métricas de rate limiting
- [ ] Atualizar em tempo real

## Fase 6: Hardening Adicional (BAIXA PRIORIDADE)

### Tarefa 6.1: Migrar para PostgreSQL (opcional)
- [ ] Avaliar necessidade de migração
- [ ] Criar backup do SQLite
- [ ] Configurar PostgreSQL no docker-compose
- [ ] Migrar dados para PostgreSQL
- [ ] Atualizar DATABASE_URL
- [ ] Testar migração completa

### Tarefa 6.2: Implementar criptografia do banco de dados
- [ ] Avaliar solução de criptografia (SQLCipher)
- [ ] Configurar chave de criptografia
- [ ] Criar backup antes de criptografar
- [ ] Migrar dados para banco criptografado
- [ ] Testar descriptografia e acesso

### Tarefa 6.3: Adicionar WAF (Web Application Firewall)
- [ ] Avaliar solução WAF (ModSecurity, Cloudflare)
- [ ] Configurar regras básicas de WAF
- [ ] Testar regras com tráfego normal
- [ ] Monitorar falsos positivos
- [ ] Documentar exceções necessárias

### Tarefa 6.4: Implementar backup automatizado
- [ ] Criar script de backup
- [ ] Configurar cron job para backup diário
- [ ] Backup de banco de dados
- [ ] Backup de configurações
- [ ] Backup de mídia (opcional)
- [ ] Testar restore

### Tarefa 6.5: Adicionar scan de vulnerabilidades
- [ ] Instalar safety ou pip-audit
- [ ] Configurar scan no CI/CD
- [ ] Scan de dependências Python
- [ ] Scan de imagens Docker (Trivy)
- [ ] Corrigir vulnerabilidades encontradas
- [ ] Documentar processo de correção

## Atualização de Documentação

### Tarefa DOC.1: Atualizar README.md
- [ ] Adicionar seção de segurança
- [ ] Documentar novas variáveis de ambiente
- [ ] Atualizar instruções de setup
- [ ] Adicionar checklist de segurança pós-setup
- [ ] Atualizar ROADMAP.md com tarefas concluídas

### Tarefa DOC.2: Criar docs/seguranca.md
- [ ] Documentar arquitetura de segurança
- [ ] Documentar fluxo de autenticação
- [ ] Documentar políticas de rate limiting
- [ ] Documentar procedimentos de incidente
- [ ] Documentar auditoria e compliance

### Tarefa DOC.3: Atualizar ROADMAP.md
- [ ] Marcar tarefas de segurança como concluídas
- [ ] Adicionar novas tarefas de segurança ao backlog
- [ ] Atualizar roadmap de curto prazo
- [ ] Atualizar roadmap de longo prazo

## Testes e Validação

### Tarefa TEST.1: Testar secrets fortes
- [ ] Verificar que aplicação inicia com novos secrets
- [ ] Verificar que JWTs são válidos com novo secret
- [ ] Verificar que API key funciona
- [ ] Testar rotação de secrets

### Tarefa TEST.2: Testar Dockerfile melhorado
- [ ] Buildar imagem com sucesso
- [ ] Verificar que container roda como não-root
- [ ] Verificar que healthcheck funciona
- [ ] Verificar tamanho reduzido da imagem

### Tarefa TEST.3: Testar docker-compose melhorado
- [ ] Subir todos os serviços com sucesso
- [ ] Verificar healthchecks passando
- [ ] Verificar isolamento de redes
- [ ] Verificar limites de recursos
- [ ] Testar restart automático

### Tarefa TEST.4: Testar autenticação melhorada
- [ ] Testar rate limiting
- [ ] Testar proteção CSRF
- [ ] Testar bloqueio após tentativas falhas
- [ ] Testar validação de senha
- [ ] Testar refresh tokens

### Tarefa TEST.5: Testar monitoramento
- [ ] Verificar logs centralizados
- [ ] Verificar rotação de logs
- [ ] Testar alertas
- [ ] Verificar métricas
- [ ] Testar dashboard

## Checklist Final de Segurança

- [ ] Todos os secrets são fortes e únicos
- [ ] .env está no .gitignore
- [ ] .env.example existe e está documentado
- [ ] Dockerfile usa usuário não-root
- [ ] Todos os serviços têm healthcheck
- [ ] Redes Docker estão isoladas
- [ ] Rate limiting está ativo
- [ ] Logs são centralizados
- [ ] Não há secrets expostos no código
- [ ] Documentação está atualizada
- [ ] Testes de segurança passaram
- [ ] Backup foi realizado antes das mudanças
