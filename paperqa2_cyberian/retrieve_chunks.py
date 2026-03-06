"""Embedding-based chunk retrieval using paperqa's Docs + local sentence-transformers.

No LLM calls — only local embeddings. Outputs JSON to stdout.

Usage:
    uv run python retrieve_chunks.py "question" [--k 15] [--papers-dir papers papers_fetched] [--cache-dir .paperqa_cache]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path

from paperqa import Docs, Settings
from paperqa.llms import embedding_model_factory
from paperqa.settings import ParsingSettings

from paperqa2_cyberian.cache import load_docs_cache, papers_cache_key, save_docs_cache

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger(__name__)


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

    cache_key = papers_cache_key(paper_paths, embedding_name)
    docs = load_docs_cache(cache_dir, cache_key)

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

        save_docs_cache(cache_dir, cache_key, docs)
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
