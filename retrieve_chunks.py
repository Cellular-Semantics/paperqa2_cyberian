"""Embedding-based chunk retrieval using paperqa's Docs + local sentence-transformers.

No LLM calls — only local embeddings. Outputs JSON to stdout.

Usage:
    uv run python retrieve_chunks.py "question" [--k 15] [--papers-dir papers papers_fetched] [--cache-dir .paperqa_cache]
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import logging
import pickle
import sys
import zlib
from pathlib import Path

from paperqa import Docs, Settings
from paperqa.llms import embedding_model_factory
from paperqa.settings import ParsingSettings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Cache helpers (duplicated from main.py — they're small)
# ---------------------------------------------------------------------------

def _papers_cache_key(paper_paths: list[Path], embedding_model: str) -> str:
    """SHA-256 of sorted (name, size, mtime_ns) for each paper plus the model name."""
    parts = sorted(
        f"{p.name}:{p.stat().st_size}:{p.stat().st_mtime_ns}"
        for p in paper_paths
    )
    parts.append(embedding_model)
    return hashlib.sha256("|".join(parts).encode()).hexdigest()


def _load_docs_cache(cache_dir: Path | None, key: str) -> Docs | None:
    if cache_dir is None:
        return None
    path = cache_dir / f"{key}.pkl.gz"
    if not path.exists():
        return None
    logger.info("Loading docs from cache %s", path)
    return pickle.loads(zlib.decompress(path.read_bytes()))  # noqa: S301


def _save_docs_cache(cache_dir: Path | None, key: str, docs: Docs) -> None:
    if cache_dir is None:
        return
    cache_dir.mkdir(exist_ok=True)
    path = cache_dir / f"{key}.pkl.gz"
    path.write_bytes(zlib.compress(pickle.dumps(docs)))
    logger.info("Saved docs cache → %s", path)


# ---------------------------------------------------------------------------
# Core retrieval
# ---------------------------------------------------------------------------

async def retrieve(
    question: str,
    paper_paths: list[Path],
    k: int = 15,
    embedding_name: str = "st-all-MiniLM-L6-v2",
    cache_dir: Path | None = Path(".paperqa_cache"),
) -> list[dict]:
    """Index papers (cached) and retrieve top-k chunks by embedding similarity."""

    if not paper_paths:
        return []

    settings = Settings(
        embedding=embedding_name,
        parsing=ParsingSettings(
            use_doc_details=False,
            multimodal=False,
        ),
    )

    cache_key = _papers_cache_key(paper_paths, embedding_name)
    docs = _load_docs_cache(cache_dir, cache_key)

    if docs is None:
        docs = Docs()
        for path in paper_paths:
            logger.info("Adding %s …", path.name)
            try:
                clean = path.stem.replace(".", "_").replace("-", "_")
                await docs.aadd(
                    path,
                    citation=f"{clean} (unknown year). {clean}.",
                    docname=clean,
                    settings=settings,
                )
            except Exception as exc:
                logger.warning("Skipping %s — %s", path.name, exc)

        if not docs.docs:
            logger.error("No documents were indexed successfully.")
            return []

        _save_docs_cache(cache_dir, cache_key, docs)
    else:
        logger.info("Cache hit — skipping indexing (%d doc(s))", len(docs.docs))

    emb = embedding_model_factory(embedding_name)
    texts = await docs.retrieve_texts(
        query=question,
        k=k,
        settings=settings,
        embedding_model=emb,
    )

    results = []
    for t in texts:
        results.append({
            "text": t.text,
            "name": t.name,
            "doc_citation": t.doc.citation if hasattr(t.doc, "citation") else "",
            "doc_name": t.doc.docname if hasattr(t.doc, "docname") else "",
        })

    return results


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Retrieve top-k chunks via embedding similarity (no LLM calls)."
    )
    parser.add_argument("question", help="The research question")
    parser.add_argument("--k", type=int, default=15, help="Number of chunks to retrieve (default: 15)")
    parser.add_argument(
        "--papers-dir", nargs="+", default=["papers", "papers_fetched"],
        help="Directories to search for papers (default: papers papers_fetched)",
    )
    parser.add_argument(
        "--cache-dir", default=".paperqa_cache",
        help="Cache directory for indexed docs (default: .paperqa_cache)",
    )
    args = parser.parse_args()

    # Collect all PDFs and text files from all paper dirs
    paper_paths: list[Path] = []
    for d in args.papers_dir:
        dirpath = Path(d)
        if dirpath.exists():
            paper_paths.extend(sorted(dirpath.glob("*.pdf")))
            paper_paths.extend(sorted(dirpath.glob("*.txt")))

    if not paper_paths:
        logger.error("No papers found in: %s", args.papers_dir)
        print("[]")
        sys.exit(0)

    logger.info("Found %d paper(s) in %s", len(paper_paths), args.papers_dir)

    cache_dir = Path(args.cache_dir) if args.cache_dir else None
    results = asyncio.run(retrieve(args.question, paper_paths, args.k, cache_dir=cache_dir))

    print(json.dumps(results, ensure_ascii=False))


if __name__ == "__main__":
    main()
