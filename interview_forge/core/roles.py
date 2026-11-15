"""Authoritative role presentation derived only from a server-resolved account.

The persisted role stays user/admin for old workers and clients. Never trust an
effective_role or role_label supplied by a client, token, cache, or database row.
"""
from interview_forge.core.runtime import server_runtime


def _field(user, key, default=None):
    try:
        return user[key]
    except (KeyError, IndexError, TypeError):
        return default


def has_admin_role(user) -> bool:
    # Older authenticated projections omit is_active; session resolution already
    # rejects inactive accounts. Explicit inactive values always fail closed.
    return _field(user, "role") == "admin" and _field(user, "is_active", 1) == 1


def effective_role(user, *, permanent_username=None) -> str:
    if not has_admin_role(user):
        return "user"
    value = server_runtime.PERMANENT_ADMIN_USERNAME if permanent_username is None else permanent_username
    configured = str(value or "").strip()
    if configured and _field(user, "is_active", 0) == 1 and _field(user, "username") == configured:
        return "super_admin"
    return "admin"


def role_fields(user) -> dict[str, str]:
    tier = effective_role(user)
    return {"role": "admin" if _field(user, "role") == "admin" else "user", "effective_role": tier,
            "role_label": {"user": "用户", "admin": "管理员", "super_admin": "超级管理员"}[tier]}
