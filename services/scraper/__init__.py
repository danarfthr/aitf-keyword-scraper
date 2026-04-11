"""Scraper library for Keyword Manager."""

from .delta import detect_delta
from .google_trends import scrape_google_trends
from .trends24 import scrape_trends24

__all__ = ["scrape_google_trends", "scrape_trends24", "detect_delta"]
