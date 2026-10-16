"""Serviços do backend Tribble TV."""

from .load_balancer_service import LoadBalancerService, get_load_balancer, load_balancer
from .server_health_service import ServerHealthService, health_service, start_health_monitoring, stop_health_monitoring
from .settings_service import KEY_LIVE_STRATEGY, KEY_VOD_STRATEGY, get_setting, set_setting

__all__ = [
    "LoadBalancerService",
    "get_load_balancer",
    "load_balancer",
    "ServerHealthService",
    "health_service",
    "start_health_monitoring",
    "stop_health_monitoring",
    "KEY_LIVE_STRATEGY",
    "KEY_VOD_STRATEGY",
    "get_setting",
    "set_setting",
]
