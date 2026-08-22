"""Convenience alias: ``python -m scrapper_api`` runs the dev server (see also ``poe api``)."""

from __future__ import annotations

import uvicorn


def main() -> None:
    """Run the FastAPI app with uvicorn's development server."""
    uvicorn.run("scrapper_api.app:app", host="127.0.0.1", port=8000, reload=True)


if __name__ == "__main__":
    main()
