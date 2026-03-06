"""Experiment: run a full paperqa2 RAG pipeline with Cyberian/codex as the LLM backend.

Usage:
    # 1. Start one or more codex agentapi servers (in separate terminals):
    #    agentapi server codex --port 3284 -- --dangerously-bypass-approvals-and-sandbox
    #    agentapi server codex --port 3285 -- --dangerously-bypass-approvals-and-sandbox
    #
    # 2. Drop PDF papers into papers/
    #
    # 3. Run:
    #    uv run python main.py "What are the main findings?"
    #    uv run python main.py  (uses default question)

Configuration via environment variables:
    AGENTAPI_HOST     agentapi hostname (default: localhost)
    AGENTAPI_PORT     agentapi port when using a single instance (default: 3284)
    AGENTAPI_PORTS    comma-separated ports for parallel instances, e.g. "3284,3285,3286"
                      overrides AGENTAPI_PORT when set; unreachable ports are skipped
    AGENTAPI_TIMEOUT  max seconds to wait per LLM call (default: 300)
    EMBEDDING_MODEL   sentence-transformer model name, st- prefix added automatically
                      (default: all-MiniLM-L6-v2)
                      Set to "text-embedding-3-small" to use OpenAI embeddings instead
                      (requires OPENAI_API_KEY).
    CACHE_DIR         directory for the embedding cache (default: .paperqa_cache)
                      Set to "" to disable caching.
"""

from __future__ import annotations

import asyncio
import logging
import os
import subprocess
import sys
import time
from pathlib import Path

import httpx
from paperqa import Docs, Settings
from paperqa.settings import ParsingSettings

from paperqa2_cyberian.cache import load_docs_cache, papers_cache_key, save_docs_cache
from paperqa2_cyberian.cyberian_llm import CyberianLLMModel

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
PAPERS_DIR = Path("papers")
DEFAULT_QUESTION = "What are the main findings of these papers?"

AGENTAPI_HOST = os.environ.get("AGENTAPI_HOST", "localhost")
AGENTAPI_PORT = int(os.environ.get("AGENTAPI_PORT", "3284"))
AGENTAPI_TIMEOUT = int(os.environ.get("AGENTAPI_TIMEOUT", "300"))

_ports_env = os.environ.get("AGENTAPI_PORTS", "")
AGENTAPI_PORTS: list[int] = (
    [int(p.strip()) for p in _ports_env.split(",") if p.strip()]
    if _ports_env
    else [AGENTAPI_PORT]
)

# Use a local sentence-transformer so we make zero OpenAI embedding calls.
# paperqa2 recognises the "st-" prefix and uses sentence-transformers locally.
_embedding_env = os.environ.get("EMBEDDING_MODEL", "all-MiniLM-L6-v2")
EMBEDDING_MODEL = (
    _embedding_env
    if _embedding_env.startswith(("st-", "text-embedding"))
    else f"st-{_embedding_env}"
)

_cache_dir_env = os.environ.get("CACHE_DIR", ".paperqa_cache")
CACHE_DIR: Path | None = Path(_cache_dir_env) if _cache_dir_env else None


# ---------------------------------------------------------------------------
# agentapi server helpers
# ---------------------------------------------------------------------------

def _is_server_running(host: str = AGENTAPI_HOST, port: int = AGENTAPI_PORT) -> bool:
    try:
        r = httpx.get(f"http://{host}:{port}/status", timeout=2.0)
        return r.status_code == 200
    except Exception:
        return False


def _resolve_live_ports(host: str, ports: list[int]) -> list[int]:
    """Return only the ports that have a reachable agentapi server; warn about the rest."""
    live = []
    for port in ports:
        if _is_server_running(host, port):
            live.append(port)
        else:
            logger.warning("agentapi not reachable on %s:%d — skipping", host, port)
    return live


def _start_agentapi_server(
    port: int = AGENTAPI_PORT,
    workdir: str | Path = ".",
    startup_timeout: int = 60,
) -> subprocess.Popen:
    """Launch `agentapi server codex` and wait until the server responds."""
    workdir = Path(workdir).resolve()
    cmd = [
        "agentapi", "server", "codex",
        "--port", str(port),
        "--", "--dangerously-bypass-approvals-and-sandbox",
    ]
    logger.info("Starting agentapi: %s (workdir=%s)", " ".join(cmd), workdir)
    proc = subprocess.Popen(
        cmd,
        cwd=str(workdir),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )

    deadline = time.monotonic() + startup_timeout
    while time.monotonic() < deadline:
        if _is_server_running(port=port):
            logger.info("agentapi server ready on port %d (pid %d)", port, proc.pid)
            return proc
        if proc.poll() is not None:
            out, _ = proc.communicate()
            raise RuntimeError(
                f"agentapi process exited early (rc={proc.returncode}):\n"
                + (out.decode(errors="replace") if out else "")
            )
        time.sleep(1.0)

    proc.terminate()
    raise RuntimeError(
        f"agentapi server did not respond within {startup_timeout}s on port {port}"
    )


