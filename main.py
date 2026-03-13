"""
main.py
=======
Entry point — runs the full scrape pipeline.

Usage:
    uv run python main.py
    # or via the project script:
    uv run scrape
"""

import asyncio
from keyword_scraper.runner import run


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
