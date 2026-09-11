"""Account weather preferences and Open-Meteo business operations.

The service consumes late-bound composition-root dependencies.  The existing
application and tests replace paths, auth connections, cache objects and
upstream helpers on the assembly object; resolving those dependencies at call
time preserves that extension point while keeping weather rules out of the
HTTP module.
"""
from __future__ import annotations
from interview_forge.core.runtime import server_runtime

import json
import asyncio
import re
import threading
import time
import unicodedata
from contextlib import closing
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


_WEATHER_DEFAULT = {"mode": "default", "display_name": "南京", "latitude": 32.06,
                    "longitude": 118.80, "timezone": "Asia/Shanghai"}
_WEATHER_FRESH_DEFAULT = 30 * 60
_WEATHER_FRESH_CUSTOM = 15 * 60
_WEATHER_STALE_MAX = 6 * 60 * 60
_WEATHER_SEARCH_TTL = 7 * 24 * 60 * 60
_WEATHER_SEARCH_VERSION = "cn-rank-v2"
_WEATHER_CACHE: dict[tuple[object, ...], tuple[float, dict[str, object]]] = {}
_WEATHER_SEARCH_CACHE: dict[str, tuple[float, list[dict[str, object]]]] = {}
_WEATHER_CACHE_LOCK = threading.Lock()
_WEATHER_KEY_LOCKS: dict[tuple[object, ...], threading.Lock] = {}
_WEATHER_KEY_LOCKS_LOCK = threading.Lock()



class WeatherServiceError(RuntimeError):
    """稳定的天气上游失败；异常正文不向浏览器透传。"""


def _weather_key_lock(key: tuple[object, ...]):
    with _WEATHER_KEY_LOCKS_LOCK:
        return _WEATHER_KEY_LOCKS.setdefault(key, threading.Lock())


def _weather_http_json(base_url: str, params: dict[str, object]) -> dict[str, object]:
    request = Request(base_url + "?" + urlencode(params), headers={
        "Accept": "application/json", "User-Agent": "InterviewForge/1.0 weather",
    })
    try:
        with urlopen(request, timeout=8) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise WeatherServiceError("天气服务暂时不可用") from exc
    if not isinstance(payload, dict):
        raise WeatherServiceError("天气服务暂时不可用")
    return payload


def _weather_code(code: int) -> dict[str, object]:
    groups = [
        ({0}, "晴", "☀️"), ({1}, "大致晴朗", "🌤️"), ({2}, "局部多云", "⛅"),
        ({3}, "阴", "☁️"), ({45, 48}, "有雾", "🌫️"),
        ({51, 53, 55}, "毛毛雨", "🌦️"), ({56, 57, 66, 67}, "冻雨", "🌧️"),
        ({61, 63, 65}, "有雨", "🌧️"), ({71, 73, 75, 77}, "有雪", "🌨️"),
        ({80, 81, 82}, "阵雨", "🌦️"), ({85, 86}, "阵雪", "🌨️"),
        ({95, 96, 99}, "雷暴", "⛈️"),
    ]
    for codes, description, icon in groups:
        if code in codes:
            return {"code": code, "description": description, "icon": icon}
    return {"code": code, "description": "天气变化", "icon": "🌡️"}


def get_weather_preference(username: str) -> dict[str, object]:
    runtime = server_runtime
    with closing(runtime.connect_auth()) as connection:
        row = connection.execute(
            """SELECT wp.mode, wp.display_name, wp.latitude, wp.longitude, wp.timezone
               FROM users u LEFT JOIN weather_preferences wp ON wp.user_id = u.id
               WHERE u.username = ?""", (username,)).fetchone()
    if row is None:
        raise ValueError("用户不存在")
    if row["mode"] is None:
        return dict(_WEATHER_DEFAULT)
    return {key: row[key] for key in ("mode", "display_name", "latitude", "longitude", "timezone")}


def set_weather_preference(username: str, payload: dict[str, object]) -> dict[str, object]:
    runtime = server_runtime
    mode = str(payload.get("mode", "")).strip()
    if mode not in {"default", "city", "geolocation"}:
        raise ValueError("天气位置模式不正确")
    with closing(runtime.connect_auth()) as connection:
        row = connection.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()
        if row is None:
            raise ValueError("用户不存在")
        if mode == "default":
            connection.execute("DELETE FROM weather_preferences WHERE user_id = ?", (row["id"],))
            return dict(_WEATHER_DEFAULT)
        try:
            latitude = float(payload.get("latitude"))
            longitude = float(payload.get("longitude"))
        except (TypeError, ValueError) as exc:
            raise ValueError("经纬度格式不正确") from exc
        if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
            raise ValueError("经纬度超出范围")
        if mode == "geolocation":
            latitude, longitude = round(latitude, 2), round(longitude, 2)
            display_name, timezone_name = "当前位置", "auto"
        else:
            display_name = str(payload.get("display_name", "")).strip()
            timezone_name = str(payload.get("timezone", "auto")).strip() or "auto"
            if not (1 <= len(display_name) <= 50):
                raise ValueError("城市名称长度不正确")
            if len(timezone_name) > 64 or not re.fullmatch(r"[A-Za-z0-9_+./:-]+", timezone_name):
                raise ValueError("时区格式不正确")
            latitude, longitude = round(latitude, 4), round(longitude, 4)
        connection.execute(
            """INSERT INTO weather_preferences(user_id, mode, display_name, latitude, longitude, timezone, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(user_id) DO UPDATE SET mode=excluded.mode, display_name=excluded.display_name,
                 latitude=excluded.latitude, longitude=excluded.longitude, timezone=excluded.timezone,
                 updated_at=excluded.updated_at""",
            (row["id"], mode, display_name, latitude, longitude, timezone_name, runtime.now_iso()))
    return {"mode": mode, "display_name": display_name, "latitude": latitude,
            "longitude": longitude, "timezone": timezone_name}


