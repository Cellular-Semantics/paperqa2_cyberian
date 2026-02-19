"""CyberianLLMModel: routes paperqa2 LLM calls through a local agentapi/codex server.

The agentapi server exposes three endpoints:
  POST /message  — send a message to the agent
  GET  /status   — poll until status in {idle, ready, stable, waiting}
  GET  /messages — retrieve conversation history; last agent message is the response

Design note — context clearing:
  paperqa2 makes many separate LLM calls (one per chunk summary, one per citation,
  one for the final answer, …).  All of these hit the same running codex session, so
  context accumulates rapidly.  We send `/new` before every real message so each
  call starts with a clean slate and codex's context window never fills up.

Design note — parallel sessions:
  Pass ports=[3284, 3285, ...] to use multiple agentapi instances concurrently.
  Each call acquires a free port from the pool, runs, then returns it.
  With N ports, up to N chunk-summary calls proceed in parallel.

Inspired by cellsem_llm_client (https://github.com/Cellular-Semantics/cellsem_llm_client)
and cyberian (https://github.com/contextualizer-ai/cyberian).
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import AsyncIterable
from typing import Any

import httpx
from aviary.core import Message
from lmi.llms import LLMModel
from lmi.types import LLMResult
from pydantic import Field, PrivateAttr

logger = logging.getLogger(__name__)

# agentapi statuses that mean the agent has finished processing
_IDLE_STATUSES = {"idle", "ready", "stable", "waiting"}

# How long to wait after /new before sending the real message
_CLEAR_SETTLE_SECS = 1.0


def _wait_for_idle(base: str, deadline: float, poll_interval: float) -> None:
    """Block until agentapi reports an idle status or deadline is reached."""
    while True:
        if time.monotonic() > deadline:
            raise TimeoutError(f"Timed out waiting for agentapi idle at {base}")
        try:
            sr = httpx.get(f"{base}/status", timeout=5.0)
            sr.raise_for_status()
            if sr.json().get("status", "").lower() in _IDLE_STATUSES:
                return
        except httpx.HTTPError as exc:
            logger.debug("Status poll error: %s — retrying", exc)
        time.sleep(poll_interval)


def _sync_send_and_wait(
    host: str,
    port: int,
    content: str,
    timeout: int,
    poll_interval: float,
) -> str:
    """Send *content* to the agentapi server and block until the agent responds.

    Sends /new first to reset codex's context window, then sends the real
    message, polls until idle, and returns the last agent message text.
    """
    base = f"http://{host}:{port}"
    deadline = time.monotonic() + timeout

    # 1. Start a new codex conversation so each call starts fresh.
    #    If /new itself returns 500 (server busy), we still wait for idle below
    #    so the real message is never sent to a busy server.
    try:
        httpx.post(
            f"{base}/message",
            content=json.dumps({"content": "/new", "type": "user"}),
            headers={"Content-Type": "application/json"},
            timeout=10.0,
        ).raise_for_status()
    except Exception as exc:
        logger.warning("Failed to /new codex context: %s — continuing anyway", exc)
    # Always wait for idle before the real message — covers both the case where
    # /new succeeded (wait for it to finish) and where it failed (wait for the
    # server to finish whatever it was doing).
    _wait_for_idle(base, deadline, poll_interval)
    time.sleep(_CLEAR_SETTLE_SECS)

    # 2. Send the real message
    httpx.post(
        f"{base}/message",
        content=json.dumps({"content": content, "type": "user"}),
        headers={"Content-Type": "application/json"},
        timeout=30.0,
    ).raise_for_status()

    # 3. Poll /status until the agent is idle again
    _wait_for_idle(base, deadline, poll_interval)

    # 4. Retrieve the last agent message
    mr = httpx.get(f"{base}/messages", timeout=5.0)
    mr.raise_for_status()
    messages = mr.json().get("messages", [])

    for msg in reversed(messages):
        if msg.get("role", "").lower() in ("agent", "assistant"):
            return _strip_terminal_chrome(msg.get("content", ""))

    raise ValueError("No agent response found in agentapi message history")


# Patterns that appear in codex's terminal status bar / UI chrome — strip them
# from the end of responses so they don't pollute paperqa2's context/answer.
_TERMINAL_CHROME_PATTERNS = (
    "› Implement {feature}",
    "? for shortcuts",
    "% context left",
)


def _strip_terminal_chrome(text: str) -> str:
    """Remove codex terminal UI chrome that bleeds into agent messages."""
    lines = text.splitlines()
    # Drop trailing lines that are purely UI chrome
    while lines:
        stripped = lines[-1].strip()
        if not stripped or any(pat in stripped for pat in _TERMINAL_CHROME_PATTERNS):
            lines.pop()
        else:
            break
    return "\n".join(lines).strip()


def _format_messages(messages: list[Message]) -> str:
    """Flatten a list of chat messages into a single prompt string.

    System messages become a preamble; user/assistant messages are
    labelled so codex understands the conversational structure.
    """
    parts: list[str] = []
    for msg in messages:
        if not msg.content:
            continue
        role = msg.role.lower()
        if role == "system":
            parts.append(f"[System instructions]\n{msg.content}")
        elif role == "user":
            parts.append(f"[User]\n{msg.content}")
        else:
            parts.append(f"[Assistant]\n{msg.content}")
    return "\n\n---\n\n".join(parts)


class CyberianLLMModel(LLMModel):
    """Routes paperqa2 LLM calls to a local agentapi/codex server.

    Each call acquires a free port from the pool, sends /new to reset codex's
    context, sends the prompt, and returns the port when done.  With a single
    port the behaviour is identical to a simple lock; with multiple ports up to
    N calls run concurrently.

    Usage::

        from cyberian_llm import CyberianLLMModel
        # single instance (default)
        llm = CyberianLLMModel(host="localhost", ports=[3284])
        # three parallel instances
        llm = CyberianLLMModel(host="localhost", ports=[3284, 3285, 3286])
        session = await docs.aquery(question, llm_model=llm, summary_llm_model=llm)
    """

    name: str = "cyberian/codex"
    host: str = Field(default="localhost", description="agentapi server hostname")
    ports: list[int] = Field(default=[3284], description="agentapi server port(s)")
    timeout: int = Field(default=300, description="Max seconds to wait for agent response")
    poll_interval: float = Field(default=2.0, description="Seconds between status polls")

    # Pool of available ports — each entry is a port number ready to accept a call.
    # Populated in model_post_init from self.ports.
    _port_pool: asyncio.Queue = PrivateAttr(default=None)

    def model_post_init(self, _: Any) -> None:
        self._port_pool = asyncio.Queue()
        for port in self.ports:
            self._port_pool.put_nowait(port)

    async def acompletion(
        self, messages: list[Message], **kwargs: Any
    ) -> list[LLMResult]:
        """Acquire a free port, start new codex context, send messages, release port."""
        prompt = _format_messages(messages)
        port = await self._port_pool.get()
        logger.debug("Sending %d-char prompt to agentapi %s:%d", len(prompt), self.host, port)
        try:
            response_text = await asyncio.to_thread(
                _sync_send_and_wait,
                self.host,
                port,
                prompt,
                self.timeout,
                self.poll_interval,
            )
        finally:
            self._port_pool.put_nowait(port)
        logger.debug("Got %d-char response from agentapi :%d", len(response_text), port)
        return [
            LLMResult(
                model=self.name,
                text=response_text,
                prompt=messages,
                messages=[Message(role="assistant", content=response_text)],
            )
        ]

    async def acompletion_iter(
        self, messages: list[Message], **kwargs: Any
    ) -> AsyncIterable[LLMResult]:
        """Yield one LLMResult (agentapi has no streaming; we wrap acompletion)."""
        for result in await self.acompletion(messages, **kwargs):
            yield result
