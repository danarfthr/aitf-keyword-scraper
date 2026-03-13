"""
classifier.py
=============
Keyword classification pipeline:
  Stage 1 — Rule-based seed matching  (instant, confidence = null)
  Stage 2 — Zero-shot NLI via mDeBERTa (when no rule matches)
"""

from transformers import pipeline as hf_pipeline

from .config import (
    CANDIDATE_LABELS,
    FALLBACK_KAT,
    FALLBACK_SUB,
    PARENT_MAP,
    RULES,
)
from .filters import classify_prioritas, classify_sentiment

# Lazy-loaded model instance
_classifier = None


def _get_classifier():
    global _classifier
    if _classifier is None:
        print("Loading mDeBERTa zero-shot classifier (first run may take a moment)…")
        _classifier = hf_pipeline(
            "zero-shot-classification",
            model="MoritzLaurer/mDeBERTa-v3-base-mnli-xnli",
        )
    return _classifier


def classify_keyword(keyword: str) -> dict:
    """
    Classify a single keyword using the 2-stage pipeline.

    Returns a dict with:
        kategori_utama, sub_kategori, sentimen, prioritas,
        confidence_score, is_auto_labeled
    """
    kw_lower = keyword.lower()

    # ------------------------------------------------------------------
    # Stage 1 — Rule-based match
    # ------------------------------------------------------------------
    for sub_kat, kat_utama, seeds in RULES:
        for seed in seeds:
            if seed in kw_lower:
                sentimen = classify_sentiment(keyword)
                return {
                    "kategori_utama": kat_utama,
                    "sub_kategori": sub_kat,
                    "sentimen": sentimen,
                    "prioritas": classify_prioritas(sub_kat, sentimen),
                    "confidence_score": None,   # rule-based; null is valid per schema
                    "is_auto_labeled": True,
                }

    # ------------------------------------------------------------------
    # Stage 2 — Zero-shot NLI
    # ------------------------------------------------------------------
    try:
        clf = _get_classifier()
        candidate_list = list(CANDIDATE_LABELS.values())
        result = clf(keyword, candidate_list, multi_label=False)

        best_idx = result["scores"].index(max(result["scores"]))
        best_label_desc = result["labels"][best_idx]
        confidence = round(result["scores"][best_idx], 4)

        # Reverse-map description → sub_kategori code
        sub_kat = FALLBACK_SUB
        for code, desc in CANDIDATE_LABELS.items():
            if desc == best_label_desc:
                sub_kat = code
                break

        kat_utama = PARENT_MAP.get(sub_kat, FALLBACK_KAT)
        sentimen = classify_sentiment(keyword)

        return {
            "kategori_utama": kat_utama,
            "sub_kategori": sub_kat,
            "sentimen": sentimen,
            "prioritas": classify_prioritas(sub_kat, sentimen),
            "confidence_score": confidence,
            "is_auto_labeled": True,
        }

    except Exception as exc:
        print(f"  [WARN] Classifier failed for '{keyword}': {exc}. Using fallback.")
        sentimen = classify_sentiment(keyword)
        return {
            "kategori_utama": FALLBACK_KAT,
            "sub_kategori": FALLBACK_SUB,
            "sentimen": sentimen,
            "prioritas": "S",
            "confidence_score": 0.1,
            "is_auto_labeled": True,
        }