def _fetch_weather(preference: dict[str, object]) -> dict[str, object]:
    runtime = server_runtime
    payload = runtime._weather_http_json("https://api.open-meteo.com/v1/forecast", {
        "latitude": preference["latitude"], "longitude": preference["longitude"],
        "current": "temperature_2m,apparent_temperature,weather_code",
        "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max",
        "timezone": preference.get("timezone") or "auto", "forecast_days": 1,
    })
    current, daily = payload.get("current"), payload.get("daily")
    if not isinstance(current, dict) or not isinstance(daily, dict):
        raise WeatherServiceError("天气服务暂时不可用")
    try:
        code = int(current["weather_code"])
        result = {
            "location": {"mode": preference["mode"], "display_name": preference["display_name"],
                         "timezone": str(payload.get("timezone") or preference.get("timezone") or "")},
            "current": {"temperature": float(current["temperature_2m"]),
                        "apparent_temperature": float(current["apparent_temperature"]), **_weather_code(code)},
            "daily": {"temperature_max": float(daily["temperature_2m_max"][0]),
                      "temperature_min": float(daily["temperature_2m_min"][0]),
                      "precipitation_probability_max": int(daily["precipitation_probability_max"][0])},
            "updated_at": str(current.get("time") or runtime.now_iso()), "stale": False,
            "source": {"name": "Open-Meteo", "url": "https://open-meteo.com/"},
        }
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise WeatherServiceError("天气服务暂时不可用") from exc
    return result


def _weather_response(cached: dict[str, object], preference: dict[str, object], *, stale: bool | None = None) -> dict[str, object]:
    """把共享坐标缓存投影为当前账号的显示名，不在缓存键/值中绑定用户。"""
    result = dict(cached)
    location = dict(result.get("location", {}))
    location.update({"mode": preference["mode"], "display_name": preference["display_name"]})
    result["location"] = location
    if stale is not None:
        result["stale"] = stale
    return result


def weather_for_user(username: str) -> dict[str, object]:
    runtime = server_runtime
    preference = runtime.get_weather_preference(username)
    default = preference["mode"] == "default"
    key = (("forecast", "default-nanjing") if default else
           ("forecast", round(float(preference["latitude"]), 2), round(float(preference["longitude"]), 2)))
    ttl = _WEATHER_FRESH_DEFAULT if default else _WEATHER_FRESH_CUSTOM
    now = time.monotonic()
    with _WEATHER_CACHE_LOCK:
        cached = _WEATHER_CACHE.get(key)
    if cached and now - cached[0] <= ttl:
        return _weather_response(cached[1], preference)
    lock = runtime._weather_key_lock(key)
    if not lock.acquire(blocking=False):
        if cached and now - cached[0] <= _WEATHER_STALE_MAX:
            return _weather_response(cached[1], preference, stale=True)
        if not lock.acquire(timeout=10):
            raise WeatherServiceError("天气服务暂时不可用")
    try:
        with _WEATHER_CACHE_LOCK:
            cached = _WEATHER_CACHE.get(key)
        now = time.monotonic()
        if cached and now - cached[0] <= ttl:
            return _weather_response(cached[1], preference)
        try:
            result = runtime._fetch_weather(preference)
        except WeatherServiceError:
            if cached and now - cached[0] <= _WEATHER_STALE_MAX:
                return _weather_response(cached[1], preference, stale=True)
            raise
        with _WEATHER_CACHE_LOCK:
            if len(_WEATHER_CACHE) >= 256 and key not in _WEATHER_CACHE:
                oldest = min(_WEATHER_CACHE, key=lambda item: _WEATHER_CACHE[item][0])
                _WEATHER_CACHE.pop(oldest, None)
            _WEATHER_CACHE[key] = (time.monotonic(), result)
        return _weather_response(result, preference)
    finally:
        lock.release()


async def weather_for_user_async(username: str) -> dict[str, object]:
    """Event-loop-safe adapter; the established sync contract is unchanged."""
    return await asyncio.to_thread(weather_for_user, username)


