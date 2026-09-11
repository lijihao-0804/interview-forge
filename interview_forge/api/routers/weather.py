"""Weather preference, lookup and forecast routes."""
from __future__ import annotations

from fastapi import APIRouter, Request

from interview_forge.api.support import error_response, json_response, read_json, require_user, service_error
from interview_forge.services.weather import WeatherServiceError, search_weather_locations, set_weather_preference, weather_for_user

router = APIRouter()


@router.get("/api/weather")
def weather(request: Request):
    user, denied = require_user(request)
    if denied is not None:
        return denied
    try:
        return json_response(weather_for_user(str(user["username"])))
    except WeatherServiceError:
        return error_response("天气服务暂时不可用", 503, error_category="weather_unavailable", retryable=True)


@router.get("/api/weather/locations")
def weather_locations(request: Request):
    user, denied = require_user(request)
    if denied is not None:
        return denied
    try:
        return json_response({"items": search_weather_locations(request.query_params.get("q", ""))})
    except ValueError as exc:
        return error_response(str(exc), 400, error_category="invalid_query")
    except WeatherServiceError:
        return error_response("城市搜索暂时不可用", 503, error_category="weather_unavailable", retryable=True)


@router.post("/api/weather/preferences")
async def weather_preferences(request: Request):
    user, denied = require_user(request)
    if denied is not None:
        return denied
    try:
        payload = await read_json(request)
        allowed = {"mode", "display_name", "latitude", "longitude", "timezone"}
        if any(key not in allowed for key in payload):
            raise ValueError("请求参数不正确")
        preference = set_weather_preference(str(user["username"]), payload)
        return json_response({"preference": {key: preference[key] for key in ("mode", "display_name", "timezone")}}, 201)
    except BaseException as exc:
        return service_error(exc, write=True) or error_response("天气设置失败", 500)
