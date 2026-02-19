# Embedding cache

## Context

`run_experiment()` calls `docs.aadd()` for every PDF on every run, re-embedding all chunks from scratch each time — even when the papers haven't changed. The fix is to pickle the fully-built `Docs` object after the first indexing pass and reload it on subsequent runs, skipping `aadd()` entirely when nothing has changed.

## Approach

Use `pickle` + `zlib.compress` (same format as paperqa2's own agent-layer cache).

**Cache key**: SHA-256 of sorted `(filename, file_size, mtime_ns)` for all PDFs **plus** `EMBEDDING_MODEL`. Changing, adding, or removing any paper — or changing the embedding model — invalidates the cache automatically.

**Cache location**: `.paperqa_cache/<hash>.pkl.gz` in the project working directory. Overridable via `CACHE_DIR` env var.

## Changes — `main.py` only

### 1. Imports
Add `hashlib, pickle, zlib` to the existing stdlib imports.

### 2. Config section
Add after the existing env-var block:
```python
CACHE_DIR = Path(os.environ.get("CACHE_DIR", ".paperqa_cache"))
```

### 3. Three new helpers (after agentapi server helpers)
```python
def _papers_cache_key(paper_paths: list[Path], embedding_model: str) -> str:
    parts = sorted(
        f"{p.name}:{p.stat().st_size}:{p.stat().st_mtime_ns}"
        for p in paper_paths
    )
    parts.append(embedding_model)
    return hashlib.sha256("|".join(parts).encode()).hexdigest()

def _load_docs_cache(key: str) -> Docs | None:
    path = CACHE_DIR / f"{key}.pkl.gz"
    if not path.exists():
        return None
    logger.info("Loading docs from cache %s", path)
    return pickle.loads(zlib.decompress(path.read_bytes()))

def _save_docs_cache(key: str, docs: Docs) -> None:
    CACHE_DIR.mkdir(exist_ok=True)
    path = CACHE_DIR / f"{key}.pkl.gz"
    path.write_bytes(zlib.compress(pickle.dumps(docs)))
    logger.info("Saved docs cache to %s", path)
```

### 4. In `run_experiment()`, wrap the indexing loop
Replace:
```python
docs = Docs()

# Index all papers
for path in paper_paths:
    ...
```
With:
```python
cache_key = _papers_cache_key(paper_paths, EMBEDDING_MODEL)
docs = _load_docs_cache(cache_key)
if docs is None:
    docs = Docs()
    for path in paper_paths:
        ...  # existing aadd loop unchanged
    if docs.docs:
        _save_docs_cache(cache_key, docs)
else:
    logger.info("Cache hit — skipping indexing (%d doc(s))", len(docs.docs))
```

### 5. Module docstring
Add `CACHE_DIR` to the env-var table (default `.paperqa_cache`).

## Verification
- First run: cache miss → indexes PDFs → saves `.paperqa_cache/<hash>.pkl.gz` → runs query
- Second run (same papers): "Cache hit" logged → no `aadd` calls → runs query faster
- Add/remove/modify a PDF → new hash → cache miss → re-indexes
- Change `EMBEDDING_MODEL` → new hash → cache miss → re-indexes

## Notes
- paperqa2's `Docs` is a plain Pydantic model; `pickle` round-trips correctly including the numpy embedding arrays in `NumpyVectorStore`
- The agent-layer `get_directory_index()` path (in `paperqa/agents/search.py`) provides a more integrated cache but requires using the full agent API rather than `Docs.aadd()` directly — out of scope for this experiment