def _normalize_place(value: object) -> str:
    return re.sub(r"[\s·•,，._-]+", "", unicodedata.normalize("NFKC", str(value)).casefold())


def _administrative_name(value: object) -> str:
    normalized = _normalize_place(value)
    return normalized[:-1] if normalized.endswith("市") else normalized


_CN_MAJOR_CITIES = {
    "北京", "上海", "天津", "重庆", "南京", "广州", "深圳", "杭州", "成都", "武汉",
    "西安", "长沙", "郑州", "济南", "沈阳", "长春", "哈尔滨", "合肥", "福州", "南昌",
    "昆明", "贵阳", "海口", "石家庄", "太原", "兰州", "西宁", "南宁", "呼和浩特",
    "银川", "乌鲁木齐", "拉萨",
}
_PLACE_FEATURE_RANK = {"PPLC": 0, "PPLA": 1, "PPLA2": 2, "PPLA3": 3, "PPL": 4}


def _rank_weather_location(item: dict[str, object], query: str) -> tuple[object, ...]:
    name = _normalize_place(item.get("name"))
    wanted = _normalize_place(query)
    name_admin = _administrative_name(item.get("name"))
    admin1 = _administrative_name(item.get("admin1"))
    feature = str(item.get("feature_code", "")).upper()
    population = int(item.get("population") or 0) if str(item.get("population") or "").isdigit() else 0
    return (
        0 if name == wanted or name_admin == _administrative_name(query) else 1 if name.startswith(wanted) else 2,
        0 if name_admin in _CN_MAJOR_CITIES else 1,
        _PLACE_FEATURE_RANK.get(feature, 8),
        0 if name_admin and name_admin == admin1 else 1,
        -population,
        name, admin1, _normalize_place(item.get("admin2")),
        round(float(item.get("latitude", 0)), 4), round(float(item.get("longitude", 0)), 4),
    )


def search_weather_locations(query: str) -> list[dict[str, object]]:
    runtime = server_runtime
    query = query.strip()
    if not (2 <= len(query) <= 50):
        raise ValueError("城市名称需为 2 至 50 个字符")
    cache_key = _WEATHER_SEARCH_VERSION + ":" + _normalize_place(query)
    now = time.monotonic()
    with _WEATHER_CACHE_LOCK:
        cached = _WEATHER_SEARCH_CACHE.get(cache_key)
    if cached and now - cached[0] <= _WEATHER_SEARCH_TTL:
        return [dict(item) for item in cached[1]]
    lock = runtime._weather_key_lock(("search", cache_key))
    with lock:
        with _WEATHER_CACHE_LOCK:
            cached = _WEATHER_SEARCH_CACHE.get(cache_key)
        if cached and time.monotonic() - cached[0] <= _WEATHER_SEARCH_TTL:
            return [dict(item) for item in cached[1]]
        payload = runtime._weather_http_json("https://geocoding-api.open-meteo.com/v1/search", {
            "name": query, "count": 20, "language": "zh", "countryCode": "CN", "format": "json",
        })
        candidates: list[dict[str, object]] = []
        seen: set[tuple[object, ...]] = set()
        for item in payload.get("results", []) if isinstance(payload.get("results"), list) else []:
            if not isinstance(item, dict):
                continue
            try:
                dedupe_key = (_normalize_place(item["name"]), _normalize_place(item.get("admin1")),
                              _normalize_place(item.get("admin2")), round(float(item["latitude"]), 2),
                              round(float(item["longitude"]), 2))
                if dedupe_key in seen:
                    continue
                seen.add(dedupe_key)
                candidate = dict(item)
                candidate["latitude"], candidate["longitude"] = float(item["latitude"]), float(item["longitude"])
                candidates.append(candidate)
            except (KeyError, TypeError, ValueError):
                continue
        candidates.sort(key=lambda item: runtime._rank_weather_location(item, query))
        results = []
        seen_region: set[tuple[str, str]] = set()
        for item in candidates:
            region_key = (_normalize_place(item.get("name")), _normalize_place(item.get("admin1")))
            if region_key in seen_region:
                continue
            seen_region.add(region_key)
            results.append({"city": str(item["name"])[:50], "admin1": str(item.get("admin1", ""))[:50],
                            "admin2": str(item.get("admin2", ""))[:50], "country": str(item.get("country", ""))[:50],
                            "latitude": round(float(item["latitude"]), 4), "longitude": round(float(item["longitude"]), 4),
                            "timezone": str(item.get("timezone") or "auto")[:64]})
            if len(results) >= 5:
                break
        with _WEATHER_CACHE_LOCK:
            if len(_WEATHER_SEARCH_CACHE) >= 256 and cache_key not in _WEATHER_SEARCH_CACHE:
                oldest = min(_WEATHER_SEARCH_CACHE, key=lambda item: _WEATHER_SEARCH_CACHE[item][0])
                _WEATHER_SEARCH_CACHE.pop(oldest, None)
            _WEATHER_SEARCH_CACHE[cache_key] = (time.monotonic(), results)
        return [dict(item) for item in results]
