"""Hybrid retrieval over exact passages in a single account, session and turn prefix."""
from __future__ import annotations

import hashlib
import logging
import math
import re
import sqlite3
import threading
import time
from collections import Counter, OrderedDict
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path

from interview_forge.ai.chat.relevance import topic_terms
from interview_forge.ai.embedding_spec import EMBEDDING_DIMENSION, MODEL_ID
from interview_forge.ai.history_encoder import BATCH_SIZE, INDEX_VERSION, history_encoder
from interview_forge.runtime.shared import mutex

_LOG = logging.getLogger(__name__)
_CHARS = 192
_OVERLAP = 40
_BOUNDARY = re.compile(r"[。！？；\n]|[.!?;](?=\s)")
_ROW_BATCH = 32
_ONLINE_PASSAGES = 32768
_SOFT_SECONDS = 20.0
_SCAN_SECONDS = 25.0
_EXCERPT_CHARS = 320
_VECTOR_SIZE = EMBEDDING_DIMENSION * 4
_LOCKS = tuple(threading.Lock() for _ in range(64))
_SCOPE = "m.session_id=? AND m.id<? AND m.role IN ('user','assistant')"


def _windows(text: str):
    """Split the unmodified source, preserving Unicode code-point offsets."""
    start = 0
    while start < len(text):
        end = min(start + _CHARS, len(text))
        if end < len(text):
            for match in _BOUNDARY.finditer(text, start + _CHARS // 2, end):
                end = match.end()
        yield start, end
        if end == len(text):
            break
        start = end - _OVERLAP


def _source_hash(text: str) -> bytes:
    return hashlib.sha256(text.encode("utf-8")).digest()


@dataclass(slots=True)
class Passage:
    message_id: int
    role: str
    start: int
    end: int
    digest: bytes
    content: str
    vector: bytes | None = None


@dataclass(slots=True)
class Candidate:
    message_id: int
    role: str
    start: int
    end: int
    digest: bytes
    terms: frozenset[str]
    exact: int
    dense: float | None


def _passages(db, rows, session_id, cutoff, use_vectors):
    saved = {}
    if use_vectors:
        hits = db.execute(
            f"""SELECT e.message_id, e.source_offset, e.source_end, e.vector
                 FROM chat_messages m JOIN chat_history_embeddings e ON e.message_id=m.id
                 WHERE {_SCOPE} AND m.id BETWEEN ? AND ? AND e.index_version=?
                 AND length(e.vector)=?""",
            (session_id, cutoff, rows[0][0], rows[-1][0], INDEX_VERSION, _VECTOR_SIZE),
        )
        saved = {(mid, start, end): vector for mid, start, end, vector in hits}
    for mid, role, content in rows:
        digest = _source_hash(content)
        for start, end in _windows(content):
            yield Passage(mid, role, start, end, digest, content[start:end], saved.get((mid, start, end)))


def _read_page(db, session_id, cutoff, after, use_vectors):
    # Read the originals and their cache from the same short SQLite snapshot.
    # Inference, waiting on a worker and ranking happen after the snapshot closes.
    with db:
        db.execute("BEGIN")
        rows = db.execute(
            f"SELECT m.id, m.role, m.content FROM chat_messages m WHERE {_SCOPE} AND m.id>? ORDER BY m.id LIMIT ?",
            (session_id, cutoff, after, _ROW_BATCH),
        ).fetchall()
        passages = list(_passages(db, rows, session_id, cutoff, use_vectors)) if rows else []
    return rows, passages


def _save_batch(db, batch, session_id, cutoff):
    # Inference takes place with no SQLite transaction open. Recheck the full
    # source under this brief write transaction before publishing its vectors.
    with db:
        db.execute("BEGIN IMMEDIATE")
        digests = {p.message_id: p.digest for p in batch}
        ids = ",".join("?" for _ in digests)
        valid = {
            mid for mid, content in db.execute(
                f"SELECT m.id, m.content FROM chat_messages m WHERE {_SCOPE} AND m.id IN ({ids})",
                (session_id, cutoff, *digests),
            ) if _source_hash(content) == digests[mid]
        }
        writes = db.executemany(
            """INSERT INTO chat_history_embeddings(message_id, source_offset, source_end, index_version, vector)
               VALUES (?,?,?,?,?) ON CONFLICT(message_id, source_offset) DO UPDATE SET
               source_end=excluded.source_end, index_version=excluded.index_version, vector=excluded.vector""",
            [(p.message_id, p.start, p.end, INDEX_VERSION, p.vector) for p in batch if p.message_id in valid],
        )
    return writes.rowcount


def _encode_missing(db, encoder, passages, session_id, cutoff, memo, deadline):
    missing = [p for p in passages if p.vector is None]
    saved = 0
    # Nearby lengths share a padding budget. Keep a small request-local memo
    # for identical passages (including repeated code/log blocks).
    missing.sort(key=lambda p: len(p.content))
    for pos in range(0, len(missing), BATCH_SIZE):
        if time.monotonic() >= deadline:
            break
        batch = missing[pos:pos + BATCH_SIZE]
        texts = list(dict.fromkeys(p.content for p in batch if p.content not in memo))
        if texts:
            memo.update(zip(texts, encoder.encode(texts), strict=True))
        for p in batch:
            p.vector = memo[p.content]
        saved += _save_batch(db, batch, session_id, cutoff)
        while len(memo) > 512:
            memo.popitem(last=False)
    return saved


def _index_lock(path, session_id):
    key = str(Path(path).resolve()) + ":" + session_id
    return key, _LOCKS[hash(key) % len(_LOCKS)]


def backfill_session(user_db: Path, session_id: str, cutoff: int = 2**63 - 1) -> dict:
    """Precompute all missing embeddings for one explicitly selected session."""
    encoder = history_encoder()
    if encoder is None:
        raise RuntimeError("The configured history encoder is unavailable")
    path = Path(user_db).resolve()
    key, lock = _index_lock(path, session_id)
    memo = OrderedDict()
    after = indexed = total = 0
    with closing(sqlite3.connect(path.as_uri() + "?mode=rw", uri=True, timeout=2)) as db:
        while True:
            with lock, mutex("history-embeddings", key, timeout=10):
                rows, passages = _read_page(db, session_id, cutoff, after, True)
                total += len(passages)
                indexed += _encode_missing(db, encoder, passages, session_id, cutoff, memo, float("inf"))
            if len(rows) < _ROW_BATCH:
                break
            after = rows[-1][0]
    return {"passages": total, "new_vectors": indexed, "model": MODEL_ID}


def _rank(candidates, query_terms, passage_count, oldest, limit):
    if not candidates:
        return []
    frequencies = Counter(term for c in candidates for term in c.terms)
    weights = {t: math.log1p((passage_count - frequencies[t] + 0.5) / (frequencies[t] + 0.5))
               for t in query_terms}
    total_weight = sum(weights.values()) or 1.0
    best_dense = max((c.dense for c in candidates if c.dense is not None), default=-1.0)
    scored = []
    for c in candidates:
        lexical = sum(weights[t] for t in c.terms) / total_weight
        # E5's contrastive training concentrates even irrelevant scores near
        # .7-.8. Rank dense candidates relative to their strongest neighbour.
        dense_match = c.dense is not None and c.dense >= max(0.76, best_dense - 0.045)
        if c.exact < 0 and not dense_match and (not c.terms or lexical < 0.12):
            continue
        score = (c.dense if c.dense is not None else 0.65) + 0.10 * lexical + 0.15 * (c.exact >= 0)
        scored.append((score, lexical, c))
    if not scored:
        return []
    # Distinguish a plausible occurrence from an earlier unrelated passage.
    # Apply chronology to supported candidates before cutting to top-k.
    if oldest:
        best = max(s for s, _, _ in scored)
        scored = [(s, lexical, c) for s, lexical, c in scored if c.exact >= 0 or s >= best - 0.025
                  or (c.dense is not None and c.dense >= max(0.80, best_dense - 0.025))
                  or (c.dense is None and lexical >= 0.55)]
        scored.sort(key=lambda pair: (pair[2].message_id, -pair[0], pair[2].start))
    else:
        scored.sort(key=lambda pair: (-pair[0], pair[2].message_id, pair[2].start))
    unique = {}
    for _, _, c in scored:
        unique.setdefault(c.message_id, c)
        if len(unique) == limit:
            break
    return list(unique.values())


def _excerpts(db, sources, session_id, cutoff):
    items = []
    for c in sources:
        row = db.execute(
            f"SELECT m.role, m.content FROM chat_messages m WHERE {_SCOPE} AND m.id=?",
            (session_id, cutoff, c.message_id),
        ).fetchone()
        if row is None or row[0] != c.role or _source_hash(row[1]) != c.digest:
            continue
        content = row[1]
        # Give the model the original sentence with some surrounding context.
        # A literal match near a window boundary must remain visible.
        anchor = c.start + c.exact if c.exact >= 0 else (c.start + c.end) // 2
        start = max(0, min(anchor - _EXCERPT_CHARS // 2, len(content) - _EXCERPT_CHARS))
        end = min(start + _EXCERPT_CHARS, len(content))
        item = {"message_id": c.message_id, "role": c.role, "offset": start, "excerpt": content[start:end]}
        if end < len(content):
            item["next_offset"] = end
        items.append(item)
    return items


def search_history(user_db: Path, session_id: str, cutoff: int, query: str, *, oldest=False, first_only=False):
    """Serve one scoped search, indexing missing vectors oldest first up to a deadline."""
    started = time.monotonic()
    encoder = history_encoder()
    query_vector = None
    if encoder is not None:
        try:
            query_vector, = encoder.encode([query], query=True)
        except Exception as error:
            _LOG.warning("History query encoding unavailable (%s)", type(error).__name__)
            encoder = None
    uri = Path(user_db).resolve().as_uri()
    terms = topic_terms(query)
    literal = re.compile(re.escape(query), re.IGNORECASE)
    candidates = []
    seen = embedded = last_id = 0
    scan_complete = False
    try:
        connection = sqlite3.connect(uri + ("?mode=rw" if encoder else "?mode=ro"), uri=True, timeout=1)
    except sqlite3.OperationalError:
        connection = sqlite3.connect(uri + "?mode=ro", uri=True, timeout=1)
        encoder = query_vector = None
    with closing(connection) as db:
        # Legacy/read-only snapshots may not yet have the optional index.
        if encoder and not db.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='chat_history_embeddings'").fetchone():
            encoder = query_vector = None
        memo = OrderedDict()
        key, lock = _index_lock(user_db, session_id)
        while seen < _ONLINE_PASSAGES and time.monotonic() - started < _SCAN_SECONDS:
            rows, passages = _read_page(db, session_id, cutoff, last_id, encoder is not None)
            if not rows:
                scan_complete = True
                break
            remaining = _ONLINE_PASSAGES - seen
            if encoder and any(p.vector is None for p in passages[:remaining]) and time.monotonic() - started < _SOFT_SECONDS:
                # A competing worker may already own the cold build. Never hold a
                # database lock while waiting for it or while running the encoder.
                acquired = lock.acquire(timeout=min(1, max(0, started + _SOFT_SECONDS - time.monotonic())))
                try:
                    if acquired:
                        with mutex("history-embeddings", key, timeout=1):
                            rows, passages = _read_page(db, session_id, cutoff, last_id, True)
                            _encode_missing(db, encoder, passages[:remaining], session_id, cutoff, memo, started + _SOFT_SECONDS)
                except (TimeoutError, sqlite3.OperationalError):
                    pass  # Current source is still eligible for lexical ranking.
                except Exception as error:
                    _LOG.warning("History passage encoding unavailable (%s)", type(error).__name__)
                    encoder = None
                finally:
                    if acquired:
                        lock.release()
            capped = len(passages) > remaining
            passages = passages[:remaining]
            vectors = [p.vector for p in passages if p.vector is not None]
            scores = iter(encoder.scores(query_vector, vectors)) if encoder and vectors else iter(())
            for p in passages:
                dense = float(next(scores)) if encoder and p.vector is not None else None
                embedded += int(dense is not None)
                seen += 1
                matches = frozenset(topic_terms(p.content) & terms)
                found = literal.search(p.content)
                if found or matches or dense is not None:
                    candidates.append(Candidate(p.message_id, p.role, p.start, p.end, p.digest,
                                                matches, found.start() if found else -1, dense))
            if len(rows) < _ROW_BATCH or capped:
                scan_complete = not capped
                break
            last_id = rows[-1][0]
    complete = scan_complete and (query_vector is None or embedded == seen)
    selected = _rank(candidates, terms, seen, oldest=oldest, limit=1 if first_only else 3)
    with closing(sqlite3.connect(uri + "?mode=ro", uri=True, timeout=1)) as db:
        items = _excerpts(db, selected, session_id, cutoff)
    summary = {"kind": "hybrid" if embedded else "lexical", "coverage_complete": complete,
               "passages_scanned": seen, "embedded_passages": embedded}
    if embedded:
        summary["model"] = MODEL_ID
    return {"items": items, "retrieval": summary}
