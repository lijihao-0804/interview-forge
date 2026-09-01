"""增量构建缓存（InterviewForge 专用）。

思路：对“源文件 → 输出文件”的逐文件渲染，记录源文件内容哈希与输出清单；
再次构建时源哈希未变且输出都在 → 跳过渲染。缓存文件放在项目根
（.build-cache.json，已在 .gitignore 中排除）。

失效规则：
- 源文件内容变化（sha256）→ 该条目标记需要重建；
- 输出文件缺失 → 重建；
- 构建脚本自身哈希或资源版本（ASSET_VERSION）变化 → 整体清空缓存全量重建。

聚合产物（index.html / manifest.json / search-index.json / README 等）不参与
增量：它们依赖全局数据，渲染量小，始终全量重建。
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

CACHE_VERSION = 1


def file_sha256(path: Path) -> str:
    """流式计算文件 sha256，避免大文件一次性读入内存。"""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_cache(root: Path) -> dict[str, object]:
    path = root / ".build-cache.json"
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def save_cache(root: Path, cache: dict[str, object]) -> None:
    (root / ".build-cache.json").write_text(
        json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8"
    )


def entries(cache: dict[str, object]) -> dict[str, object]:
    return cache.setdefault("entries", {})


def needs_rebuild(cache: dict[str, object], key: str, sha: str, outputs: list[str], root: Path) -> bool:
    """源哈希未变且全部输出存在 → False（跳过）；否则 True（重建）。"""
    entry = entries(cache).get(key)
    if not entry or entry.get("sha") != sha:
        return True
    for rel_out in outputs:
        if not (root / rel_out).exists():
            return True
    return False


def mark_built(cache: dict[str, object], key: str, sha: str, outputs: list[str]) -> None:
    entries(cache)[key] = {"sha": sha, "outputs": outputs}


def invalidate_on_tool_change(cache: dict[str, object], tool_path: Path) -> dict[str, object]:
    """构建脚本变化时整体失效，返回新缓存骨架。

    ASSET_VERSION 是各脚本内的代码常量，改动必然改变工具指纹（tools/*.py 联合
    哈希），因此无需单独比对资源版本——两个构建脚本各自的 ASSET_VERSION 不同
    也不会互相误判失效。
    """
    tool_sha = tools_fingerprint(tool_path)
    if cache.get("tool_sha") != tool_sha or cache.get("version") != CACHE_VERSION:
        return {
            "version": CACHE_VERSION,
            "tool_sha": tool_sha,
            "entries": {},
        }
    return cache


def tools_fingerprint(tool_path: Path) -> str:
    """tools 目录下全部 .py 的联合哈希。

    三个构建脚本（build_hot100 / build_library / build_html_site）共用同一个
    .build-cache.json，必须用同一把“工具指纹”判断构建代码是否变化：
    任一 .py 改动 → 指纹变化 → 整链全量重建；全部未动 → 缓存跨脚本保持有效。
    """
    tools_dir = tool_path.parent
    hasher = hashlib.sha256()
    for source in sorted(tools_dir.glob("*.py")):
        hasher.update(source.read_bytes())
    return hasher.hexdigest()
