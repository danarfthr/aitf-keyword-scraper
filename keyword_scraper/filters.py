"""
filters.py
==========
Stage 1 rule-based filter using word-boundary regex to reduce false positives.
"""

import re
from typing import Final

# ~80 governance/public-interest signals (from existing TAXONOMY_RULES seeds)
GOVERNANCE_SIGNALS: Final[list[str]] = [
    "korupsi", "kpk", "suap", "tipikor", "lhkpn", "reformasi", "birokrasi",
    "kebijakan", "regulasi", "layanan publik", "ina digital", "e-gov",
    "apbn", "audit", "anggaran", "kementeri", "pejabat", "menteri",
    "presiden", "gubernur", "bupati", "walikota",
    "judi online", "hoaks", "hack", "bocor", "phishing", "penipuan", "scam", "deepfake",
    "bansos", "pkh", "blt", "kemiskinan", "bpnt", "jaminan sosial",
    "tol", "krl", "mrt", "bts", "fiber", "satria", "infrastruktur",
    "fintech", "startup", "pse", "qris", "kripto", "e-commerce", "pajak",
    "phk", "umr", "ump", "pengangguran", "prakerja", "tka", "ketenagakerjaan",
    "bpjs", "wabah", "pandemi", "nakes", "klb", "puskesmas", "kesehatan",
    "sekolah", "ppdb", "literasi", "beasiswa", "universitas", "kampus", "pendidikan",
    "banjir", "gempa", "longsor", "erupsi", "bnpb", "bpbd", "bencana", "tsunami",
    "polisi", "polda", "polres", "densus", "tni", "kpu", "bawaslu", "mk", "ma",
    "kejaksaan", "jaksa", "hakim",
    "dpr", "dprd", "mpr", "parpol", "partai", "pilkada", "pemilu", "pilpres",
    "hukum", "undang-undang", "perda", "perpu", "perpres", "inpres",
    "nkri", "pancasila", "uud", "konstitusi",
    "komdigi", "kominfo", "bssn", "bpk", "bkp", "kpk", "ombudsman", "mahkamah",
    "subsidi", "inflasi", "deflasi", "rupiah", "kurs", "utang negara",
    "pangan", "sembako", "beras", "minyak goreng", "bbm", "solar", "pertalite",
    "imigran", "pengungsi", "tppo", "perdagangan manusia",
    "narkoba", "narkotika", "bnn",
    "operasi ketupat", "mudik", "keselamatan lalu lintas",
    "bulog", "baznas", "bnpt",
    "israel", "palestina", "ukraine", "russia", "nato", "pbb", "imf", "worldbank",
    "iran", "netanyahu", "trump", "biden", "zelensky",
]

# Pre-compiled regex: word-boundary match for each signal
_SIGNAL_PATTERNS: list[re.Pattern] = [
    re.compile(rf"\b{re.escape(signal)}\b", re.IGNORECASE)
    for signal in GOVERNANCE_SIGNALS
]

governance_signals = GOVERNANCE_SIGNALS  # exposed for Streamlit chip UI


def match_rule_filter(keyword: str) -> bool:
    """
    Returns True if keyword matches any governance signal as a standalone word.
    Uses word-boundary regex (\\b) to avoid false positives.
    """
    for pattern in _SIGNAL_PATTERNS:
        if pattern.search(keyword):
            return True
    return False
