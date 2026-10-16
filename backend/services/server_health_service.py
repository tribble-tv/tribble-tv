"""Serviço de health check para servidores de streaming."""
import logging
import threading
import time
from typing import Optional
import requests
from backend.extensions import db
from backend.models import StreamingServer


class ServerHealthService:
    """Monitora saúde dos servidores de streaming."""
    
    CHECK_INTERVAL = 30  # segundos entre checagens
    TIMEOUT = 5  # segundos para timeout da requisição
    MAX_FAILURES = 3  # falhas consecutivas antes de marcar como unhealthy
    
    def __init__(self):
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
    
    def start_monitoring(self):
        """Inicia thread de monitoramento em background."""
        with self._lock:
            if self._running:
                return
            
            self._running = True
            self._thread = threading.Thread(target=self._monitor_loop, daemon=True)
            self._thread.start()
            logging.info("[HealthService] Monitoramento iniciado")
    
    def stop_monitoring(self):
        """Para thread de monitoramento."""
        with self._lock:
            self._running = False
            if self._thread:
                self._thread.join(timeout=5)
            logging.info("[HealthService] Monitoramento parado")
    
    def _monitor_loop(self):
        """Loop contínuo de health check."""
        while True:
            with self._lock:
                if not self._running:
                    break
            
            try:
                self.check_all_servers()
            except Exception as e:
                logging.error(f"[HealthService] Erro no monitoramento: {e}")
            
            # Aguardar intervalo
            for _ in range(self.CHECK_INTERVAL):
                with self._lock:
                    if not self._running:
                        break
                time.sleep(1)
    
    def check_all_servers(self):
        """Verifica saúde de todos os servidores ativos."""
        servers = StreamingServer.query.filter_by(is_active=True).all()
        
        for server in servers:
            result = self.check_server(server)
            self._update_server_status(server, result)
    
    def check_server(self, server: StreamingServer) -> dict:
        """Verifica saúde de um servidor específico.
        
        Returns:
            Dict com resultado do health check
        """
        url = f"{server.url}/health"
        
        try:
            start_time = time.time()
            response = requests.get(url, timeout=self.TIMEOUT)
            latency_ms = int((time.time() - start_time) * 1000)
            
            healthy = response.status_code == 200
            
            return {
                "healthy": healthy,
                "status_code": response.status_code,
                "latency_ms": latency_ms,
                "error": None
            }
            
        except requests.exceptions.Timeout:
            return {
                "healthy": False,
                "status_code": None,
                "latency_ms": self.TIMEOUT * 1000,
                "error": "timeout"
            }
        except requests.exceptions.ConnectionError:
            return {
                "healthy": False,
                "status_code": None,
                "latency_ms": None,
                "error": "connection_error"
            }
        except Exception as e:
            return {
                "healthy": False,
                "status_code": None,
                "latency_ms": None,
                "error": str(e)
            }
    
    def _update_server_status(self, server: StreamingServer, result: dict):
        """Atualiza status do servidor no banco de dados."""
        server.last_health_check = db.func.now()
        server.latency_ms = result.get("latency_ms")
        
        if result["healthy"]:
            # Resetar falhas se está saudável
            if server.health_status != "healthy":
                server.health_status = "healthy"
                server.health_check_failures = 0
                logging.info(f"[HealthService] Servidor {server.name} está saudável")
        else:
            # Incrementar falhas
            server.health_check_failures += 1
            
            if server.health_check_failures >= self.MAX_FAILURES:
                if server.health_status != "unreachable":
                    server.health_status = "unreachable"
                    logging.warning(
                        f"[HealthService] Servidor {server.name} marcado como unreachable "
                        f"({server.health_check_failures} falhas, erro: {result.get('error')})"
                    )
        
        db.session.commit()
    
    def force_check(self, server_id: int) -> dict:
        """Força health check imediato de um servidor.
        
        Returns:
            Resultado do health check
        """
        server = StreamingServer.query.get(server_id)
        if not server:
            return {"error": "Server not found"}
        
        result = self.check_server(server)
        self._update_server_status(server, result)
        
        return {
            "server_id": server_id,
            "server_name": server.name,
            **result,
            "health_status": server.health_status
        }


# Instância global do serviço de health check
health_service = ServerHealthService()


def start_health_monitoring():
    """Inicia monitoramento de saúde dos servidores."""
    health_service.start_monitoring()


def stop_health_monitoring():
    """Para monitoramento de saúde."""
    health_service.stop_monitoring()
