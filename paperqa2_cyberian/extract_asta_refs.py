"""Extract and deduplicate refMentions from ASTA snippet_search responses.

Provides structured extraction of Semantic Scholar corpus IDs from
snippet_search results, with sentence-level context and deduplication.
"""

from __future__ import annotations

import json
import sys
import urllib.request
import urllib.error
from dataclasses import dataclass, field


@dataclass
class RefMention:
    """A single reference mention extracted from a snippet."""

    corpus_id: str
    source_paper_corpus_id: str
    source_paper_title: str
    snippet_text: str
    sentence: str | None
    section: str | None
    char_start: int
    char_end: int
    snippet_score: float


@dataclass
class ExtractionResult:
    """Aggregated extraction result across all snippets."""

    query: str
    unique_corpus_ids: list[str] = field(default_factory=list)
    ref_mentions: list[RefMention] = field(default_factory=list)
    unresolved_count: int = 0
    source_papers: dict[str, str] = field(default_factory=dict)
    stats: dict[str, int] = field(default_factory=dict)


def _find_sentence_for_ref(
    annotations: dict | None,
    ref_start: int,
    ref_end: int,
    snippet_text: str,
) -> str | None:
    """Find the sentence containing a ref mention using sentence annotations."""
    if annotations is None:
        return None
    sentences = annotations.get("sentences")
    if not sentences:
        return None
    for sent in sentences:
        s, e = sent["start"], sent["end"]
        if s <= ref_start and ref_end <= e:
            return snippet_text[s:e]
    return None


def _extract_from_snippet(snippet_data: dict, query: str) -> list[RefMention]:
    """Extract RefMentions from a single snippet search result item."""
    paper = snippet_data.get("paper", {})
    source_corpus_id = str(paper.get("corpusId", ""))
    source_title = paper.get("title", "")

    snippet = snippet_data.get("snippet", {})
    text = snippet.get("text", "")
    section = snippet.get("section")
    score = snippet_data.get("score", 0.0)

    annotations = snippet.get("annotations")
    if annotations is None:
        return []

    ref_mentions_raw = annotations.get("refMentions")
    if not ref_mentions_raw:
        return []

    results = []
    for rm in ref_mentions_raw:
        corpus_id = rm.get("matchedPaperCorpusId")
        if corpus_id is None:
            continue
        start = rm.get("start", 0)
        end = rm.get("end", 0)
        sentence = _find_sentence_for_ref(annotations, start, end, text)
        results.append(
            RefMention(
                corpus_id=str(corpus_id),
                source_paper_corpus_id=source_corpus_id,
                source_paper_title=source_title,
                snippet_text=text,
                sentence=sentence,
                section=section,
                char_start=start,
                char_end=end,
                snippet_score=score,
            )
        )
    return results


def extract_ref_mentions(
    snippet_search_response: dict, query: str
) -> ExtractionResult:
    """Extract all ref mentions from a full snippet_search response.

    Args:
        snippet_search_response: Raw response dict from ASTA snippet_search.
        query: The search query that produced this response.

    Returns:
        ExtractionResult with deduplicated corpus IDs and all mentions.
    """
    result_data = snippet_search_response.get("result", snippet_search_response)
    data = result_data.get("data", [])

    all_mentions: list[RefMention] = []
    unresolved = 0
    source_papers: dict[str, str] = {}
    total_ref_mentions_raw = 0

    for item in data:
        # Track source papers
        paper = item.get("paper", {})
        cid = str(paper.get("corpusId", ""))
        if cid:
            source_papers[cid] = paper.get("title", "")

        # Count unresolved refs
        snippet = item.get("snippet", {})
        annotations = snippet.get("annotations")
        if annotations:
            raw_refs = annotations.get("refMentions") or []
            total_ref_mentions_raw += len(raw_refs)
            for rm in raw_refs:
                if rm.get("matchedPaperCorpusId") is None:
                    unresolved += 1

        # Extract resolved mentions
        mentions = _extract_from_snippet(item, query)
        all_mentions.extend(mentions)

    # Deduplicate corpus IDs preserving first-appearance order
    seen: set[str] = set()
    unique_ids: list[str] = []
    for m in all_mentions:
        if m.corpus_id not in seen:
            seen.add(m.corpus_id)
            unique_ids.append(m.corpus_id)

    return ExtractionResult(
        query=query,
        unique_corpus_ids=unique_ids,
        ref_mentions=all_mentions,
        unresolved_count=unresolved,
        source_papers=source_papers,
        stats={
            "total_snippets": len(data),
            "total_ref_mentions": total_ref_mentions_raw,
            "resolved_refs": len(all_mentions),
            "unresolved_refs": unresolved,
            "unique_refs": len(unique_ids),
            "source_papers": len(source_papers),
        },
    )


