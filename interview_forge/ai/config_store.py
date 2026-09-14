"""Project-scoped storage for managed AI configuration.

This database is deliberately separate from auth and per-user learning DBs.
Only encrypted provider secrets are stored here; callers receive redacted
provider records by default.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import sqlite3
import uuid
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlparse
import ipaddress
import socket

from cryptography.fernet import Fernet, InvalidToken

from interview_forge.core.paths import DATA_DIR


AI_CONFIG_DB_PATH = DATA_DIR / "ai_config.db"
SUPPORTED_BUSINESS_KEYS = ("chat", "learning_analysis", "memory_extraction")
SUPPORTED_PROTOCOLS = {"openai_chat", "openai_responses", "anthropic_messages", "gemini"}
_MAX_PROVIDER_NAME = 96
_MAX_MODEL_ID = 160


class AIConfigError(ValueError):
    """Safe, user-facing validation/configuration error."""


class AISecretUnavailable(AIConfigError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _db_path(path: Path | str | None = None) -> Path:
    value = path or os.environ.get("INTERVIEW_FORGE_AI_CONFIG_DB", "")
    return Path(value) if value else AI_CONFIG_DB_PATH


def validate_base_url(value: str) -> str:
    value = str(value or "").strip().rstrip("/")
    if len(value) > 512:
        raise AIConfigError("Base URL 过长")
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise AIConfigError("Base URL 必须是 http 或 https 地址")
    if parsed.username or parsed.password:
        raise AIConfigError("Base URL 不允许包含用户名或密码")
    if parsed.fragment:
        raise AIConfigError("Base URL 不允许包含 fragment")
    try:
        address = ipaddress.ip_address(parsed.hostname or "")
    except ValueError:
        address = None
    if address is not None and (address.is_unspecified or address.is_link_local or address.is_multicast):
        raise AIConfigError("Base URL 不允许指向未指定、链路本地或组播地址")
    return value


def network_scope(value: str) -> str:
    """Classify only what can be established without performing DNS."""
    hostname = (urlparse(str(value or "")).hostname or "").lower()
    if hostname == "localhost":
        return "local/private"
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        return "unknown"
    return "local/private" if address.is_private or address.is_loopback else "public"


def validate_network_target(value: str) -> None:
    """Resolve a probe target once and reject unsafe resolved addresses."""
    hostname = (urlparse(str(value or "")).hostname or "").strip().lower()
    if not hostname:
        raise AIConfigError("Base URL 主机名缺失")
    if hostname in {"metadata.google.internal", "metadata", "instance-data"}:
        raise AIConfigError("禁止访问云元数据地址")
    try:
        addresses = {
            ipaddress.ip_address(item[4][0])
            for item in socket.getaddrinfo(hostname, None, type=socket.SOCK_STREAM)
        }
    except (OSError, ValueError) as exc:
        raise AIConfigError("Base URL 主机名无法解析") from exc
    if not addresses:
        raise AIConfigError("Base URL 主机名无法解析")
    forbidden = [address for address in addresses if address.is_unspecified or address.is_link_local or address.is_multicast]
    if forbidden:
        raise AIConfigError("Base URL 解析到不允许的网络地址")


def _validate_models_path(value: str) -> str:
    value = str(value or "/models").strip()
    if not value.startswith("/") or "://" in value or len(value) > 160:
        raise AIConfigError("模型发现路径不合法")
    return value


def _cipher() -> Fernet:
    raw = os.environ.get("INTERVIEW_FORGE_AI_CONFIG_KEY", "").strip()
    if not raw:
        raise AISecretUnavailable("AI 配置主密钥未设置")
    try:
        key = raw.encode("ascii")
        Fernet(key)
    except Exception:
        # Permit a deployment secret stored as an ordinary env string while
        # still deriving a stable authenticated-encryption key from it.
        key = base64.urlsafe_b64encode(hashlib.sha256(raw.encode("utf-8")).digest())
    return Fernet(key)


def encrypt_secret(secret: str) -> str:
    if not str(secret or ""):
        raise AISecretUnavailable("API Key 不能为空")
    return _cipher().encrypt(str(secret).encode("utf-8")).decode("ascii")


def decrypt_secret(ciphertext: str) -> str:
    if not ciphertext:
        return ""
    try:
        return _cipher().decrypt(str(ciphertext).encode("ascii")).decode("utf-8")
    except (AISecretUnavailable, InvalidToken, UnicodeError, ValueError) as exc:
        raise AISecretUnavailable("AI 配置主密钥不可用") from exc


def key_hint(secret: str) -> str:
    secret = str(secret or "")
    if not secret:
        return ""
    suffix = secret[-3:] if len(secret) >= 3 else secret
    return f"{secret[:3] if len(secret) >= 3 else ''}••••{suffix}"


@dataclass(frozen=True)
class ProviderRecord:
    id: str
    name: str
    vendor: str
    protocol: str
    base_url: str
    enabled: bool
    models_path: str
    key_configured: bool
    key_hint: str
    created_at: str
    updated_at: str
    last_test_status: str | None
    last_test_latency_ms: float | None
    last_test_at: str | None


@dataclass(frozen=True)
class ModelRecord:
    id: str
    provider_id: str
    model_id: str
    display_name: str
    enabled: bool
    available: bool
    capabilities: dict[str, Any]
    capability_source: str
    discovered_at: str | None
    last_seen_at: str | None


@dataclass(frozen=True)
class BusinessProfile:
    business_key: str
    provider_id: str
    model_id: str
    reasoning_mode: str
    reasoning_effort: str | None
    reasoning_budget: int | None
    enabled: bool
    updated_at: str


SCHEMA = """
CREATE TABLE IF NOT EXISTS ai_providers (
 id TEXT PRIMARY KEY, name TEXT NOT NULL, vendor TEXT NOT NULL,
 protocol TEXT NOT NULL, base_url TEXT NOT NULL, encrypted_secret TEXT,
 enabled INTEGER NOT NULL DEFAULT 1, models_path TEXT NOT NULL DEFAULT '/models',
 created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
 last_test_status TEXT, last_test_latency_ms REAL, last_test_at TEXT
);
CREATE TABLE IF NOT EXISTS ai_models (
 id TEXT PRIMARY KEY, provider_id TEXT NOT NULL REFERENCES ai_providers(id) ON DELETE CASCADE,
 model_id TEXT NOT NULL, display_name TEXT NOT NULL, enabled INTEGER NOT NULL DEFAULT 1,
 available INTEGER NOT NULL DEFAULT 1, capabilities_json TEXT NOT NULL DEFAULT '{}',
 capability_source TEXT NOT NULL DEFAULT 'unknown', discovered_at TEXT, last_seen_at TEXT,
 UNIQUE(provider_id, model_id)
);
CREATE TABLE IF NOT EXISTS ai_business_profiles (
 business_key TEXT PRIMARY KEY, provider_id TEXT NOT NULL REFERENCES ai_providers(id),
 model_id TEXT NOT NULL, reasoning_mode TEXT NOT NULL DEFAULT 'auto',
 reasoning_effort TEXT, reasoning_budget INTEGER, enabled INTEGER NOT NULL DEFAULT 1,
 updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_ai_models_provider ON ai_models(provider_id);
"""


def _bool(value: Any) -> bool:
    return bool(int(value)) if isinstance(value, (int, str)) else bool(value)


class AIConfigStore:
    def __init__(self, path: Path | str | None = None) -> None:
        self.path = _db_path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.ensure_schema()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=8)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 8000")
        return connection

    def ensure_schema(self) -> None:
        with closing(self.connect()) as connection:
            connection.executescript(SCHEMA)
            connection.commit()

    @staticmethod
    def _provider(row: sqlite3.Row) -> ProviderRecord:
        secret = str(row["encrypted_secret"] or "")
        hint = ""
        if secret:
            try:
                hint = key_hint(decrypt_secret(secret))
            except AISecretUnavailable:
                hint = "已配置（主密钥不可用）"
        return ProviderRecord(
            id=str(row["id"]), name=str(row["name"]), vendor=str(row["vendor"]),
            protocol=str(row["protocol"]), base_url=str(row["base_url"]),
            enabled=_bool(row["enabled"]), models_path=str(row["models_path"]),
            key_configured=bool(secret), key_hint=hint,
            created_at=str(row["created_at"]), updated_at=str(row["updated_at"]),
            last_test_status=row["last_test_status"],
            last_test_latency_ms=row["last_test_latency_ms"], last_test_at=row["last_test_at"],
        )

    @staticmethod
    def _model(row: sqlite3.Row) -> ModelRecord:
        try:
            capabilities = json.loads(str(row["capabilities_json"] or "{}"))
        except (TypeError, ValueError, json.JSONDecodeError):
            capabilities = {}
        return ModelRecord(
            id=str(row["id"]), provider_id=str(row["provider_id"]),
            model_id=str(row["model_id"]), display_name=str(row["display_name"]),
            enabled=_bool(row["enabled"]), available=_bool(row["available"]),
            capabilities=capabilities if isinstance(capabilities, dict) else {},
            capability_source=str(row["capability_source"]),
            discovered_at=row["discovered_at"], last_seen_at=row["last_seen_at"],
        )

    def list_providers(self) -> list[ProviderRecord]:
        with closing(self.connect()) as connection:
            rows = connection.execute("SELECT * FROM ai_providers ORDER BY name, id").fetchall()
        return [self._provider(row) for row in rows]

    def get_provider(self, provider_id: str) -> ProviderRecord | None:
        with closing(self.connect()) as connection:
            row = connection.execute("SELECT * FROM ai_providers WHERE id = ?", (str(provider_id),)).fetchone()
        return self._provider(row) if row else None

    def _secret_for(self, provider_id: str) -> str:
        with closing(self.connect()) as connection:
            row = connection.execute("SELECT encrypted_secret FROM ai_providers WHERE id = ?", (str(provider_id),)).fetchone()
        if not row:
            raise LookupError("Provider 不存在")
        return decrypt_secret(str(row[0] or ""))

    def create_provider(self, *, name: str, vendor: str, protocol: str, base_url: str,
                        api_key: str = "", enabled: bool = True, models_path: str = "/models") -> ProviderRecord:
        name = str(name or "").strip()[:_MAX_PROVIDER_NAME]
        vendor = str(vendor or "").strip().lower()[:64]
        protocol = str(protocol or "").strip().lower()[:64]
        if not name or not vendor or not protocol:
            raise AIConfigError("Provider 名称、Vendor、Protocol 不能为空")
        if protocol not in SUPPORTED_PROTOCOLS:
            raise AIConfigError("不支持的 Provider Protocol")
        base_url = validate_base_url(base_url)
        encrypted = encrypt_secret(api_key) if api_key else None
        now, provider_id = _now(), uuid.uuid4().hex
        with closing(self.connect()) as connection:
            connection.execute("""INSERT INTO ai_providers
                (id,name,vendor,protocol,base_url,encrypted_secret,enabled,models_path,created_at,updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (provider_id, name, vendor, protocol, base_url, encrypted, int(enabled), _validate_models_path(models_path), now, now))
            connection.commit()
        return self.get_provider(provider_id)  # type: ignore[return-value]

    def update_provider(self, provider_id: str, *, name: str | None = None, vendor: str | None = None,
                        protocol: str | None = None, base_url: str | None = None,
                        api_key: str | None = None, clear_api_key: bool = False,
                        enabled: bool | None = None, models_path: str | None = None) -> ProviderRecord:
        current = self.get_provider(provider_id)
        if current is None:
            raise LookupError("Provider 不存在")
        fields: list[str] = []
        values: list[Any] = []
        if name is not None:
            value = str(name).strip()[:_MAX_PROVIDER_NAME]
            if not value: raise AIConfigError("Provider 名称不能为空")
            fields.append("name = ?"); values.append(value)
        if vendor is not None: fields.append("vendor = ?"); values.append(str(vendor).strip().lower()[:64])
        if protocol is not None:
            protocol_value = str(protocol).strip().lower()[:64]
            if protocol_value not in SUPPORTED_PROTOCOLS: raise AIConfigError("不支持的 Provider Protocol")
            fields.append("protocol = ?"); values.append(protocol_value)
        if base_url is not None: fields.append("base_url = ?"); values.append(validate_base_url(base_url))
        if enabled is not None: fields.append("enabled = ?"); values.append(int(bool(enabled)))
        if models_path is not None: fields.append("models_path = ?"); values.append(_validate_models_path(models_path))
        if clear_api_key and api_key:
            raise AIConfigError("不能同时替换和清除 API Key")
        if api_key is not None: fields.append("encrypted_secret = ?"); values.append(encrypt_secret(api_key))
        elif clear_api_key: fields.append("encrypted_secret = NULL")
        if fields:
            fields.append("updated_at = ?"); values.append(_now()); values.append(str(provider_id))
            with closing(self.connect()) as connection:
                connection.execute(f"UPDATE ai_providers SET {', '.join(fields)} WHERE id = ?", values)
                connection.commit()
        return self.get_provider(provider_id)  # type: ignore[return-value]

    def delete_provider(self, provider_id: str) -> None:
        with closing(self.connect()) as connection:
            if connection.execute("SELECT 1 FROM ai_business_profiles WHERE provider_id = ? LIMIT 1", (str(provider_id),)).fetchone():
                raise AIConfigError("Provider 仍被业务路由使用，不能删除")
            cursor = connection.execute("DELETE FROM ai_providers WHERE id = ?", (str(provider_id),))
            if cursor.rowcount == 0: raise LookupError("Provider 不存在")
            connection.commit()

    def list_models(self, provider_id: str | None = None) -> list[ModelRecord]:
        sql, params = "SELECT * FROM ai_models", []
        if provider_id: sql += " WHERE provider_id = ?"; params.append(str(provider_id))
        sql += " ORDER BY provider_id, model_id"
        with closing(self.connect()) as connection:
            rows = connection.execute(sql, params).fetchall()
        return [self._model(row) for row in rows]

    def upsert_model(self, *, provider_id: str, model_id: str, display_name: str | None = None,
                     capabilities: Mapping[str, Any] | None = None, capability_source: str = "unknown",
                     available: bool = True, enabled: bool = True, discovered_at: str | None = None) -> ModelRecord:
        model_id = str(model_id or "").strip()
        if not model_id or len(model_id) > _MAX_MODEL_ID or any(ord(ch) < 32 for ch in model_id):
            raise AIConfigError("模型 ID 不合法")
        now = _now(); discovered_at = discovered_at or now
        with closing(self.connect()) as connection:
            connection.execute("""INSERT INTO ai_models
                (id,provider_id,model_id,display_name,enabled,available,capabilities_json,capability_source,discovered_at,last_seen_at)
                VALUES (?,?,?,?,?,?,?,?,?,?) ON CONFLICT(provider_id,model_id) DO UPDATE SET
                display_name=excluded.display_name, available=excluded.available,
                last_seen_at=excluded.last_seen_at,
                capabilities_json=CASE WHEN excluded.capability_source='manual' THEN excluded.capabilities_json ELSE ai_models.capabilities_json END,
                capability_source=CASE WHEN excluded.capability_source='manual' THEN excluded.capability_source ELSE ai_models.capability_source END""",
                (uuid.uuid4().hex, str(provider_id), model_id, str(display_name or model_id)[:_MAX_MODEL_ID], int(enabled), int(available),
                 json.dumps(dict(capabilities or {}), ensure_ascii=False, separators=(",", ":")), str(capability_source), discovered_at, now))
            connection.commit()
            row = connection.execute("SELECT * FROM ai_models WHERE provider_id = ? AND model_id = ?", (str(provider_id), model_id)).fetchone()
        return self._model(row)  # type: ignore[arg-type]

    def mark_provider_models_unavailable(self, provider_id: str, seen_model_ids: set[str]) -> None:
        with closing(self.connect()) as connection:
            rows = connection.execute("SELECT model_id FROM ai_models WHERE provider_id = ?", (str(provider_id),)).fetchall()
            for row in rows:
                if str(row[0]) not in seen_model_ids:
                    connection.execute("UPDATE ai_models SET available = 0 WHERE provider_id = ? AND model_id = ?", (str(provider_id), str(row[0])))
            connection.commit()

    def update_model(
        self,
        *,
        provider_id: str,
        model_id: str,
        enabled: bool | None = None,
        display_name: str | None = None,
        capabilities: Mapping[str, Any] | None = None,
    ) -> ModelRecord:
        fields: list[str] = []
        values: list[Any] = []
        if enabled is not None:
            fields.append("enabled = ?"); values.append(int(bool(enabled)))
        if display_name is not None:
            label = str(display_name).strip()[:_MAX_MODEL_ID]
            if not label: raise AIConfigError("模型显示名不能为空")
            fields.append("display_name = ?"); values.append(label)
        if capabilities is not None:
            fields.extend(["capabilities_json = ?", "capability_source = ?"])
            values.extend([json.dumps(dict(capabilities), ensure_ascii=False, separators=(",", ":")), "manual"])
        if fields:
            with closing(self.connect()) as connection:
                values.extend([str(provider_id), str(model_id)])
                cursor = connection.execute(
                    f"UPDATE ai_models SET {', '.join(fields)} WHERE provider_id = ? AND model_id = ?",
                    values,
                )
                if cursor.rowcount == 0: raise LookupError("模型不存在")
                connection.commit()
        item = next((item for item in self.list_models(provider_id) if item.model_id == str(model_id)), None)
        if item is None: raise LookupError("模型不存在")
        return item

    def get_profile(self, business_key: str) -> BusinessProfile | None:
        with closing(self.connect()) as connection:
            row = connection.execute("SELECT * FROM ai_business_profiles WHERE business_key = ?", (str(business_key),)).fetchone()
        if not row: return None
        return BusinessProfile(str(row["business_key"]), str(row["provider_id"]), str(row["model_id"]), str(row["reasoning_mode"]), row["reasoning_effort"], row["reasoning_budget"], _bool(row["enabled"]), str(row["updated_at"]))

    def list_profiles(self) -> list[BusinessProfile]:
        with closing(self.connect()) as connection:
            rows = connection.execute("SELECT * FROM ai_business_profiles ORDER BY business_key").fetchall()
        return [BusinessProfile(str(row["business_key"]), str(row["provider_id"]), str(row["model_id"]), str(row["reasoning_mode"]), row["reasoning_effort"], row["reasoning_budget"], _bool(row["enabled"]), str(row["updated_at"])) for row in rows]

    def save_profile(self, profile: BusinessProfile) -> BusinessProfile:
        if profile.business_key not in SUPPORTED_BUSINESS_KEYS: raise AIConfigError("不支持的业务类型")
        with closing(self.connect()) as connection:
            provider = connection.execute("SELECT enabled FROM ai_providers WHERE id = ?", (profile.provider_id,)).fetchone()
            if provider is None: raise LookupError("Provider 不存在")
            if not _bool(provider[0]): raise AIConfigError("Provider 已停用")
            model = connection.execute(
                "SELECT enabled, available FROM ai_models WHERE provider_id = ? AND model_id = ?",
                (profile.provider_id, profile.model_id),
            ).fetchone()
            if model is None: raise AIConfigError("模型不存在")
            if not _bool(model[0]): raise AIConfigError("模型已停用")
            if not _bool(model[1]): raise AIConfigError("模型当前不可用")
            connection.execute("""INSERT INTO ai_business_profiles(business_key,provider_id,model_id,reasoning_mode,reasoning_effort,reasoning_budget,enabled,updated_at)
                VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(business_key) DO UPDATE SET provider_id=excluded.provider_id,model_id=excluded.model_id,reasoning_mode=excluded.reasoning_mode,reasoning_effort=excluded.reasoning_effort,reasoning_budget=excluded.reasoning_budget,enabled=excluded.enabled,updated_at=excluded.updated_at""",
                (profile.business_key, profile.provider_id, profile.model_id, profile.reasoning_mode, profile.reasoning_effort, profile.reasoning_budget, int(profile.enabled), _now()))
            connection.commit()
        return self.get_profile(profile.business_key)  # type: ignore[return-value]

    def provider_secret(self, provider_id: str) -> str:
        return self._secret_for(provider_id)


__all__ = ["AIConfigError", "AIConfigStore", "AISecretUnavailable", "AI_CONFIG_DB_PATH", "BusinessProfile", "ModelRecord", "ProviderRecord", "SUPPORTED_BUSINESS_KEYS", "SUPPORTED_PROTOCOLS", "decrypt_secret", "encrypt_secret", "key_hint", "network_scope", "validate_base_url", "validate_network_target"]
