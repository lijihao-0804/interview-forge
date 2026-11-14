"""Hybrid retrieval over exact passages in a single account, session and turn prefix.

Ordinary lookups return at most three sources: two by hybrid relevance, then
one by eligible dense relevance when it can improve on the third hybrid hit.
Explicit quotation requests can inspect a larger set before verifying the
answer. Ordered, comparison and occurrence queries retain individual messages.
"""
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
from itertools import chain
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
_QUOTE_CANDIDATES = 8
_FOCUS_SLOTS = 3
_VECTOR_SIZE = EMBEDDING_DIMENSION * 4
_LOCKS = tuple(threading.Lock() for _ in range(64))
_SCOPE = "m.session_id=? AND m.id<? AND m.role IN ('user','assistant')"
_OCCURRENCE_OR_COMPARISON = re.compile(
    r"最早|最初|最先|最晚|最后|最迟|先后|前后|后来|时间线|按.{0,3}(?:顺序|次序)|"
    r"比较|对比|对照|分别|区别|差异|不同|变化|变更|更改|改口|矛盾|冲突|"
    r"重复|反复|几次|几遍|多少次|多少遍|次数|频率|每次|各次|每条|逐条|所有|全部|"
    r"每一[次条]|(?:两|多)[次遍条]|多少条|几条|第[一二三四五六七八九十百千万两\d]+[次条遍]|"
    r"\b(?:compar\w*|contrast\w*|differ\w*|versus|vs|both|respectively|contradict\w*|"
    r"repeat\w*|repetit\w*|occurrence\w*|duplicates?|count(?:s|ed|ing)?|how (?:many|often)|"
    r"each|every|all|twice|multiple|changed?|changes|first|earliest|oldest|last|latest|timeline|chronolog\w*)\b", re.I,
)
_REPEATED_OCCURRENCES = re.compile(
    r"重复|反复|几次|几遍|多少[次遍条]|次数|频率|每[次条]|逐条|每一[次条]|(?:两|多)[次遍]|"
    r"第[一二三四五六七八九十百千万两\d]+[次条遍]|(?:所有|全部|每个).{0,6}(?:消息|记录|留言|出现)|"
    r"比较|对比|对照|\b(?:compar\w*|contrast\w*|repeat\w*|occurrence\w*|duplicates?|"
    r"count(?:s|ed|ing)?|how (?:many|often)|every|twice|chronolog\w*)\b", re.I,
)
_WRITER = {
    "user": re.compile(r"我(?:当时|之前|先前|最初|原先|曾经|写过|说过|提过|问过|记下|发过)|"
                       r"我的(?:原话|原句|说法|提问|留言|记录)|"
                       r"\b(?:I (?:said|wrote|noted|recorded|asked)|my (?:original )?(?:words|quote|message|note))\b", re.I),
    "assistant": re.compile(r"(?:你|助手)(?:当时|之前|先前|最初|原先|曾经|写过|说过|提过|问过|发过|建议我)|"
                            r"你的(?:原话|原句|说法|回答|建议|留言)|"
                            r"\b(?:you (?:said|wrote|advised|suggested|recommended)|your (?:original )?(?:words|quote|message|advice))\b", re.I),
}
_CLAUSE = re.compile(r"[，,。！？?!；;\n]+|(?<!\d)\.(?!\d)")
_QUESTION_CLAUSE = re.compile(
    r"怎么|怎样|如何|为何|为什么|什么|哪[个次样儿里种处项边些位]|何[时地处]|"
    r"\b(?:what|which|where|how|when|why|who|whose)\b", re.I,
)
_RECALL_INSTRUCTIONS = re.compile(
    r"消息(?:号|编号|ID)|原[话句文]|逐字|找不到|记不清|不记得|忘了|想不起|记混|"
    r"\b(?:verbatim|quot(?:e|es|ation)|message (?:id|number)|can['’]t remember|don['’]t recall)\b", re.I,
)


