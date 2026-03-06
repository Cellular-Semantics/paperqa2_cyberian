"""Shim — entry point kept at repo root so skills can call `uv run python parse_jats_citations.py`."""
from paperqa2_cyberian.parse_jats_citations import cli_main

if __name__ == "__main__":
    cli_main()
