"""
openrouter.py
==============
Batch AI classification via OpenRouter API.
Single API call for ALL keywords — never per-keyword.
"""

import os
import json
import requests
from pydantic import BaseModel


class ClassificationResult(BaseModel):
    keyword: str
    relevant: bool


OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = "google/gemma-4-26b-a4b-it:free"
QUALITY_MODEL = "qwen/qwen3.6-plus"


def classify_batch(keywords: list[str], model: str = DEFAULT_MODEL) -> list[ClassificationResult]:
    """
    Batch-classify keywords via OpenRouter.

    Returns a list of ClassificationResult (keyword + relevant bool).
    Keywords that are not relevant are NOT included in Phase 2 output.
    """
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        raise ValueError("OPENROUTER_API_KEY environment variable is required")

    prompt = f"""Classify each keyword as relevant or not relevant for government/public interest/politics in Indonesia.
Relevance means: related to policy, governance, public safety, economics, or social issues.

Keywords to classify:
{json.dumps(keywords, ensure_ascii=False)}

Output a JSON array with this exact format — no extra text:
{{"results": [{{"keyword": "keyword text", "relevant": true/false}}, ...]}}
"""

    response = requests.post(
        OPENROUTER_API_URL,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1,
        },
        timeout=120,
    )

    if response.status_code != 200:
        raise RuntimeError(f"OpenRouter API error: {response.status_code} {response.text}")

    content = response.json()["choices"][0]["message"]["content"]
    try:
        data = json.loads(content)
        return [ClassificationResult(**item) for item in data["results"]]
    except (json.JSONDecodeError, KeyError) as e:
        raise RuntimeError(f"Failed to parse OpenRouter response: {e}\nContent: {content}")
