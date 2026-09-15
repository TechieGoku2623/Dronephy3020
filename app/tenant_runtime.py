"""Per-tenant runtime registry for SaaS isolation."""

from __future__ import annotations

from dataclasses import dataclass
from threading import Lock

from app.human_control import HumanControlLayer
from app.memory_engine import SelfAdaptingMemory
from app.models import PowerLineSegment
from app.routing_engine import RoutingEngine
from app.weather_service import WeatherService


@dataclass
class TenantRuntime:
    """Tenant-specific service set."""

    weather_service: WeatherService
    human_control: HumanControlLayer
    memory: SelfAdaptingMemory
    routing_engine: RoutingEngine


class TenantRuntimeRegistry:
    """Lazily initializes and stores tenant runtime instances."""

    def __init__(self, base_segments: list[PowerLineSegment], weather_api_base: str) -> None:
        self._base_segments = base_segments
        self._weather_api_base = weather_api_base
        self._runtime_by_tenant: dict[str, TenantRuntime] = {}
        self._lock = Lock()

    def _new_runtime(self) -> TenantRuntime:
        weather_service = WeatherService(api_base=self._weather_api_base)
        human_control = HumanControlLayer()
        memory = SelfAdaptingMemory()
        routing_engine = RoutingEngine(self._base_segments, weather_service, memory, human_control)
        return TenantRuntime(
            weather_service=weather_service,
            human_control=human_control,
            memory=memory,
            routing_engine=routing_engine,
        )

    def get(self, tenant_id: str) -> TenantRuntime:
        """Fetch an existing tenant runtime or create one."""
        with self._lock:
            runtime = self._runtime_by_tenant.get(tenant_id)
            if runtime is None:
                runtime = self._new_runtime()
                self._runtime_by_tenant[tenant_id] = runtime
            return runtime

    def tenants(self) -> list[str]:
        """List known tenants currently active in memory."""
        with self._lock:
            return sorted(self._runtime_by_tenant.keys())
