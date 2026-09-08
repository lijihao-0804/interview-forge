import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from tools import study_server as server


FORECAST = {
    "timezone": "Asia/Shanghai",
    "current": {"time": "2026-09-08T12:00", "temperature_2m": 28.4,
                "apparent_temperature": 30.1, "weather_code": 2},
    "daily": {"temperature_2m_max": [31.0], "temperature_2m_min": [22.0],
              "precipitation_probability_max": [40]},
}


class WeatherTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.auth = Path(self.temp.name) / "auth.db"
        self.old_ready = server._AUTH_READY
        server._AUTH_READY = False
        self.auth_patch = patch.object(server, "AUTH_DB_PATH", self.auth)
        self.auth_patch.start()
        server.create_user("alice", "password1")
        server.create_user("bob", "password2")
        with server._WEATHER_CACHE_LOCK:
            server._WEATHER_CACHE.clear(); server._WEATHER_SEARCH_CACHE.clear()

    def tearDown(self):
        self.auth_patch.stop()
        server._AUTH_READY = self.old_ready
        self.temp.cleanup()

    def test_default_and_account_isolation_and_reset(self):
        self.assertEqual(server.get_weather_preference("alice")["display_name"], "南京")
        saved = server.set_weather_preference("alice", {"mode": "city", "display_name": "上海",
            "latitude": 31.2304, "longitude": 121.4737, "timezone": "Asia/Shanghai"})
        self.assertEqual(saved["display_name"], "上海")
        self.assertEqual(server.get_weather_preference("alice")["display_name"], "上海")
        self.assertEqual(server.get_weather_preference("bob")["display_name"], "南京")
        server.set_weather_preference("alice", {"mode": "default"})
        self.assertEqual(server.get_weather_preference("alice")["mode"], "default")

    def test_geolocation_is_rounded_and_overwritten(self):
        server.set_weather_preference("alice", {"mode": "geolocation", "latitude": 32.06789,
                                                 "longitude": 118.81234, "display_name": "不可信"})
        first = server.get_weather_preference("alice")
        self.assertEqual((first["latitude"], first["longitude"], first["display_name"]), (32.07, 118.81, "当前位置"))
        server.set_weather_preference("alice", {"mode": "geolocation", "latitude": 30.123,
                                                 "longitude": 120.456})
        with server.closing(server.connect_auth()) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM weather_preferences").fetchone()[0], 1)
        self.assertEqual(server.get_weather_preference("alice")["latitude"], 30.12)

    def test_validation(self):
        for payload in ({"mode": "ip"}, {"mode": "city", "display_name": "", "latitude": 1, "longitude": 2},
                        {"mode": "geolocation", "latitude": 91, "longitude": 2}):
            with self.assertRaises(ValueError):
                server.set_weather_preference("alice", payload)
        with self.assertRaises(ValueError):
            server.search_weather_locations("南")

    def test_default_and_custom_ttl_and_stale_fallback(self):
        calls = []
        original_fetch = server._fetch_weather
        def fake_fetch(pref):
            calls.append(pref["display_name"])
            return original_fetch(pref)
        with patch.object(server, "_weather_http_json", return_value=FORECAST), patch.object(server, "_fetch_weather", side_effect=fake_fetch):
            self.assertEqual(server.weather_for_user("alice")["current"]["description"], "局部多云")
            server.weather_for_user("bob")
        self.assertEqual(len(calls), 1)  # 南京跨用户共享
        key = ("forecast", "default-nanjing")
        with server._WEATHER_CACHE_LOCK:
            stamp, data = server._WEATHER_CACHE[key]
            server._WEATHER_CACHE[key] = (stamp - server._WEATHER_FRESH_DEFAULT - 1, data)
        with patch.object(server, "_fetch_weather", side_effect=server.WeatherServiceError("x")):
            self.assertTrue(server.weather_for_user("alice")["stale"])
        with server._WEATHER_CACHE_LOCK:
            _, data = server._WEATHER_CACHE[key]
            server._WEATHER_CACHE[key] = (time.monotonic() - server._WEATHER_STALE_MAX - 1, data)
        with patch.object(server, "_fetch_weather", side_effect=server.WeatherServiceError("x")):
            with self.assertRaises(server.WeatherServiceError):
                server.weather_for_user("alice")

        server.set_weather_preference("alice", {"mode": "city", "display_name": "上海",
            "latitude": 31.23, "longitude": 121.47, "timezone": "Asia/Shanghai"})
        with patch.object(server, "_weather_http_json", return_value=FORECAST):
            server.weather_for_user("alice")
        custom_key = ("forecast", 31.23, 121.47)
        with server._WEATHER_CACHE_LOCK:
            self.assertIn(custom_key, server._WEATHER_CACHE)
        self.assertEqual(server._WEATHER_FRESH_CUSTOM, 900)
        self.assertEqual(server._WEATHER_SEARCH_TTL, 604800)

    def test_same_coordinate_stampede_is_single_fetch(self):
        server.set_weather_preference("alice", {"mode": "city", "display_name": "甲", "latitude": 31.23,
                                                 "longitude": 121.47, "timezone": "Asia/Shanghai"})
        server.set_weather_preference("bob", {"mode": "city", "display_name": "乙", "latitude": 31.23,
                                               "longitude": 121.47, "timezone": "Asia/Shanghai"})
        calls = 0
        lock = threading.Lock()
        def slow(_pref):
            nonlocal calls
            with lock: calls += 1
            time.sleep(.05)
            return {"location": {"timezone": "Asia/Shanghai"}, "current": {}, "daily": {},
                    "updated_at": "now", "stale": False, "source": {}}
        results = []
        with patch.object(server, "_fetch_weather", side_effect=slow):
            threads = [threading.Thread(target=lambda name=n: results.append(server.weather_for_user(name)))
                       for n in ("alice", "bob")]
            [thread.start() for thread in threads]; [thread.join() for thread in threads]
        self.assertEqual(calls, 1)
        self.assertEqual({item["location"]["display_name"] for item in results}, {"甲", "乙"})

    def test_search_is_cached_and_cropped(self):
        upstream = {"results": [{"name": "南京", "admin1": "江苏", "country": "中国", "latitude": 32.06,
                                  "longitude": 118.8, "timezone": "Asia/Shanghai", "population": 999}]}
        with patch.object(server, "_weather_http_json", return_value=upstream) as mocked:
            first = server.search_weather_locations("南京")
            second = server.search_weather_locations("南京")
        self.assertEqual(mocked.call_count, 1)
        self.assertEqual(first, second)
        self.assertNotIn("population", first[0])

    def test_shanghai_ranking_deduplicates_noise_and_versions_cache(self):
        upstream = {"results": [
            {"name": "上海", "admin1": "云南", "admin2": "曲靖", "country": "中国", "country_code": "CN",
             "latitude": 25.1, "longitude": 103.8, "timezone": "Asia/Shanghai", "feature_code": "PPL", "population": 300},
            {"name": "上海", "admin1": "浙江", "admin2": "台州", "country": "中国", "country_code": "CN",
             "latitude": 28.7, "longitude": 121.3, "timezone": "Asia/Shanghai", "feature_code": "PPL", "population": 800},
            {"name": "上海", "admin1": "上海市", "admin2": "", "country": "中国", "country_code": "CN",
             "latitude": 31.2222, "longitude": 121.4581, "timezone": "Asia/Shanghai", "feature_code": "PPLA", "population": 24874500},
            {"name": "上海", "admin1": "云南", "admin2": "曲靖", "country": "中国", "country_code": "CN",
             "latitude": 25.1001, "longitude": 103.8001, "timezone": "Asia/Shanghai", "feature_code": "PPL", "population": 200},
            {"name": "上海", "admin1": "四川", "admin2": "达州", "country": "中国", "country_code": "CN",
             "latitude": 31.0, "longitude": 107.5, "timezone": "Asia/Shanghai", "feature_code": "PPL", "population": 100},
        ]}
        with patch.object(server, "_weather_http_json", return_value=upstream) as mocked:
            results = server.search_weather_locations("上海")
        self.assertEqual(results[0]["admin1"], "上海市")
        self.assertLessEqual(len(results), 5)
        self.assertEqual(sum(item["admin1"] == "云南" for item in results), 1)
        params = mocked.call_args.args[1]
        self.assertEqual((params["language"], params["countryCode"], params["count"]), ("zh", "CN", 20))
        with server._WEATHER_CACHE_LOCK:
            self.assertTrue(any(key.startswith(server._WEATHER_SEARCH_VERSION + ":")
                                for key in server._WEATHER_SEARCH_CACHE))

    def test_major_city_exact_result_beats_town(self):
        beijing = {"name": "北京", "admin1": "北京市", "feature_code": "PPLA", "population": 21000000,
                   "latitude": 39.9, "longitude": 116.4}
        town = {"name": "北京村", "admin1": "云南省", "feature_code": "PPL", "population": 50,
                "latitude": 25.0, "longitude": 102.0}
        self.assertLess(server._rank_weather_location(beijing, "北京"), server._rank_weather_location(town, "北京"))

    def test_ui_contract(self):
        html = (server.ROOT / "cockpit.html").read_text(encoding="utf-8")
        self.assertIn("Weather data by Open-Meteo", html)
        self.assertIn('target="_blank" rel="noopener noreferrer"', html)
        self.assertIn('navigator.geolocation.getCurrentPosition', html)
        self.assertEqual(html.count("navigator.geolocation.getCurrentPosition"), 1)
        self.assertIn('navigator.permissions.query({ name: "geolocation" })', html)
        self.assertIn('status.state === "denied"', html)
        self.assertIn('status.state === "granted"', html)
        self.assertIn('status.state === "prompt"', html)
        self.assertIn('error.code === 1', html)
        self.assertIn('!navigator.permissions || typeof navigator.permissions.query !== "function"', html)
        self.assertIn("网页无法代为修改浏览器权限", html)
        self.assertIn("地址栏左侧的网站信息或权限图标", html)
        self.assertIn("重新检测权限", html)
        self.assertIn("改为选择城市", html)
        self.assertIn("系统暂时无法获取位置", html)
        self.assertIn("获取位置超时", html)
        self.assertIn('document.getElementById("weather-geo").addEventListener("click", checkWeatherPermission)', html)
        startup = html[html.index('api("/api/me")'):html.index("/* 聊天室入口")]
        self.assertNotIn("getCurrentPosition", startup)
        self.assertNotIn("permissions.query", startup)
        self.assertIn("@media(max-width:720px)", html)
        self.assertIn("weather-modal-status", html)


if __name__ == "__main__":
    unittest.main()
