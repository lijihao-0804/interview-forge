"""Immutable assets for the local multilingual E5 encoder and its installer."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


MODEL_ID = "intfloat/multilingual-e5-small"
UPSTREAM_REVISION = "614241f622f53c4eeff9890bdc4f31cfecc418b3"
ONNX_REPOSITORY = "Xenova/multilingual-e5-small"
MODEL_REVISION = "761b726dd34fb83930e26aab4e9ac3899aa1fa78"
EMBEDDING_DIMENSION = 384
DEFAULT_MODEL_DIR = Path("data/runtime/semantic-models/multilingual-e5-small-q8")


@dataclass(frozen=True)
class ModelFile:
    source_path: str
    size: int
    sha256: str


MODEL_FILES = {
    "model.onnx": ModelFile(
        "onnx/model_quantized.onnx",
        118_308_185,
        "f80102d3f2a1229f387d3c81909990d8945513e347b0eab049f7de3c6f98c193",
    ),
    "tokenizer.json": ModelFile(
        "tokenizer.json",
        17_082_730,
        "0b44a9d7b51c3c62626640cda0e2c2f70fdacdc25bbbd68038369d14ebdf4c39",
    ),
}
