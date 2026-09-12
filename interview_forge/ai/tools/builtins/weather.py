"""Read-only weather lookup through the existing weather Service."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from interview_forge.ai.tools.contracts import ToolExecutionContext, ToolResult
from interview_forge.services.weather import weather_for_location, weather_for_user


class GetWeatherArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    location: str | None = Field(default=None, max_length=120)


def _username(context: ToolExecutionContext) -> str:
    supplied = context.artifacts.get("username")
    return str(supplied or context.user_db.parent.name)


def _compact_weather(value: dict[str, object]) -> dict[str, object]:
    location = value.get("location") if isinstance(value.get("location"), dict) else {}
    current = value.get("current") if isinstance(value.get("current"), dict) else {}
    daily = value.get("daily") if isinstance(value.get("daily"), dict) else {}
    return {
        "location": {
            "display_name": location.get("display_name"),
            "mode": location.get("mode"),
        },
        "current": {
            key: current.get(key)
            for key in ("temperature", "apparent_temperature", "description", "icon")
            if key in current
        },
        "daily": {
            key: daily.get(key)
            for key in ("temperature_max", "temperature_min", "precipitation_probability_max")
            if key in daily
        },
        "updated_at": value.get("updated_at"),
        "stale": bool(value.get("stale", False)),
    }


def get_weather(context: ToolExecutionContext, args: GetWeatherArgs) -> ToolResult:
    location = (args.location or "").strip()
    value = weather_for_location(location) if location else weather_for_user(_username(context))
    return ToolResult(_compact_weather(value), "已获取天气信息")


__all__ = ["GetWeatherArgs", "get_weather"]
