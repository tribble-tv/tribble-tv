"""Serviço de autenticação para Xtream Codes API."""
import time
from flask import current_app, request
from backend.models import XtreamUser


def authenticate(username, password):
    """Autentica um usuário Xtream Codes.
    
    Args:
        username: Nome de usuário
        password: Senha
        
    Returns:
        XtreamUser se autenticado, None caso contrário
    """
    if not username or not password:
        return None
    
    user = XtreamUser.query.filter_by(username=username, is_active=True).first()
    if not user:
        return None
    
    if user.check_password(password):
        return user
    
    return None


def generate_user_info(user):
    """Gera o objeto user_info para resposta da API.
    
    Args:
        user: Instância de XtreamUser
        
    Returns:
        Dict com informações do usuário no formato XC API
    """
    return {
        "username": user.username,
        "password": "***",  # Não retornar senha real por segurança
        "message": "Bem-vindo ao Tribble TV",
        "auth": 1,
        "status": "Active" if user.is_active else "Inactive",
        "exp_date": "null",  # Sem expiração por padrão
        "is_trial": "0",
        "active_cons": "0",  # TODO: Implementar contador de conexões ativas
        "max_connections": str(user.max_connections),
        "created_at": user.created_at.timestamp() if user.created_at else "",
    }


def generate_server_info():
    """Gera o objeto server_info para resposta da API.
    
    Returns:
        Dict com informações do servidor no formato XC API
    """
    # Determinar URL e protocolo
    host = request.host
    server_url = current_app.config.get("STREAM_PUBLIC_URL", "")
    
    # Extrair host da URL pública se disponível
    if server_url:
        from urllib.parse import urlparse
        parsed = urlparse(server_url)
        if parsed.netloc:
            host = parsed.netloc
    
    is_https = request.is_secure or "https" in server_url
    
    return {
        "url": host,
        "port": "80" if not is_https else "443",
        "https_port": "443",
        "server_protocol": "https" if is_https else "http",
        "rtmp_port": "25462",  # Porta padrão RTMP
        "timezone": "America/Sao_Paulo",
        "timestamp_now": int(time.time()),
        "time_now": time.strftime("%Y-%m-%d %H:%M:%S"),
    }


def create_default_response(user=None):
    """Cria resposta padrão do player_api.php.
    
    Args:
        user: Instância de XtreamUser ou None
        
    Returns:
        Dict com estrutura base da resposta
    """
    if user:
        return {
            "user_info": generate_user_info(user),
            "server_info": generate_server_info(),
        }
    
    # Resposta para usuário não autenticado
    return {
        "user_info": {
            "auth": 0,
            "status": "Invalid",
            "message": "Invalid username or password",
        },
        "server_info": generate_server_info(),
    }
