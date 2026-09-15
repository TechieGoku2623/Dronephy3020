"""Authentication and tenant resolution for multi-tenant SaaS operation."""

from __future__ import annotations

from dataclasses import dataclass
from re import fullmatch

from fastapi import Header, HTTPException, status

from app.config import Settings

TENANT_PATTERN = r"^[a-z0-9][a-z0-9_-]{1,63}$"


@dataclass(frozen=True)
class RequestContext:
    """Resolved request context used by business endpoints."""

    tenant_id: str
    principal: str
    api_key_present: bool


class Authenticator:
    """Validates API keys and tenant headers according to runtime settings."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._api_key_name_by_value = {value: name for name, value in settings.api_keys.items()}

    def _resolve_tenant(self, raw_tenant: str | None) -> str:
        if raw_tenant is None or not raw_tenant.strip():
            if self._settings.enforce_tenant_header:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Missing required X-Tenant-ID header.",
                )
            tenant = self._settings.default_tenant_id
        else:
            tenant = raw_tenant.strip().lower()

        if not fullmatch(TENANT_PATTERN, tenant):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Invalid tenant id format. Use lowercase alphanumeric, '_' or '-'.",
            )
        return tenant

    def _resolve_principal(self, raw_api_key: str | None) -> tuple[str, bool]:
        key_present = bool(raw_api_key and raw_api_key.strip())
        if raw_api_key:
            api_key = raw_api_key.strip()
            principal = self._api_key_name_by_value.get(api_key)
            if principal:
                return principal, True
            if self._settings.api_keys:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid API key.",
                )

        if self._settings.require_api_key:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing API key.",
            )
        return "anonymous", key_present

    async def dependency(
        self,
        x_tenant_id: str | None = Header(default=None, alias="X-Tenant-ID"),
        x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    ) -> RequestContext:
        """FastAPI dependency that resolves tenant + principal for each request."""
        tenant = self._resolve_tenant(x_tenant_id)
        principal, key_present = self._resolve_principal(x_api_key)
        return RequestContext(tenant_id=tenant, principal=principal, api_key_present=key_present)
