"""FastAPI entrypoint for GridOS-Logic v2.0 SaaS release."""

from __future__ import annotations

import logging
from dataclasses import asdict
from time import perf_counter
from uuid import uuid4

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config import Settings
from app.models import (
    DroneTelemetry,
    HumanControlCommand,
    MissionFeedback,
    PowerLineSegment,
    WeatherOverrideInput,
)
from app.rate_limiter import FixedWindowRateLimiter
from app.security import Authenticator, RequestContext
from app.tenant_runtime import TenantRuntime, TenantRuntimeRegistry


def _seed_segments() -> list[PowerLineSegment]:
    return [
        PowerLineSegment(
            segment_id="SEG-A1",
            lat_start=37.7710,
            lon_start=-122.4470,
            lat_end=37.7740,
            lon_end=-122.4410,
            current_amperage=1250.0,
            ambient_temp_c=32.0,
            wind_speed_ms=8.5,
            total_harmonic_distortion=7.5,
        ),
        PowerLineSegment(
            segment_id="SEG-B3",
            lat_start=37.7650,
            lon_start=-122.4540,
            lat_end=37.7695,
            lon_end=-122.4490,
            current_amperage=800.0,
            ambient_temp_c=28.0,
            wind_speed_ms=5.0,
            total_harmonic_distortion=4.0,
        ),
        PowerLineSegment(
            segment_id="SEG-C5",
            lat_start=37.7790,
            lon_start=-122.4390,
            lat_end=37.7830,
            lon_end=-122.4330,
            current_amperage=1550.0,
            ambient_temp_c=35.0,
            wind_speed_ms=4.5,
            total_harmonic_distortion=10.0,
        ),
        PowerLineSegment(
            segment_id="SEG-D9",
            lat_start=37.7600,
            lon_start=-122.4320,
            lat_end=37.7630,
            lon_end=-122.4270,
            current_amperage=450.0,
            ambient_temp_c=24.0,
            wind_speed_ms=12.0,
            total_harmonic_distortion=3.0,
        ),
    ]


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build FastAPI application with production SaaS controls."""
    active_settings = settings or Settings.from_env()
    if active_settings.require_api_key and not active_settings.api_keys:
        raise ValueError("GRIDOS_REQUIRE_API_KEY=true requires GRIDOS_API_KEYS to be configured.")

    logging.basicConfig(level=active_settings.log_level)
    logger = logging.getLogger("gridos-api")

    app = FastAPI(title=active_settings.app_name, version=active_settings.app_version)
    authenticator = Authenticator(active_settings)
    runtime_registry = TenantRuntimeRegistry(_seed_segments(), active_settings.weather_api_base)
    rate_limiter = FixedWindowRateLimiter(active_settings.rate_limit_per_minute)

    app.state.settings = active_settings
    app.state.runtime_registry = runtime_registry

    app.add_middleware(
        CORSMiddleware,
        allow_origins=active_settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def telemetry_middleware(request: Request, call_next):
        request_id = uuid4().hex
        request.state.request_id = request_id
        start = perf_counter()
        response = await call_next(request)
        elapsed_ms = (perf_counter() - start) * 1000.0
        response.headers["X-Request-ID"] = request_id
        logger.info(
            "request_id=%s method=%s path=%s status=%s duration_ms=%.2f",
            request_id,
            request.method,
            request.url.path,
            response.status_code,
            elapsed_ms,
        )
        return response

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException):
        request_id = getattr(request.state, "request_id", "unknown")
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail, "request_id": request_id},
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        request_id = getattr(request.state, "request_id", "unknown")
        return JSONResponse(
            status_code=422,
            content={"detail": exc.errors(), "request_id": request_id},
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        request_id = getattr(request.state, "request_id", "unknown")
        logger.exception("request_id=%s unexpected_error=%s", request_id, exc)
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal Server Error", "request_id": request_id},
        )

    @app.middleware("http")
    async def rate_limit_middleware(request: Request, call_next):
        if not active_settings.enable_rate_limit or not request.url.path.startswith("/api/"):
            return await call_next(request)

        tenant = request.headers.get("X-Tenant-ID") or active_settings.default_tenant_id
        api_key = request.headers.get("X-API-Key")
        principal = "anonymous"
        if api_key and api_key in active_settings.api_keys.values():
            principal = "api-key"
        key = f"{tenant.lower()}:{principal}:{request.client.host if request.client else 'unknown'}"
        allowed, remaining = rate_limiter.consume(key)
        if not allowed:
            return JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded. Retry in the next minute."},
                headers={
                    "X-RateLimit-Limit": str(rate_limiter.requests_per_minute),
                    "X-RateLimit-Remaining": "0",
                },
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(rate_limiter.requests_per_minute)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        return response

    async def request_context_dependency(
        context: RequestContext = Depends(authenticator.dependency),
    ) -> RequestContext:
        return context

    def get_runtime(context: RequestContext) -> TenantRuntime:
        return runtime_registry.get(context.tenant_id)

    @app.get("/health/live")
    async def liveness() -> dict[str, str]:
        """Container liveness probe endpoint."""
        return {"status": "alive"}

    @app.get("/health/ready")
    async def readiness() -> dict[str, object]:
        """Readiness probe with active tenant metadata."""
        return {
            "status": "ready",
            "environment": active_settings.environment,
            "tenants_loaded": runtime_registry.tenants(),
        }

    @app.post("/api/v1/routing/next-perch")
    async def next_perch(
        telemetry: DroneTelemetry,
        context: RequestContext = Depends(request_context_dependency),
    ):
        """Compute the safest and highest-yield next perch recommendation."""
        runtime = get_runtime(context)
        return await runtime.routing_engine.recommend_next_perch(telemetry)

    @app.get("/api/v1/grid/segments")
    async def get_grid_segments(
        context: RequestContext = Depends(request_context_dependency),
    ):
        """Expose live segment states for the dashboard."""
        runtime = get_runtime(context)
        return {"segments": await runtime.routing_engine.segment_states()}

    @app.post("/api/v1/weather/override")
    async def set_weather_override(
        weather_override: WeatherOverrideInput,
        context: RequestContext = Depends(request_context_dependency),
    ):
        """Apply human-simulated weather control to a specific quadrant."""
        runtime = get_runtime(context)
        runtime.weather_service.apply_override(weather_override)
        return {"ok": True, "quadrant": weather_override.quadrant.upper(), "tenant_id": context.tenant_id}

    @app.delete("/api/v1/weather/override/{quadrant}")
    async def clear_weather_override(
        quadrant: str,
        context: RequestContext = Depends(request_context_dependency),
    ):
        """Clear weather simulation override for one quadrant."""
        runtime = get_runtime(context)
        runtime.weather_service.clear_override(quadrant)
        return {"ok": True, "quadrant": quadrant.upper(), "tenant_id": context.tenant_id}

    @app.post("/api/v1/control/command")
    async def set_control_command(
        command: HumanControlCommand,
        context: RequestContext = Depends(request_context_dependency),
    ):
        """Set operator lockout or force-segment command."""
        runtime = get_runtime(context)
        state = runtime.human_control.update(command)
        return {"ok": True, "state": asdict(state), "tenant_id": context.tenant_id}

    @app.delete("/api/v1/control/command")
    async def clear_control_command(
        context: RequestContext = Depends(request_context_dependency),
    ):
        """Return system to autonomous-only mode."""
        runtime = get_runtime(context)
        runtime.human_control.clear()
        return {"ok": True, "tenant_id": context.tenant_id}

    @app.post("/api/v1/memory/feedback")
    async def post_mission_feedback(
        feedback: MissionFeedback,
        context: RequestContext = Depends(request_context_dependency),
    ):
        """Ingest mission outcome for self-adapting memory updates."""
        runtime = get_runtime(context)
        runtime.memory.register_feedback(feedback)
        return {"ok": True, "tenant_id": context.tenant_id}

    @app.post("/api/v1/memory/reset/{drone_id}")
    async def reset_memory(
        drone_id: str,
        context: RequestContext = Depends(request_context_dependency),
    ):
        """Reset one drone's learning profile."""
        runtime = get_runtime(context)
        runtime.memory.reset_drone(drone_id)
        return {"ok": True, "drone_id": drone_id, "tenant_id": context.tenant_id}

    @app.get("/api/v1/system/state")
    async def system_state(
        context: RequestContext = Depends(request_context_dependency),
    ):
        """Return current control and memory state for audit visibility."""
        runtime = get_runtime(context)
        state = runtime.human_control.active_state()
        return {
            "tenant_id": context.tenant_id,
            "human_control": asdict(state) if state else None,
            "memory_snapshot": runtime.memory.snapshot(),
        }

    @app.get("/api/v1/system/release")
    async def release_metadata() -> dict[str, object]:
        """Return non-secret SaaS release metadata for operational visibility."""
        return {
            "app_name": active_settings.app_name,
            "version": active_settings.app_version,
            "environment": active_settings.environment,
            "require_api_key": active_settings.require_api_key,
            "enforce_tenant_header": active_settings.enforce_tenant_header,
            "rate_limit_per_minute": active_settings.rate_limit_per_minute,
        }

    return app


app = create_app()