# ---------------------------------------------------------------------------
# Main experiment
# ---------------------------------------------------------------------------

async def run_experiment(question: str, paper_paths: list[Path]) -> None:
    """Index *paper_paths* and answer *question* using Cyberian/codex."""

    # Check which requested ports are actually reachable; skip the rest.
    live_ports = _resolve_live_ports(AGENTAPI_HOST, AGENTAPI_PORTS)
    if not live_ports:
        logger.error(
            "No reachable agentapi servers on %s ports %s. Aborting.",
            AGENTAPI_HOST, AGENTAPI_PORTS,
        )
        return

    llm = CyberianLLMModel(
        host=AGENTAPI_HOST,
        ports=live_ports,
        timeout=AGENTAPI_TIMEOUT,
    )
    logger.info(
        "LLM backend: %s  (agentapi %s ports %s)",
        llm.name, llm.host, llm.ports,
    )
    logger.info("Embedding model: %s", EMBEDDING_MODEL)

    # Settings only drives embedding + parsing; LLM calls use our custom model.
    # We supply placeholder model strings — they are overridden by llm_model= kwargs.
    # use_doc_details=False: skip the JSON citation-extraction LLM call per PDF —
    # codex returns garbled output for structured prompts, and the call is unnecessary
    # for the retrieval experiment.
    settings = Settings(
        llm="gpt-4o-2024-11-20",         # placeholder — overridden by llm_model=
        summary_llm="gpt-4o-2024-11-20", # placeholder — overridden by summary_llm_model=
        embedding=EMBEDDING_MODEL,
        verbosity=1,
        parsing=ParsingSettings(
            use_doc_details=False,
            multimodal=False,      # disable image/table enrichment (calls enrichment LLM per chunk)
        ),
    )

    # Try loading a cached Docs object (embeddings included) to skip re-indexing.
    cache_key = papers_cache_key(paper_paths, EMBEDDING_MODEL)
    docs = load_docs_cache(CACHE_DIR, cache_key)

    if docs is None:
        docs = Docs()

        # Index all papers
        for path in paper_paths:
            logger.info("Adding %s …", path.name)
            try:
                # Skip LLM citation-generation (codex treats it as a coding task).
                # Supply a clean docname + minimal citation string directly.
                clean = path.stem.replace(".", "_").replace("-", "_")
                await docs.aadd(
                    path,
                    citation=f"{clean} (unknown year). {clean}.",
                    docname=clean,
                    settings=settings,
                    llm_model=llm,
                )
            except Exception as exc:
                logger.warning("Skipping %s — %s", path.name, exc)

        if not docs.docs:
            logger.error("No documents were indexed successfully. Aborting.")
            return

        save_docs_cache(CACHE_DIR, cache_key, docs)
    else:
        logger.info("Cache hit — skipping indexing (%d doc(s))", len(docs.docs))

    logger.info("Indexed %d document(s). Running query …", len(docs.docs))
    logger.info("Question: %s", question)

    session = await docs.aquery(
        question,
        settings=settings,
        llm_model=llm,
        summary_llm_model=llm,
    )

    print("\n" + "=" * 70)
    print("ANSWER")
    print("=" * 70)
    print(session.answer)
    print("\n" + "-" * 70)
    print("REFERENCES")
    print("-" * 70)
    print(session.references or "(none)")
    print("=" * 70 + "\n")


def main() -> None:
    question = " ".join(sys.argv[1:]).strip() or DEFAULT_QUESTION

    papers = sorted(PAPERS_DIR.glob("*.pdf")) if PAPERS_DIR.exists() else []
    if not papers:
        print(
            f"No PDF files found in {PAPERS_DIR}/\n"
            "Add at least one PDF and retry.\n"
            "Example:\n"
            "  mkdir -p papers && cp myarticle.pdf papers/\n"
            "  uv run python main.py 'What are the main conclusions?'"
        )
        sys.exit(1)

    managed_proc: subprocess.Popen | None = None
    try:
        # Auto-start a single server only when no AGENTAPI_PORTS override is set
        # and the default port isn't already running.
        if len(AGENTAPI_PORTS) == 1 and not _is_server_running(AGENTAPI_HOST, AGENTAPI_PORTS[0]):
            managed_proc = _start_agentapi_server(port=AGENTAPI_PORTS[0])
        else:
            logger.info(
                "Using agentapi on %s port(s) %s",
                AGENTAPI_HOST, AGENTAPI_PORTS,
            )

        asyncio.run(run_experiment(question, papers))

    finally:
        if managed_proc is not None:
            logger.info("Stopping agentapi server (pid %d) …", managed_proc.pid)
            managed_proc.terminate()
            try:
                managed_proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                managed_proc.kill()


if __name__ == "__main__":
    main()
