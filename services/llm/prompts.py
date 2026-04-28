"""LLM prompt templates for the combined justifier+enricher processor."""

from shared.shared.constants import SUMMARY_CHAR_THRESHOLD


COMBINED_SYSTEM = """
You are a content relevance and keyword expansion assistant for a government
issue monitoring system operated by the Indonesian Ministry of Communication
and Informatics (Komdigi).

You will receive a keyword and sample news articles about it.

Step 1 — RELEVANCE: Determine whether this keyword topic is related to
Indonesian government affairs. Relevant topics include: ministry activities,
public policy, regulations, government programs, state-owned enterprises (BUMN),
parliamentary proceedings, court rulings affecting public policy, or
government-linked institutions. Base your decision on the article content,
not just the keyword text alone.

Step 2 — EXPANSION: If relevant, generate related search keywords that will
help a crawler find more government-relevant articles on the same topic.

Rules for expansion:
- Generate 5 to 10 expanded keywords.
- All keywords must be in Indonesian.
- Base keywords strictly on the article content — do not invent unrelated terms.
- Each keyword must be specific and directly related to the government topic.
- Avoid generic terms such as: "berita", "indonesia", "terbaru", "informasi".
- Keep each keyword concise: 1 to 4 words.

Respond ONLY with a valid JSON object. No text before or after the JSON.

Format when not relevant:
{"is_relevant": false, "justification": "<reason in Indonesian, max 2 sentences>"}

Format when relevant:
{"is_relevant": true, "justification": "<reason in Indonesian, max 2 sentences>", "expanded_keywords": ["keyword1", "keyword2", "keyword3"]}
"""


def build_combined_prompt(keyword: str, article_context: str) -> str:
    """Build the user message for the combined justification+enrichment LLM call."""
    return f"""Keyword trending: {keyword}

Sampel artikel:
{article_context}

Tahap 1 — Apakah keyword ini berkaitan dengan isu pemerintahan Indonesia?
Tahap 2 — Jika ya, hasilkan keyword pencarian tambahan yang relevan."""


def build_article_context(articles: list) -> str:
    """
    Build a compact article context string for LLM prompts.
    Uses summary if available, otherwise truncates body to SUMMARY_CHAR_THRESHOLD.
    Numbers each article for readability.
    """
    parts = []
    for i, article in enumerate(articles, 1):
        content = (
            article.summary
            if article.summary
            else (article.body or "")[:SUMMARY_CHAR_THRESHOLD]
        )
        title = article.title or "(no title)"
        parts.append(f"[Artikel {i}] {title}\\n{content}")
    return "\\n\\n".join(parts)


def build_messages(system: str, user: str) -> list[dict]:
    """Build the messages list for an OpenRouter chat completion request."""
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
