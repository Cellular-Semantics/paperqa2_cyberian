"""Embedding cache helpers shared by main.py and retrieve_chunks.py."""

from __future__ import annotations

import hashlib
import logging
import pickle
import zlib
from pathlib import Path

from paperqa import Docs

logger = logging.getLogger(__name__)


def papers_cache_key(paper_paths: list[Path], embedding_model: str) -> str:
    """SHA-256 of sorted (name, size, mtime_ns) for each paper plus the model name."""
    parts = sorted(
        f"{p.name}:{p.stat().st_size}:{p.stat().st_mtime_ns}"
        for p in paper_paths
    )
    parts.append(embedding_model)
    return hashlib.sha256("|".join(parts).encode()).hexdigest()


def load_docs_cache(cache_dir: Path | None, key: str) -> Docs | None:
    if cache_dir is None:
        return None
    path = cache_dir / f"{key}.pkl.gz"
    if not path.exists():
        return None
    logger.info("Loading docs from cache %s", path)
    return pickle.loads(zlib.decompress(path.read_bytes()))  # noqa: S301


def save_docs_cache(cache_dir: Path | None, key: str, docs: Docs) -> None:
    if cache_dir is None:
        return
    cache_dir.mkdir(exist_ok=True)
    path = cache_dir / f"{key}.pkl.gz"
    path.write_bytes(zlib.compress(pickle.dumps(docs)))
    logger.info("Saved docs cache → %s", path)
