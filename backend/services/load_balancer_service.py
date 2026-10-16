"""Serviço de balanceamento de carga entre servidores de streaming."""
import random
import threading
from typing import List, Optional
from backend.models import StreamingServer


class LoadBalancerService:
    """Balanceador de carga com múltiplas estratégias."""
    
    STRATEGIES = ["round_robin", "weighted", "least_connections", "random", "health_based"]
    
    def __init__(self, strategy: str = "round_robin"):
        self.strategy = strategy if strategy in self.STRATEGIES else "round_robin"
        self._counter = 0
        self._lock = threading.Lock()
    
    def get_server(self, client_id: Optional[str] = None, region: Optional[str] = None) -> Optional[StreamingServer]:
        """Retorna o melhor servidor baseado na estratégia configurada.
        
        Args:
            client_id: ID único do cliente (para sticky sessions)
            region: Região preferida do cliente (para geo-routing)
            
        Returns:
            StreamingServer disponível ou None
        """
        # Buscar servidores ativos e saudáveis
        servers = self._get_available_servers(region)
        
        if not servers:
            return None
        
        if len(servers) == 1:
            return servers[0]
        
        # Aplicar estratégia
        if self.strategy == "round_robin":
            return self._round_robin(servers)
        elif self.strategy == "weighted":
            return self._weighted(servers)
        elif self.strategy == "least_connections":
            return self._least_connections(servers)
        elif self.strategy == "random":
            return self._random(servers)
        else:  # health_based
            return self._health_based(servers)
    
    def _get_available_servers(self, region: Optional[str] = None) -> List[StreamingServer]:
        """Retorna servidores disponíveis (ativos, saudáveis, com slots)."""
        query = StreamingServer.query.filter(
            StreamingServer.is_active == True,
            StreamingServer.health_status == "healthy"
        )
        
        # Priorizar região se especificada
        if region:
            # Primeiro tentar mesma região
            regional = query.filter(StreamingServer.region == region).all()
            available_regional = [s for s in regional if s.is_available]
            if available_regional:
                return available_regional
        
        # Retornar todos disponíveis
        all_servers = query.all()
        return [s for s in all_servers if s.is_available]
    
    def _round_robin(self, servers: List[StreamingServer]) -> StreamingServer:
        """Distribui conexões igualmente em ordem circular."""
        with self._lock:
            idx = self._counter % len(servers)
            self._counter += 1
            return servers[idx]
    
    def _weighted(self, servers: List[StreamingServer]) -> StreamingServer:
        """Distribui baseado no peso (priority) de cada servidor."""
        # Criar lista ponderada
        weighted_list = []
        for server in servers:
            # Quanto maior o priority, mais chances
            weight = max(1, server.priority // 10)
            weighted_list.extend([server] * weight)
        
        return random.choice(weighted_list)
    
    def _least_connections(self, servers: List[StreamingServer]) -> StreamingServer:
        """Direciona para o servidor com menos conexões ativas."""
        return min(servers, key=lambda s: s.current_connections)
    
    def _random(self, servers: List[StreamingServer]) -> StreamingServer:
        """Seleciona servidor aleatoriamente."""
        return random.choice(servers)
    
    def _health_based(self, servers: List[StreamingServer]) -> StreamingServer:
        """Considera latência e carga para escolher o melhor."""
        # Score = latência + (carga_atual / capacidade) * 1000
        def score(server):
            latency = server.latency_ms or 1000  # Default alto se desconhecido
            load_factor = server.current_connections / max(1, server.max_connections)
            return latency + (load_factor * 1000)
        
        return min(servers, key=score)
    
    def get_all_servers_status(self) -> List[dict]:
        """Retorna status de todos os servidores para monitoramento."""
        servers = StreamingServer.query.all()
        return [{
            **server.to_dict(),
            "utilization_percent": server.load_percentage
        } for server in servers]
    
    def get_cluster_stats(self) -> dict:
        """Estatísticas agregadas do cluster."""
        servers = StreamingServer.query.all()
        
        total_capacity = sum(s.max_connections for s in servers)
        total_active = sum(s.current_connections for s in servers)
        healthy_servers = sum(1 for s in servers if s.health_status == "healthy")
        
        return {
            "total_servers": len(servers),
            "healthy_servers": healthy_servers,
            "unhealthy_servers": len(servers) - healthy_servers,
            "total_capacity": total_capacity,
            "active_connections": total_active,
            "available_capacity": total_capacity - total_active,
            "utilization_percent": (total_active / max(1, total_capacity)) * 100,
            "by_region": self._stats_by_region(servers)
        }
    
    def _stats_by_region(self, servers: List[StreamingServer]) -> dict:
        """Agrupa estatísticas por região."""
        regions = {}
        for server in servers:
            region = server.region or "unknown"
            if region not in regions:
                regions[region] = {"servers": 0, "active_connections": 0, "capacity": 0}
            regions[region]["servers"] += 1
            regions[region]["active_connections"] += server.current_connections
            regions[region]["capacity"] += server.max_connections
        
        return regions


# Instância global do balanceador
load_balancer = LoadBalancerService(strategy="round_robin")


def get_load_balancer(strategy: Optional[str] = None) -> LoadBalancerService:
    """Retorna instância do balanceador, respeitando a estratégia explícita ou
    a configuração persistida no painel (`AppSetting`)."""
    if strategy and strategy in LoadBalancerService.STRATEGIES:
        return LoadBalancerService(strategy=strategy)
    try:
        from backend.services.settings_service import KEY_LIVE_STRATEGY, get_setting

        persisted = get_setting(KEY_LIVE_STRATEGY)
        if persisted and persisted in LoadBalancerService.STRATEGIES:
            if persisted != load_balancer.strategy:
                load_balancer.strategy = persisted
            return load_balancer
    except Exception:
        pass
    return load_balancer
