# Embedding Retrieval Blockers: Findings and Ameliorations

Date: 2026-02-20
Context: Running `paperqa` retrieval for local papers from the Codex agent in this workspace.

## Executive summary
Embedding-based retrieval failed due to environment/network restrictions rather than paper indexing logic. The core blocker is inability to resolve/reach Hugging Face endpoints required to instantiate the sentence-transformers embedding model at query time. Additional friction came from cache path sandboxing and an unstable `uv` invocation in this environment.

## Observed findings

1. `uv` global cache access blocked by sandbox
- Error observed:
  - `failed to open file '/Users/do12/.cache/uv/sdists-v9/.git': Operation not permitted`
- Impact:
  - `uv run ...` failed before running retrieval logic.
- Workaround used:
  - Set workspace-local cache (`UV_CACHE_DIR=$(pwd)/.uvcache`).

2. `uv` runtime panic on this host invocation path
- Error observed:
  - panic from `system-configuration` crate (`Attempted to create a NULL object.`)
- Impact:
  - `uv` process aborted independent of retrieval script semantics.
- Workaround used:
  - Ran script directly via `.venv/bin/python`.

3. Embedding model initialization blocked by network/DNS constraints
- Error observed (key):
  - Failed HEAD request to:
    - `https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2/resolve/main/adapter_config.json`
  - DNS/connectivity errors (`nodename nor servname provided`), retry loop, and downstream `httpx` client failure.
- Impact:
  - Retrieval script could not instantiate `SentenceTransformer` model, so embedding query step failed.
- Important nuance:
  - Paper docs cache existed and loaded successfully (`.paperqa_cache/...pkl.gz`), but query-time embedding still requires model availability.

## Root cause analysis

Primary root cause:
- Outbound network + DNS to model host endpoints unavailable for agent-run commands.

Secondary contributing causes:
- Default cache paths (`~/.cache/uv`) not writable/readable in current sandbox profile.
- `uv` invocation instability in this environment (panic), which increases fragility even when permissions are adjusted.

## Required permission changes (administrator ask)

Minimum required for sentence-transformers/Hugging Face embeddings:
1. Outbound HTTPS + DNS:
- Allow DNS resolution.
- Allow TCP 443 egress to:
  - `huggingface.co`
  - `cdn-lfs.huggingface.co`

2. Writable cache/model directories:
- Either allow user cache locations:
  - `~/.cache/huggingface`
  - `~/.cache/torch`
  - `~/.cache/uv`
- Or require workspace-local cache dirs and grant write access there.

3. Agent command allowance (policy/prefix level):
- Permit the retrieval command pattern without repeated manual escalations.

For future OpenAI embeddings:
1. Outbound HTTPS + DNS:
- Allow TCP 443 egress to:
  - `api.openai.com`

2. Secret injection:
- Provide `OPENAI_API_KEY` securely to agent-run shell processes.
- Optional org/project env vars as needed by deployment policy.

## Ameliorations (short term)

1. Force workspace-local caches in retrieval wrappers
- Set at runtime:
  - `UV_CACHE_DIR=$(pwd)/.uvcache`
  - `HF_HOME=$(pwd)/.hf_home`
  - `TRANSFORMERS_CACHE=$(pwd)/.hf_home/transformers`
- Benefit:
  - Avoids reliance on blocked home cache paths.

2. Prefer `.venv/bin/python` over `uv run` in constrained sessions
- Benefit:
  - Avoids `uv`-specific panic path and cache friction.

3. Improve failure messaging in `retrieve_chunks.py`
- Add explicit catch around embedding model init; return actionable diagnostics:
  - offline/network blocked
  - model not present in local cache
  - exact env vars to set
- Benefit:
  - Faster operator triage; less noisy stack traces.

## Ameliorations (medium term)

1. Add explicit offline mode
- Support `--offline` (or env-driven) path with:
  - `HF_HUB_OFFLINE=1`
  - `TRANSFORMERS_OFFLINE=1`
  - `local_files_only=True`
- Behavior:
  - Fail fast with clear message if local model cache is missing.

2. Pre-seed embedding models for air-gapped/restricted environments
- Pre-download approved models to a shared local directory.
- Point runtime to that directory via cache env vars.

3. Add provider abstraction for embeddings
- Allow selecting embedding backend per environment:
  - local sentence-transformers
  - OpenAI embeddings
- Include startup checks that validate provider reachability + credentials before retrieval.

4. Add healthcheck command
- A lightweight command to verify:
  - DNS/network reachability
  - cache writability
  - embedding provider readiness
- Benefit:
  - Catch infra misconfiguration before user queries run.

## Suggested implementation tasks

1. Retrieval wrapper hardening
- Create a launcher script that always sets local cache env vars and uses `.venv/bin/python`.

2. Error-handling hardening
- Patch `retrieve_chunks.py` to trap model-load failures and print concise remediation guidance.

3. Config surface
- Add documented config for embedding provider selection + offline flag.

4. Ops documentation
- Add a runbook section in `README.md` for required domains, env vars, and cache policy.

## Risk notes

- Enabling broad network access can violate policy; domain allowlisting is preferred.
- OpenAI provider use introduces API-key management and potential cost controls (rate limits, quotas) that should be enforced centrally.
- Mixed environments (sometimes offline, sometimes online) require deterministic fallback behavior to avoid intermittent failures.

## Immediate practical recommendation

If admin changes are pending, operate in one of these two modes:
1. Fully offline local embeddings:
- Pre-seed model cache + enforce offline flags.

2. OpenAI embeddings path:
- Allow `api.openai.com` + inject `OPENAI_API_KEY` + switch provider in config.

Either mode should be accompanied by startup validation and explicit error text.
