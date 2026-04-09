"""
openrouter.py
==============
Batch AI classification via OpenRouter API.
Single API call for ALL keywords — never per-keyword.
"""

import os
import re
import json
import requests
from pydantic import BaseModel


class ClassificationResult(BaseModel):
    keyword: str
    relevant: bool


OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = "nvidia/nemotron-3-super-120b-a12b:free"
QUALITY_MODEL = "google/gemini-2.5-flash-preview"


def _strip_markdown_fences(text: str) -> str:
    """Strip ```json ... ``` or ``` ... ``` fences from LLM output."""
    text = text.strip()
    pattern = re.compile(r"^```(?:json)?\s*\n?(.*?)\n?\s*```$", re.DOTALL)
    match = pattern.match(text)
    if match:
        return match.group(1).strip()
    return text


def classify_batch(keywords: list[str], model: str = DEFAULT_MODEL) -> list[ClassificationResult]:
    """
    Batch-classify keywords via OpenRouter.

    Returns a list of ClassificationResult (keyword + relevant bool).
    Keywords that are not relevant will be marked as REJECTED (not deleted).
    """
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        raise ValueError("OPENROUTER_API_KEY environment variable is required")

    prompt = (
        "Classify each keyword as relevant or not relevant for government/public interest/politics in Indonesia.\n"
        "Relevance means: related to policy, governance, public safety, economics, or social issues.\n\n"
        "Keywords to classify:\n"
        + json.dumps(keywords, ensure_ascii=False)
        + "\n\n"
        "Output ONLY a JSON object with this exact format — no markdown, no extra text:\n"
        '{"results": [{"keyword": "keyword text", "relevant": true}, ...]}'
    )

    try:
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
            timeout=180,
        )
    except requests.exceptions.Timeout:
        raise RuntimeError("OpenRouter API timed out after 180s. Try fewer keywords or a faster model.")
    except requests.exceptions.ConnectionError:
        raise RuntimeError("Could not connect to OpenRouter API. Check your internet connection.")

    if response.status_code != 200:
        error_detail = response.text[:500]
        raise RuntimeError(f"OpenRouter API error ({response.status_code}): {error_detail}")

    try:
        content = response.json()["choices"][0]["message"]["content"]
    except (KeyError, IndexError) as e:
        raise RuntimeError(f"Unexpected OpenRouter response structure: {e}")

    content = _strip_markdown_fences(content)

    try:
        data = json.loads(content)
        return [ClassificationResult(**item) for item in data["results"]]
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Failed to parse AI response as JSON: {e}\nRaw content: {content[:500]}")
    except KeyError:
        raise RuntimeError(f"AI response missing 'results' key.\nParsed: {json.dumps(data, indent=2)[:500]}")