def _load_mcp_config() -> tuple[str, dict[str, str]]:
    """Load ASTA MCP server URL and headers from .mcp.json."""
    import pathlib

    mcp_path = pathlib.Path(__file__).resolve().parent.parent / ".mcp.json"
    if not mcp_path.exists():
        print(f"MCP config not found: {mcp_path}", file=sys.stderr)
        sys.exit(1)
    with open(mcp_path) as f:
        config = json.load(f)
    server = config.get("mcpServers", {}).get("Asta_semanticscholar", {})
    url = server.get("url", "")
    headers = server.get("headers", {})
    if not url:
        print("Asta_semanticscholar not configured in .mcp.json", file=sys.stderr)
        sys.exit(1)
    return url, headers


def _call_snippet_search(
    query: str, limit: int = 10, paper_ids: str | None = None
) -> dict:
    """Call ASTA snippet_search via MCP HTTP transport."""
    mcp_url, mcp_headers = _load_mcp_config()

    arguments: dict = {"query": query, "limit": limit}
    if paper_ids:
        arguments["paper_ids"] = paper_ids

    # MCP JSON-RPC call
    payload = json.dumps({
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": "snippet_search",
            "arguments": arguments,
        },
    }).encode()

    req = urllib.request.Request(mcp_url, data=payload, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("Accept", "application/json, text/event-stream")
    for k, v in mcp_headers.items():
        req.add_header(k, v)

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode()
    except urllib.error.HTTPError as e:
        print(f"MCP API error: {e.code} {e.reason}", file=sys.stderr)
        sys.exit(1)

    # Parse SSE response: extract JSON from "data:" lines
    rpc_response = None
    for line in raw.splitlines():
        if line.startswith("data: "):
            rpc_response = json.loads(line[6:])
            break
    if rpc_response is None:
        # Try parsing as plain JSON (non-SSE)
        rpc_response = json.loads(raw)

    # Extract snippet_search result from MCP JSON-RPC response
    rpc_result = rpc_response.get("result", {})
    content = rpc_result.get("content", [])
    if not content:
        print("Empty MCP response", file=sys.stderr)
        sys.exit(1)
    return json.loads(content[0].get("text", "{}"))


def cli_main() -> None:
    """CLI entry point."""
    import argparse
    from dataclasses import asdict

    parser = argparse.ArgumentParser(
        description="Extract ref mentions from ASTA snippet search"
    )
    parser.add_argument("query", help="Search query string")
    parser.add_argument(
        "--limit", type=int, default=10, help="Max snippets (default 10)"
    )
    parser.add_argument(
        "--paper-ids", help="Comma-separated paper IDs to scope search"
    )
    parser.add_argument(
        "--pretty", action="store_true", help="Pretty-print JSON output"
    )
    args = parser.parse_args()

    response = _call_snippet_search(args.query, args.limit, args.paper_ids)
    result = extract_ref_mentions(response, args.query)

    out = asdict(result)
    indent = 2 if args.pretty else None
    print(json.dumps(out, indent=indent))


if __name__ == "__main__":
    cli_main()
