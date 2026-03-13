"""
filters.py
==========
Stage 0 relevance gate and sentiment heuristics.
"""

import re

# ---------------------------------------------------------------------------
# Stage 0 — Relevance filter
# ---------------------------------------------------------------------------

# Hard-block patterns — anything matching these is immediately dropped.
_BLOCK_PATTERNS = re.compile(
    r"""
    # Korean / Thai / Japanese Unicode blocks (fandom content)
    [\uAC00-\uD7A3\u0E00-\u0E7F\u3040-\u30FF\u4E00-\u9FFF]
    |
    # Twitter hashtags followed by fandom/event noise
    \#[A-Za-z0-9_]{3,}(?:Day|Fan|Fam|Fandom|Stay|Vote|Stream|Beat|Award|Wins|Squad|Love)
    |
    # Common K-pop / idol group name fragments
    (?:enhypen|txt|bts|exo|nct|stray.?kids|seventeen|ateez|itzy|aespa|newjeans|fifty.?fifty|
       blackpink|twice|ive|lesserafim|gidle|kep1er|nmixx|fromis|p1harmony|the.?boyz|
       tomorrow.?x|monsta.?x|shinee|super.?junior|bigbang|got7|day6|skz|svt|
       jkt48|bnk48|plave|beomgyu|heeseung|jaemin|renjun|seungmin|taehyun|yeonjun|
       soobin|huening|felix|hyunjin|wooyoung|yunho|jongho|san|mingi|yeosang|
       chaeryeong|yeji|ryujin|lia|yuna|ningning|winter|karina|giselle|
       danielle|haerin|minji|hanni|hyein|yunjin|sakura|chaewon|kazuha|
       eunchae|garam|sullyoon|jiwoo|bae|kyujin|haewon|lily|phoebe)
    |
    # Sports merchandise / fashion brand noise unrelated to gov
    (?:\bkelme\b|\berspo\b|\bmills\b|\bgloss[yi]\b)
    |
    # Pure entertainment event codes
    \b(?:ON AIR WITH|ONAIR|PRESSTOUR|FANDOM LIVE|LIVEHOUSE|AOUBOOM|NETJJ|TFO|DMD)
    """,
    re.IGNORECASE | re.VERBOSE,
)

# Allow-list — keyword must contain at least ONE governance signal to pass.
_RELEVANCE_SIGNALS = re.compile(
    r"""
    # Taxonomy seed terms (Stage 1 duplicated for fast gate)
    korupsi|kpk|suap|tipikor|lhkpn|reformasi|birokrasi
    |kebijakan|regulasi|layanan.publik|ina.digital|e-gov
    |apbn|audit|anggaran|kementeri|pejabat|menteri|presiden|gubernur|bupati|walikota
    |judi.online|hoaks|hack|bocor|phishing|penipuan|scam|deepfake|pdp|siber
    |bansos|pkh|blt|kemiskinan|bpnt|jaminan.sosial
    |tol|krl|mrt|bts|fiber|satria|infrastruktur
    |fintech|startup|pse|qris|kripto|e-commerce|pajak
    |phk|umr|ump|pengangguran|prakerja|tka|ketenagakerjaan
    |bpjs|wabah|pandemi|nakes|klb|puskesmas|kesehatan|vaksin|rumah.sakit|rs|
    |sekolah|ppdb|literasi|beasiswa|universitas|kampus|pendidikan
    |banjir|gempa|longsor|erupsi|bnpb|bpbd|bencana|tsunami
    # Broader governance & public-interest terms
    |polisi|polda|polres|densus|tni|kpu|bawaslu|mk|ma|kejaksaan|jaksa|hakim
    |dpr|dprd|mpr|parpol|partai|pilkada|pemilu|pilpres
    |hukum|undang-undang|perda|perpu|perpres|inpres
    |nkri|pancasila|uud|konstitusi
    |komdigi|kominfo|bssn|bpk|bpkp|kpk|ombudsman|mahkamah
    |subsidi|inflasi|deflasi|rupiah|kurs|apbn|apbd|utang.negara
    |pangan|sembako|beras|minyak.goreng|bbm|solar|pertalite
    |imigran|pengungsi|tppo|perdagangan.manusia
    |narkoba|narkotika|bnn
    |operasi.ketupat|mudik|keselamatan.lalu.lintas
    |bulog|baznas|bnpt|kemenkes|kemdikbud|kemlu|kemendag|kemenperin
    |aceh|papua|sulawesi|kalimantan|sumatera|jawa|ntt|ntb|maluku
    # International / geopolitical terms that appear in Indonesian trending
    |israel|palestina|ukraine|russia|nato|pbb|un.security|imf|worldbank
    |iran|netanyahu|trump|biden|zelensky
    """,
    re.IGNORECASE | re.VERBOSE,
)


def is_relevant(keyword: str) -> tuple[bool, str]:
    """
    Stage 0 relevance gate.

    Returns:
        (True, '')           — keyword should proceed to classification.
        (False, reason_str)  — keyword should be skipped.
    """
    if _BLOCK_PATTERNS.search(keyword):
        return False, "entertainment/fandom pattern"
    if not _RELEVANCE_SIGNALS.search(keyword):
        return False, "no governance signal"
    return True, ""


# ---------------------------------------------------------------------------
# Sentiment heuristics
# ---------------------------------------------------------------------------

_NEGATIVE_TERMS = re.compile(
    r"korupsi|suap|hoaks|hack|bocor|phishing|penipuan|scam|judi|ilegal|deepfake|"
    r"phk|kemiskinan|pandemi|wabah|banjir|gempa|longsor|erupsi|konflik|bencana|"
    r"defisit|pengangguran|tipikor|kriminal|darurat",
    re.IGNORECASE,
)
_POSITIVE_TERMS = re.compile(
    r"beasiswa|inovasi|luncurkan|berhasil|capaian|sukses|rekrut|pelatihan|literasi|"
    r"prestasi|bantuan|program|tumbuh|naik|meningkat|positif",
    re.IGNORECASE,
)


def classify_sentiment(keyword: str) -> str:
    """Return 'NEG', 'POS', or 'NET' based on simple keyword heuristics."""
    if _NEGATIVE_TERMS.search(keyword):
        return "NEG"
    if _POSITIVE_TERMS.search(keyword):
        return "POS"
    return "NET"


def classify_prioritas(sub_kat: str, sentimen: str) -> str:
    """Return 'T' (Tinggi) or 'S' (Sedang) based on category and sentiment."""
    high_priority_cats = {"IPH", "KSD", "LKS", "KSB"}
    if sub_kat in high_priority_cats and sentimen == "NEG":
        return "T"
    return "S"