def _focus_query(request, query):
    """Keep one substantive question clause separate from its scene and recall instructions."""
    clauses = _CLAUSE.split(request[:512])
    if len(clauses) == 1:
        return None
    for clause in clauses:
        phrase = clause.strip()[:96]
        if (_QUESTION_CLAUSE.search(phrase) and not _RECALL_INSTRUCTIONS.search(phrase)
                and len(topic_terms(phrase)) >= 3 and phrase.casefold() != query.strip().casefold()):
            return phrase
    return None


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


def _quote_candidates(scored, dense_floor, diversify, writer):
    """Retain plausible competing sources for the separate quotation verifier."""
    selected = []
    seen = set()

    def source_key(candidate):
        return (candidate.role, candidate.digest) if diversify else candidate.message_id

    def add(candidate):
        key = source_key(candidate)
        if key not in seen:
            seen.add(key)
            selected.append(candidate)
            return True
        return False

    for _, _, candidate in scored:
        add(candidate)
        if len(selected) == 2:
            break
    # Authorship is a soft preference. A person can be quoted in either role,
    # and passages in the other role keep their global and dense slots.
    roles = {candidate.role for candidate in selected}
    if len(roles) == 1:
        alternative = next((c for _, _, c in scored if c.role not in roles), None)
        if alternative is not None:
            add(alternative)
    if writer:
        slots = 5 - sum(c.role == writer for c in selected)
        for _, _, candidate in scored:
            if candidate.role == writer and add(candidate):
                slots -= 1
                if slots == 0:
                    break
    dense_best = max((c for _, _, c in scored if c.dense is not None and c.dense >= dense_floor and
                      source_key(c) not in seen),
                     key=lambda c: c.dense, default=None)
    if dense_best is not None:
        add(dense_best)
    # A secondary answer can describe a different part of the query. Reserve
    # one slot for a still-unrepresented word from a relevance-qualified source.
    if diversify and len(selected) < _QUOTE_CANDIDATES:
        covered = set().union(*(c.terms for c in selected))
        for _, _, candidate in scored:
            if (candidate.terms - covered and (candidate.dense is None or candidate.dense >= dense_floor)
                    and add(candidate)):
                break
    for _, _, candidate in scored:
        if len(selected) == _QUOTE_CANDIDATES:
            break
        add(candidate)
    # A long source can contain a reported suggestion near the top and the
    # writer's own conclusion much later. Use spare capacity for eligible
    # non-overlapping evidence from the same original, never a duplicate
    # copy of that message with a different ID.
    if len(selected) < _QUOTE_CANDIDATES:
        starts_by_id = {c.message_id: [c.start] for c in selected}
        for _, _, candidate in scored:
            starts = starts_by_id.get(candidate.message_id)
            if starts is not None and all(abs(candidate.start - start) >= _EXCERPT_CHARS + _CHARS
                                          for start in starts):
                selected.append(candidate)
                starts.append(candidate.start)
                if len(selected) == _QUOTE_CANDIDATES:
                    break
    return selected


def _focused_candidates(scored, dense_floor):
    """Retain both semantic paraphrases and grounded alternatives to the question clause."""
    dense = sorted((c for _, _, c in scored if c.dense is not None and c.dense >= dense_floor),
                   key=lambda c: -c.dense)
    per_role = {}
    for c in dense:
        per_role.setdefault(c.role, c)
        if len(per_role) == 2:
            break
    covered = set(scored[0][2].terms)
    complementary = []
    for _, _, c in scored:
        if c.terms - covered and (c.dense is None or c.dense >= dense_floor):
            complementary.append(c)
            covered.update(c.terms)
            if len(complementary) == _FOCUS_SLOTS:
                break
    ordered = chain((scored[0][2],), per_role.values(), complementary, dense, (c for _, _, c in scored))
    distinct = {}
    for c in ordered:
        distinct.setdefault((c.role, c.digest), c)
        if len(distinct) == _QUOTE_CANDIDATES:
            break
    return list(distinct.values())


