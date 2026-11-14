"""CPU-only sentence embeddings for chat recall. Loading never uses the network."""
from __future__ import annotations

import hashlib
import logging
import os
import threading
from pathlib import Path

from interview_forge.ai.embedding_spec import EMBEDDING_DIMENSION, MODEL_FILES, MODEL_REVISION

_LOG = logging.getLogger(__name__)
_LOAD = threading.Lock()
_signature = None
_instance = None
MAX_TOKENS = 256
BATCH_SIZE = 16
# Version both the embedding transform and the split used by persisted offsets.
INDEX_VERSION = f"e5:{MODEL_REVISION}:mean-l2-t256:char192-overlap40-v1"


class HistoryEncoder:
    def __init__(self, directory: Path):
        import numpy as np
        import onnxruntime as ort
        from tokenizers import Tokenizer

        for filename, spec in MODEL_FILES.items():
            with (directory / filename).open("rb") as stream:
                if hashlib.file_digest(stream, "sha256").hexdigest() != spec.sha256:
                    raise ValueError("Unexpected history encoder asset")
        self.np = np
        self.tokenizer = Tokenizer.from_file(str(directory / "tokenizer.json"))
        self.tokenizer.enable_truncation(max_length=MAX_TOKENS)
        self.tokenizer.enable_padding(pad_id=self.tokenizer.token_to_id("<pad>"), pad_token="<pad>")
        options = ort.SessionOptions()
        options.intra_op_num_threads = 1
        options.inter_op_num_threads = 1
        options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
        self.session = ort.InferenceSession(str(directory / "model.onnx"), options, providers=["CPUExecutionProvider"])
        self.inputs = {item.name for item in self.session.get_inputs()}
        # Bound competing CPU jobs per web worker; callers yield between batches.
        self.run_lock = threading.Lock()

    def encode(self, texts: list[str], *, query: bool = False) -> list[bytes]:
        """Return little-endian, normalized 384-dimensional float32 vectors."""
        np = self.np
        prefix = "query: " if query else "passage: "
        with self.run_lock:
            batch = self.tokenizer.encode_batch([prefix + text for text in texts])
            inputs = {
                "input_ids": np.asarray([item.ids for item in batch], dtype=np.int64),
                "attention_mask": np.asarray([item.attention_mask for item in batch], dtype=np.int64),
            }
            if "token_type_ids" in self.inputs:
                inputs["token_type_ids"] = np.asarray([item.type_ids for item in batch], dtype=np.int64)
            hidden, = self.session.run(["last_hidden_state"], inputs)
        mask = inputs["attention_mask"].astype(np.float32)
        mean = np.einsum("bth,bt->bh", hidden, mask) / mask.sum(axis=1, keepdims=True)
        mean /= np.maximum(np.linalg.norm(mean, axis=1, keepdims=True), 1e-12)
        if mean.shape != (len(texts), EMBEDDING_DIMENSION) or not np.isfinite(mean).all():
            raise ValueError("Invalid history embedding")
        return [vector.astype("<f4", copy=False).tobytes() for vector in mean]

    def scores(self, query_vector: bytes, vectors: list[bytes]):
        np = self.np
        query = np.frombuffer(query_vector, dtype="<f4")
        matrix = np.frombuffer(b"".join(vectors), dtype="<f4").reshape(-1, EMBEDDING_DIMENSION)
        return np.einsum("ij,j->i", matrix, query)


def history_encoder() -> HistoryEncoder | None:
    global _signature, _instance
    configured = os.environ.get("AI_HISTORY_EMBEDDING_DIR", "").strip()
    if not configured:
        return None
    directory = Path(configured).resolve()
    try:
        stats = [(directory / filename).stat() for filename in MODEL_FILES]
        signature = (directory, *((item.st_size, item.st_mtime_ns, item.st_ctime_ns) for item in stats))
    except OSError:
        return None
    with _LOAD:
        if _signature != signature:
            try:
                _instance = HistoryEncoder(directory)
            except Exception as error:
                # Native runtime failures (including unsupported CPU/library versions)
                # must leave ordinary chat and the lexical retrieval path available.
                _LOG.warning("History encoder unavailable (%s)", type(error).__name__)
                _instance = None
            _signature = signature
        return _instance
