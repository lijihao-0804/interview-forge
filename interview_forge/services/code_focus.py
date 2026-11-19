"""The admin-published Code Focus document shared by all readers."""
from __future__ import annotations

from contextlib import closing

from interview_forge.services.auth import connect_auth


LANGUAGES = frozenset({
    "auto", "plaintext", "python", "java", "cpp", "c", "go",
    "javascript", "typescript", "rust", "kotlin", "sql",
})


class PublicationConflict(Exception):
    """Another editor already published a newer version."""


def publication_version() -> int:
    with closing(connect_auth()) as connection:
        return connection.execute(
            "SELECT version FROM code_focus_publication WHERE id = 1"
        ).fetchone()["version"]


def read_publication() -> dict:
    with closing(connect_auth()) as connection:
        row = connection.execute(
            "SELECT version, code, language, answers FROM code_focus_publication WHERE id = 1"
        ).fetchone()
    return dict(row)


def publish(payload: dict) -> dict:
    if set(payload) != {"version", "code", "language", "answers"}:
        raise ValueError("请提交文稿版本、代码、语言和答案")
    version = payload["version"]
    if type(version) is not int or not 0 <= version < 2**53:
        raise ValueError("文稿版本不正确")
    language = payload["language"]
    if not isinstance(language, str) or language not in LANGUAGES:
        raise ValueError("请选择支持的代码语言")
    for field in ("code", "answers"):
        if not isinstance(payload[field], str):
            raise ValueError("代码和答案必须是文本")
        try:
            payload[field].encode("utf-8")
        except UnicodeEncodeError as exc:
            raise ValueError("代码和答案必须是有效的 Unicode 文本") from exc

    # The predicate and increment run in one SQLite write across all workers.
    with closing(connect_auth()) as connection:
        updated = connection.execute(
            """UPDATE code_focus_publication
               SET version = version + 1, code = :code, language = :language, answers = :answers
               WHERE id = 1 AND version = :version""",
            payload,
        ).rowcount
    if not updated:
        raise PublicationConflict()
    return {**payload, "version": version + 1}
