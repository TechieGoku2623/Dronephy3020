"""Asynchronous weather lockout service with operator override support."""

from __future__ import annotations

import os
from dataclasses import dataclass

import httpx

from app.models import SafetyStatus, WeatherOverrideInput

LOCKOUT_WIND_SPEED_MS = 15.0
HEAVY_RAIN_MM_PER_HR = 6.0


@dataclass
class WeatherAssessment:
    """Weather risk state used by routing."""

    quadrant: str
    wind_speed_ms: float
    heavy_precipitation: bool
    safety_status: SafetyStatus


class WeatherService:
    """Fetches weather context and applies operator "weather overwrite" controls."""

    def __init__(self) -> None:
        self._overrides: dict[str, WeatherOverrideInput] = {}
        self._api_base = os.getenv("WEATHER_API_BASE", "").strip()

    @staticmethod
    def quadrant(latitude: float, longitude: float) -> str:
        """Map coordinate sign to an operational quadrant label."""
        north = "N" if latitude >= 0 else "S"
        east = "E" if longitude >= 0 else "W"
        return f"{north}{east}"

    def apply_override(self, weather_override: WeatherOverrideInput) -> None:
        """Persist simulated micro-climate input from operator controls."""
        self._overrides[weather_override.quadrant.upper()] = weather_override

    def clear_override(self, quadrant: str) -> None:
        """Clear one weather override."""
        self._overrides.pop(quadrant.upper(), None)

    async def _query_external_weather(self, latitude: float, longitude: float) -> tuple[float, bool] | None:
        """
        Query external weather if configured.

        Returns:
            (wind_speed_ms, heavy_precipitation) or None when unavailable.
        """
        if not self._api_base:
            return None

        params = {"latitude": latitude, "longitude": longitude}
        try:
            async with httpx.AsyncClient(timeout=1.0) as client:
                response = await client.get(self._api_base, params=params)
                response.raise_for_status()
                payload = response.json()
        except Exception:
            return None

        current = payload.get("current", {})
        wind_speed = float(
            current.get("wind_speed_10m", current.get("windspeed", current.get("wind_speed", 0.0)))
        )
        rain_mm = float(current.get("rain", current.get("precipitation", 0.0)))
        weather_code = int(current.get("weather_code", current.get("weathercode", 0)))
        heavy_precipitation = rain_mm >= HEAVY_RAIN_MM_PER_HR or weather_code in {63, 65, 67, 82, 86, 96, 99}
        return wind_speed, heavy_precipitation

    async def assess(self, latitude: float, longitude: float, fallback_wind_speed_ms: float) -> WeatherAssessment:
        """Compute weather safety status from override, external API, or local telemetry."""
        quad = self.quadrant(latitude, longitude)
        override = self._overrides.get(quad)
        if override is not None:
            wind_speed = override.wind_speed_ms
            heavy_precip = override.heavy_precipitation
        else:
            external = await self._query_external_weather(latitude, longitude)
            if external is not None:
                wind_speed, heavy_precip = external
            else:
                wind_speed = fallback_wind_speed_ms
                heavy_precip = False

        safety = SafetyStatus.SAFE
        if wind_speed > LOCKOUT_WIND_SPEED_MS or heavy_precip:
            safety = SafetyStatus.UNSAFE_WEATHER_LOCKOUT

        return WeatherAssessment(
            quadrant=quad,
            wind_speed_ms=wind_speed,
            heavy_precipitation=heavy_precip,
            safety_status=safety,
        )
