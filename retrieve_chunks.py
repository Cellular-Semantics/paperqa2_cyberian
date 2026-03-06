"""Shim — entry point kept at repo root so skills can call `uv run python retrieve_chunks.py`."""
from paperqa2_cyberian.retrieve_chunks import main

if __name__ == "__main__":
    main()