def _merge_quote_candidates(primary, focused):
    """Share eight source slots between the full topic and its focused question."""
    if not primary or not focused:
        return primary or focused
    keep = _QUOTE_CANDIDATES - _FOCUS_SLOTS
    selected = primary[:keep]
    for candidate in chain(focused, primary[keep:]):
        if len(selected) == _QUOTE_CANDIDATES:
            break
        # Small changes in the query can move the best window within a long
        # original. Keep a second range only if it adds distant evidence.
        if any(
            (c.message_id == candidate.message_id and abs(c.start - candidate.start) < _EXCERPT_CHARS + _CHARS)
            or (c.message_id != candidate.message_id and c.role == candidate.role
                and c.digest == candidate.digest)
            for c in selected
        ):
            continue
        selected.append(candidate)
    # Three distinct lookups can fill the verifier before it sees the tail
    # of any one ranking. Surface the selected relation sources directly
    # after the two leading topic matches, without changing membership.
    relation_sources = [c for c in selected[keep:] if c in focused]
    if not relation_sources:
        return selected
    return [*selected[:2], *relation_sources, *(c for c in selected[2:] if c not in relation_sources)]


def _rank(candidates, query_terms, passage_count, oldest, limit, *, diversify=True, writer=None,
          focus=False):
    if not candidates:
        return []
    frequencies = Counter(term for c in candidates for term in c.terms)
    weights = {t: math.log1p((passage_count - frequencies[t] + 0.5) / (frequencies[t] + 0.5))
               for t in query_terms}
    total_weight = sum(weights.values()) or 1.0
    best_dense = max((c.dense for c in candidates if c.dense is not None), default=-1.0)
    dense_floor = max(0.76, best_dense - 0.045)
    if limit == _QUOTE_CANDIDATES:
        # A nearly literal distractor can be much closer to the query than a
        # genuine paraphrase. The wider band admits alternatives for the
        # quotation verifier while preserving an absolute similarity floor.
        dense_floor = min(dense_floor, max(0.80, best_dense - 0.085))
    scored = []
    for c in candidates:
        lexical = sum(weights[t] for t in c.terms) / total_weight
        # E5's contrastive training concentrates even irrelevant scores near
        # .7-.8. Rank dense candidates relative to their strongest neighbour.
        dense_match = c.dense is not None and c.dense >= dense_floor
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
    if limit == _QUOTE_CANDIDATES:
        if focus:
            return _focused_candidates(scored, dense_floor)
        return _quote_candidates(scored, dense_floor, diversify, writer)
    # Ordered/multiple-occurrence requests and single-result lookups keep the
    # original per-message ordering, including distinct occurrences of a quote.
    diversify = diversify and not oldest and limit == 3
    selected = []
    source_keys = set()
    best_remaining_dense = None
    for _, _, c in scored:
        key = (c.role, c.digest) if diversify else c.message_id
        if key in source_keys:
            continue
        if not diversify or len(selected) < 2:
            selected.append(c)
            source_keys.add(key)
            if len(selected) == limit:
                break
            continue
        # Keep the third hybrid source as a fallback, including in lexical mode.
        # Compare dense evidence across messages. When both rankings select
        # the same third source its hybrid excerpt stays in place.
        if len(selected) == 2:
            selected.append(c)
        if c.dense is not None and c.dense >= dense_floor and (
            best_remaining_dense is None or c.dense > best_remaining_dense.dense
        ):
            best_remaining_dense = c
    if best_remaining_dense is not None:
        third = selected[2]
        if (third.role, third.digest) != (best_remaining_dense.role, best_remaining_dense.digest):
            selected[2] = best_remaining_dense
    return selected


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


