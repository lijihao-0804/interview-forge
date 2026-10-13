"""工具箱·健身房自动预约 API 的管理员边界与排程校验测试。"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from interview_forge.api.app import app
from interview_forge.services import gym

USER = {"username": "student01", "role": "user", "nickname": "同学甲"}
ADMIN = {"username": "admin01", "role": "admin", "nickname": "管理员"}


def _client() -> TestClient:
    return TestClient(app)


class GymToolboxRouteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.jobs_patcher = patch(
            "interview_forge.api.routers.gym.gym.list_jobs", return_value=[])
        self.jobs_patcher.start()
        self.addCleanup(self.jobs_patcher.stop)

    def tearDown(self) -> None:
        pass

    def test_jobs_list_requires_login(self) -> None:
        with _client() as client:
            response = client.get("/api/tools/gym/jobs")
        self.assertEqual(response.status_code, 401)

    def test_jobs_list_forbidden_for_regular_user(self) -> None:
        with patch("interview_forge.api.support.current_user", return_value=USER):
            with _client() as client:
                response = client.get("/api/tools/gym/jobs")
        self.assertEqual(response.status_code, 403)

    def test_jobs_list_ok_for_admin(self) -> None:
        with patch("interview_forge.api.support.current_user", return_value=ADMIN):
            with _client() as client:
                response = client.get("/api/tools/gym/jobs")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["items"], [])

    def test_status_forbidden_for_regular_user(self) -> None:
        with patch("interview_forge.api.support.current_user", return_value=USER):
            with _client() as client:
                response = client.get("/api/tools/gym/status")
        self.assertEqual(response.status_code, 403)

    def test_create_job_requires_configured_credentials(self) -> None:
        future = (date.today() + timedelta(days=3)).isoformat()
        with patch("interview_forge.api.support.current_user", return_value=ADMIN), \
             patch("interview_forge.api.routers.gym.gym.credentials_status",
                   return_value={"configured": False}), \
             patch("interview_forge.api.routers.gym.gym.create_job",
                   side_effect=gym.GymServiceError("请先在工具箱中保存南大账号密码，再创建自动预约")):
            with _client() as client:
                response = client.post("/api/tools/gym/jobs", json={
                    "target_date": future, "slots": ["17:00-18:00"]})
        self.assertEqual(response.status_code, 400)
        self.assertIn("南大账号密码", response.json()["error"])

    def test_all_gym_endpoints_reject_anonymous_and_regular_users(self) -> None:
        """安全回归：工具箱 API 不能只靠前端隐藏，每个端点都必须在服务端拒绝
        匿名（401）与普通用户（403）。新增端点时必须加入此表。"""
        endpoints = [
            ("GET", "/api/tools/gym/jobs", None),
            ("POST", "/api/tools/gym/jobs", {"target_date": "2026-10-15", "slots": ["17:00-18:00"]}),
            ("DELETE", "/api/tools/gym/jobs/1", None),
            ("POST", "/api/tools/gym/jobs/1/resolve", {"confirmed_no_order": True}),
            ("GET", "/api/tools/gym/status", None),
            ("GET", "/api/tools/gym/credentials", None),
            ("POST", "/api/tools/gym/credentials", {"account": "12345678", "password": "x" * 10}),
            ("DELETE", "/api/tools/gym/credentials", None),
        ]
        with _client() as client:
            for method, path, body in endpoints:
                kwargs = {"json": body} if body is not None else {}
                with self.subTest(endpoint=f"{method} {path}"):
                    response = client.request(method, path, **kwargs)
                    self.assertEqual(response.status_code, 401)
                with patch("interview_forge.api.support.current_user", return_value=USER):
                    response = client.request(method, path, **kwargs)
                    self.assertEqual(response.status_code, 403)

    def test_tools_page_forbidden_for_regular_user(self) -> None:
        """页面级 gate：普通用户直接访问 /pages/tools.html 必须被 403。

        注意 static.py 以 `from support import current_user` 直接绑定名字，
        必须 patch static 模块的引用才能命中真实代码路径。
        """
        with patch("interview_forge.api.routers.static.current_user", return_value=USER):
            with _client() as client:
                response = client.get("/pages/tools.html")
        self.assertEqual(response.status_code, 403)


class GymServiceValidationTests(unittest.TestCase):
    def test_create_job_rejects_past_date(self) -> None:
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        with self.assertRaises(gym.GymServiceError):
            gym.create_job(yesterday, ["17:00-18:00"], "admin01")

    def test_create_job_rejects_bad_slot(self) -> None:
        future = (date.today() + timedelta(days=2)).isoformat()
        with patch.object(gym, "credentials_status", return_value={"configured": True}), \
             patch.object(gym, "connect", side_effect=AssertionError("不应走到建库")):
            with self.assertRaises(gym.GymServiceError):
                gym.create_job(future, ["25:00-26:00"], "admin01")

    def test_create_job_rejects_reversed_or_zero_length_slot(self) -> None:
        future = (date.today() + timedelta(days=2)).isoformat()
        with patch.object(gym, "credentials_status", return_value={"configured": True}), \
             patch.object(gym, "connect", side_effect=AssertionError("不应走到建库")):
            for slot in ("18:00-17:00", "17:00-17:00"):
                with self.subTest(slot=slot), self.assertRaises(gym.GymServiceError):
                    gym.create_job(future, [slot], "admin01")

    def test_slot_pattern_accepts_canonical_ranges(self) -> None:
        self.assertTrue(gym.SLOT_PATTERN.fullmatch("17:00-18:00"))
        self.assertTrue(gym.SLOT_PATTERN.fullmatch("09:00-10:00"))
        self.assertFalse(gym.SLOT_PATTERN.fullmatch("17:00~18:00"))


class GymCredentialCryptoTests(unittest.TestCase):
    def setUp(self) -> None:
        import tempfile
        from pathlib import Path as PathLib

        self._tmp = tempfile.TemporaryDirectory()
        key_path = gym.SECRET_KEY_PATH
        self._original_key_path = key_path
        self._original_key = key_path.read_bytes() if key_path.exists() else None
        import interview_forge.services.gym as gym_module

        self._patcher = patch.object(gym_module, "SECRET_KEY_PATH",
                                     PathLib(self._tmp.name) / "gym-secret.key")
        self._patcher.start()
        self.addCleanup(self._patcher.stop)
        self._db_patcher = patch.object(gym_module, "GYM_DB_PATH",
                                        PathLib(self._tmp.name) / "gym.db")
        self._db_patcher.start()
        self.addCleanup(self._db_patcher.stop)
        self.addCleanup(self._tmp.cleanup)

    def tearDown(self) -> None:
        if self._original_key is not None:
            self._original_key_path.write_bytes(self._original_key)

    def test_save_and_load_roundtrip(self) -> None:
        status = gym.save_credentials("admin01", "522025230035", "a-secret-password",
                                      verify=False)
        self.assertTrue(status["configured"])
        self.assertEqual(status["account_masked"], "522****35")
        account, password = gym._load_credentials_decrypted("admin01")
        self.assertEqual(account, "522025230035")
        self.assertEqual(password, "a-secret-password")

    def test_delete_credentials(self) -> None:
        gym.save_credentials("admin01", "522025230035", "a-secret-password",
                             verify=False)
        gym.delete_credentials("admin01")
        self.assertFalse(gym.credentials_status("admin01")["configured"])
        with self.assertRaises(gym.GymServiceError):
            gym._load_credentials_decrypted("admin01")


if __name__ == "__main__":
    unittest.main()


class GymVerificationTests(unittest.TestCase):
    def setUp(self) -> None:
        import tempfile
        from pathlib import Path as PathLib

        self._tmp = tempfile.TemporaryDirectory()
        import interview_forge.services.gym as gym_module
        self._patcher = patch.object(gym_module, "SECRET_KEY_PATH",
                                     PathLib(self._tmp.name) / "gym-secret.key")
        self._patcher.start()
        self._db_patcher = patch.object(gym_module, "GYM_DB_PATH",
                                        PathLib(self._tmp.name) / "gym.db")
        self._db_patcher.start()
        self.addCleanup(self._patcher.stop)
        self.addCleanup(self._db_patcher.stop)
        self.addCleanup(self._tmp.cleanup)

    def test_save_rejects_bad_credentials_without_storing(self) -> None:
        with patch.object(gym, "verify_credentials",
                          return_value={"status": "bad_credentials", "detail": "账号或密码不正确"}):
            with self.assertRaises(gym.GymServiceError) as ctx:
                gym.save_credentials("admin01", "522025230035", "wrong-password")
        self.assertIn("不正确", str(ctx.exception))
        self.assertFalse(gym.credentials_status("admin01")["configured"])

    def test_save_stores_after_successful_verification(self) -> None:
        with patch.object(gym, "verify_credentials",
                          return_value={"status": "ok", "detail": "登录验证通过"}):
            status = gym.save_credentials("admin01", "522025230035", "a-secret-password")
        self.assertTrue(status["configured"])
        self.assertEqual(status["verification"]["status"], "ok")


class GymSmtpConfigTests(unittest.TestCase):
    def setUp(self) -> None:
        import tempfile
        from pathlib import Path as PathLib

        self._tmp = tempfile.TemporaryDirectory()
        import interview_forge.services.gym as gym_module
        self._patcher = patch.object(gym_module, "SECRET_KEY_PATH",
                                     PathLib(self._tmp.name) / "gym-secret.key")
        self._patcher.start()
        self._db_patcher = patch.object(gym_module, "GYM_DB_PATH",
                                        PathLib(self._tmp.name) / "gym.db")
        self._db_patcher.start()
        self.addCleanup(self._patcher.stop)
        self.addCleanup(self._db_patcher.stop)
        self.addCleanup(self._tmp.cleanup)

    def test_smtp_roundtrip_and_recipient(self) -> None:
        status = gym.save_smtp_config("2723542256@qq.com", "x" * 16)
        self.assertTrue(status["configured"])
        self.assertEqual(status["smtp_user"], "2723542256@qq.com")
        gym.set_notify_recipient("admin01", "2030309470@qq.com")
        merged = gym.notify_status("admin01")
        self.assertTrue(merged["configured"])
        self.assertEqual(merged["recipient"], "2030309470@qq.com")
        gym.delete_smtp_config()
        self.assertFalse(gym.notify_status("admin01")["configured"])

    def test_legacy_notify_row_migrates_to_global_smtp(self) -> None:
        conn = gym.connect()
        conn.execute(
            "INSERT INTO gym_notify_config (username, smtp_host, smtp_port, smtp_user,"
            " auth_code_encrypted, notify_to, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("legacy-user", "smtp.163.com", 465, "old@163.com", "ENC", "old@163.com",
             "2026-10-11T00:00:00"),
        )
        conn.commit()
        conn.close()
        status = gym.smtp_config_status()
        self.assertTrue(status["configured"])
        self.assertEqual(status["smtp_user"], "old@163.com")
        self.assertEqual(status["smtp_host"], "smtp.163.com")


class ToolsInterpreterTests(unittest.TestCase):
    """工具箱执行器解释器：默认跟服务一致，可用环境变量或 .venv-tools 指到单独环境。"""

    def _clear_override(self):
        os.environ.pop("GYM_TOOLS_PYTHON", None)

    def test_defaults_to_the_current_interpreter(self) -> None:
        self._clear_override()
        with patch.object(gym, "ROOT", Path(tempfile.gettempdir()) / "no-such-root"):
            self.assertEqual(gym.tools_python(), sys.executable)

    def test_env_override_points_at_a_separate_tools_venv(self) -> None:
        target = r"E:\interview-forge\.venv-tools\Scripts\python.exe"
        with patch.dict(os.environ, {"GYM_TOOLS_PYTHON": target}):
            self.assertEqual(gym.tools_python(), target)

    def test_blank_override_falls_back(self) -> None:
        with patch.dict(os.environ, {"GYM_TOOLS_PYTHON": "   "}):
            with patch.object(gym, "ROOT", Path(tempfile.gettempdir()) / "no-such-root"):
                self.assertEqual(gym.tools_python(), sys.executable)

    def test_repo_local_tools_venv_is_picked_up_without_configuration(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            exe = root / ".venv-tools" / "Scripts" / "python.exe"
            exe.parent.mkdir(parents=True)
            exe.write_bytes(b"")
            self._clear_override()
            with patch.object(gym, "ROOT", root):
                self.assertEqual(gym.tools_python(), str(exe))

    def test_env_override_wins_over_the_repo_local_tools_venv(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            exe = root / ".venv-tools" / "Scripts" / "python.exe"
            exe.parent.mkdir(parents=True)
            exe.write_bytes(b"")
            with patch.object(gym, "ROOT", root), \
                    patch.dict(os.environ, {"GYM_TOOLS_PYTHON": "explicit-python"}):
                self.assertEqual(gym.tools_python(), "explicit-python")
