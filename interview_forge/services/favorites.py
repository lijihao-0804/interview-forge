"""收藏功能：题目与书架章节的统一收藏，支持按模块筛选。

数据流：
  · 写入时冗余保存 module_id/title/url，收藏中心无需回表解析章节归属
  · 题目 target_type='problem'（target_id 为题目 id 的字符串）
  · 章节 target_type='content'（target_id 形如 "<module_id>:<chapter_id>"）
"""
from __future__ import annotations

from typing import Any

from interview_forge.core.runtime import server_runtime


def _now() -> str:
    return server_runtime.now_parts()[0]

def _connect(db_path=None):
    """统一连接入口：db_path 为 None 时使用默认用户库。"""
    if db_path is None:
        return server_runtime.connect()
    return server_runtime.connect(db_path)



def add_favorite(
    target_type: str,
    target_id: str,
    module_id: str = "",
    module_title: str = "",
    title: str = "",
    url: str = "",
    note: str = "",
    db_path=None,
) -> dict[str, Any]:
    """收藏（幂等：重复收藏只更新时间与元信息，不报错）。"""
    if target_type not in ("problem", "content"):
        raise ValueError("target_type 必须是 problem 或 content")
    if not str(target_id).strip():
        raise ValueError("target_id 不能为空")
    conn = _connect(db_path)
    try:
        conn.execute(
            """INSERT INTO favorites(target_type, target_id, module_id, module_title, title, url, note, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(target_type, target_id) DO UPDATE SET
                 module_id=excluded.module_id,
                 module_title=CASE WHEN excluded.module_title<>'' THEN excluded.module_title ELSE favorites.module_title END,
                 title=CASE WHEN excluded.title<>'' THEN excluded.title ELSE favorites.title END,
                 url=CASE WHEN excluded.url<>'' THEN excluded.url ELSE favorites.url END,
                 note=CASE WHEN excluded.note<>'' THEN excluded.note ELSE favorites.note END""",
            (target_type, str(target_id), module_id, module_title, title, url, note, _now()),
        )
        conn.commit()
    finally:
        conn.close()
    return {"target_type": target_type, "target_id": str(target_id), "favorited": True}


def remove_favorite(target_type: str, target_id: str, db_path=None) -> dict[str, Any]:
    conn = _connect(db_path)
    try:
        conn.execute(
            "DELETE FROM favorites WHERE target_type=? AND target_id=?",
            (target_type, str(target_id)),
        )
        conn.commit()
    finally:
        conn.close()
    return {"target_type": target_type, "target_id": str(target_id), "favorited": False}


def toggle_favorite(
    target_type: str,
    target_id: str,
    module_id: str = "",
    module_title: str = "",
    title: str = "",
    url: str = "",
    db_path=None,
) -> dict[str, Any]:
    """切换收藏状态，返回切换后的状态。"""
    conn = _connect(db_path)
    try:
        hit = conn.execute(
            "SELECT 1 FROM favorites WHERE target_type=? AND target_id=?",
            (target_type, str(target_id)),
        ).fetchone()
    finally:
        conn.close()
    if hit:
        return remove_favorite(target_type, target_id, db_path)
    return add_favorite(target_type, target_id, module_id, module_title, title, url, db_path=db_path)


def list_favorites(module_id: str = "", target_type: str = "", db_path=None) -> list[dict[str, Any]]:
    """列出收藏，可按模块与类型筛选（module_id / target_type 为空表示不过滤）。"""
    sql = ("SELECT target_type, target_id, module_id, module_title, title, url, note, created_at "
           "FROM favorites WHERE 1=1")
    params: list[Any] = []
    if module_id:
        sql += " AND module_id=?"
        params.append(module_id)
    if target_type:
        sql += " AND target_type=?"
        params.append(target_type)
    sql += " ORDER BY created_at DESC, target_id"
    conn = _connect(db_path)
    try:
        rows = conn.execute(sql, params).fetchall()
    finally:
        conn.close()
    return [dict(row) for row in rows]


def favorite_ids(target_type: str = "", db_path=None) -> list[str]:
    """返回已收藏的 target_id 列表，供前端标记按钮状态。"""
    if target_type:
        sql = "SELECT target_type || ':' || target_id AS key FROM favorites WHERE target_type=?"
        params = (target_type,)
    else:
        sql = "SELECT target_type || ':' || target_id AS key FROM favorites"
        params = ()
    conn = _connect(db_path)
    try:
        return [str(r["key"]) for r in conn.execute(sql, params).fetchall()]
    finally:
        conn.close()


def favorite_stats(db_path=None) -> dict[str, int]:
    """按模块统计收藏数，供收藏中心的筛选胶囊显示计数。"""
    conn = _connect(db_path)
    try:
        rows = conn.execute(
            "SELECT module_id, COUNT(*) AS n FROM favorites GROUP BY module_id"
        ).fetchall()
    finally:
        conn.close()
    out = {"__total__": 0}
    for r in rows:
        key = str(r["module_id"] or "")
        out[key] = int(r["n"])
        out["__total__"] += int(r["n"])
    return out