def search_history(user_db: Path, session_id: str, cutoff: int, query: str, *, oldest=False,
                   first_only=False, request_text: str | None = None, for_quotation=False):
    """Search one session. Full request text preserves comparison and counting intent."""
    started = time.monotonic()
    request = query if request_text is None else request_text
    quote = for_quotation and not oldest and not first_only
    preserve_occurrences = _REPEATED_OCCURRENCES if quote else _OCCURRENCE_OR_COMPARISON
    diversify = not preserve_occurrences.search(request)
    focused = _focus_query(request, query) if quote and diversify else None
    queries = [query, focused] if focused else [query]
    encoder = history_encoder()
    query_vectors = []
    if encoder is not None:
        try:
            # The quantized encoder can give the same phrase a different
            # ranking depending on the length of unrelated batch neighbours.
            # Score the retained relation consistently across tool paraphrases.
            query_vectors = [encoder.encode([q], query=True)[0] for q in queries]
        except Exception as error:
            _LOG.warning("History query encoding unavailable (%s)", type(error).__name__)
            encoder = None
    uri = Path(user_db).resolve().as_uri()
    query_terms = [topic_terms(q) for q in queries]
    literals = [re.compile(re.escape(q), re.IGNORECASE) for q in queries]
    candidates = [[] for _ in queries]
    seen = embedded = last_id = 0
    scan_complete = False
    try:
        connection = sqlite3.connect(uri + ("?mode=rw" if encoder else "?mode=ro"), uri=True, timeout=1)
    except sqlite3.OperationalError:
        connection = sqlite3.connect(uri + "?mode=ro", uri=True, timeout=1)
        encoder, query_vectors = None, []
    with closing(connection) as db:
        # Legacy/read-only snapshots may not yet have the optional index.
        if encoder and not db.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='chat_history_embeddings'").fetchone():
            encoder, query_vectors = None, []
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
            scores = [iter(encoder.scores(v, vectors)) for v in query_vectors] if encoder and vectors else []
            for p in passages:
                has_vector = bool(scores) and p.vector is not None
                embedded += int(has_vector)
                seen += 1
                passage_terms = topic_terms(p.content)
                for i, (terms, literal) in enumerate(zip(query_terms, literals)):
                    dense = float(next(scores[i])) if has_vector else None
                    matches = frozenset(passage_terms & terms)
                    found = literal.search(p.content)
                    if found or matches or dense is not None:
                        candidates[i].append(Candidate(p.message_id, p.role, p.start, p.end, p.digest,
                                                       matches, found.start() if found else -1, dense))
            if len(rows) < _ROW_BATCH or capped:
                scan_complete = not capped
                break
            last_id = rows[-1][0]
    complete = scan_complete and (not query_vectors or embedded == seen)
    limit = 1 if first_only else 3
    writer = None
    if quote:
        limit = _QUOTE_CANDIDATES
        writers = [role for role, pattern in _WRITER.items() if pattern.search(request)]
        if len(writers) == 1:
            writer = writers[0]
    # An ambiguous quotation can have multiple distinct answers. Copies
    # of an unrelated answer must not crowd them out. Keep separate
    # occurrences where a user explicitly asks to count or compare them.
    ranked = [_rank(pool, terms, seen, oldest=oldest, limit=limit, diversify=diversify, writer=writer,
                    focus=i > 0)
              for i, (pool, terms) in enumerate(zip(candidates, query_terms))]
    selected = _merge_quote_candidates(*ranked) if focused else ranked[0]
    with closing(sqlite3.connect(uri + "?mode=ro", uri=True, timeout=1)) as db:
        items = _excerpts(db, selected, session_id, cutoff)
    summary = {"kind": "hybrid" if embedded else "lexical", "coverage_complete": complete,
               "passages_scanned": seen, "embedded_passages": embedded}
    if embedded:
        summary["model"] = MODEL_ID
    return {"items": items, "retrieval": summary}
