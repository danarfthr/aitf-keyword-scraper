"""
expander.py
===========
Keyword variant expansion via OpenRouter.
Single batch prompt for all keywords — never per-keyword.
"""

import os
import json
import requests
from pydantic import BaseModel


class ExpansionResult(BaseModel):
    keyword: str
    variants: list[str]


OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = "google/gemma-4-26b-a4b-it:free"


def expand_batch(keywords: list[str], model: str = DEFAULT_MODEL) -> list[ExpansionResult]:
    """
    Batch-generate variants for multiple keywords via OpenRouter.

    Returns list of ExpansionResult (keyword + list of variants).
    """
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        raise ValueError("OPENROUTER_API_KEY environment variable is required")

    prompt = (
        "Generate search query variants for the following Indonesian keywords.\n"
        "For each keyword, produce 3-5 relevant variant queries that Indonesian social media users might search.\n\n"
        "Keywords:\n"
        + json.dumps(keywords, ensure_ascii=False)
        + "\n\n"
        'Output a JSON array with this exact format — no extra text:\n'
        '{"results": [{"keyword": "original keyword", "variants": ["variant 1", "variant 2", ...]}, ...]}'
    )

    response = requests.post(
        OPENROUTER_API_URL,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.3,
        },
        timeout=120,
    )

    if response.status_code != 200:
        raise RuntimeError(f"OpenRouter API error: {response.status_code} {response.text}")

    content = response.json()["choices"][0]["message"]["content"]
    try:
        data = json.loads(content)
        return [ExpansionResult(**item) for item in data["results"]]
    except (json.JSONDecodeError, KeyError) as e:
        raise RuntimeError(f"Failed to parse OpenRouter response: {e}\nContent: {content}")
