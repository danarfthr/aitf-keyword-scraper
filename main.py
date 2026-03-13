"""
Unified Trends Scraper
=======================
Scrapes trending keywords from:
  - Google Trends (GTR) — https://trends.google.com/trending?geo=ID&category=10
  - Trends24 (T24)      — https://trends24.in/indonesia/

Output: /data/merged_trends_<YYYYMMDD_HHMMSS>.json
Schema: scraped_item.schema.json (UUID, source_platform, keyword, rank, geo, labels…)

Classification (3-stage):
  Stage 0 — Relevance gate  : drop entertainment, fandom, celebrity noise
  Stage 1 — Rule-based match: seed terms → instant label (confidence = null)
  Stage 2 — Zero-shot NLI   : mDeBERTa if no rule matched
"""

import asyncio
import io
import json
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

import nest_asyncio
from bs4 import BeautifulSoup
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode
from transformers import pipeline

nest_asyncio.apply()

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

OUTPUT_DIR = Path(__file__).parent / "data"
URL_GEO = "ID"

# ---------------------------------------------------------------------------
# Taxonomy rules — Stage 1 (rule-based)
# ---------------------------------------------------------------------------

TAXONOMY_RULES: list[tuple[str, str, str]] = [
    # (sub_kategori, kategori_utama, comma-separated seed terms)
    ("IPH", "POG", "korupsi,kpk,suap,tipikor,ite,penegakan hukum,lhkpn,reformasi birokrasi"),
    ("KLP", "POG", "kebijakan,regulasi,layanan publik,ina digital,permen,pp nomor,e-government"),
    ("KPM", "POG", "kinerja menteri,apbn,audit bpk,efisiensi anggaran,kepuasan layanan"),
    ("KSD", "POG", "judi online,hoaks,hack,bocor data,phishing,penipuan,scam,deepfake,pdp,konten ilegal"),
    ("KBS", "ECD", "bansos,pkh,blt,kemiskinan,bpnt,perlindungan sosial,jaminan sosial"),
    ("ILT", "ECD", "tol,krl,mrt,bts,fiber optik,satria,internet desa,infrastruktur"),
    ("EKD", "ECD", "e-commerce,fintech,startup,pse,qris,kripto,marketplace,pajak digital"),
    ("KTK", "ECD", "phk,umr,ump,pengangguran,prakerja,tka,ketenagakerjaan"),
    ("LKS", "SEH", "bpjs,wabah,pandemi,nakes,klb,puskesmas,kesehatan"),
    ("PSD", "SEH", "sekolah,ppdb,literasi digital,aitf,beasiswa,perguruan tinggi,sdm"),
    ("KSB", "SEH", "banjir,gempa,longsor,erupsi,bnpb,bpbd,konflik sosial,bencana"),
]

# Pre-process rules into list of (sub_kat, kat_utama, [seed, ...])
_RULES: list[tuple[str, str, list[str]]] = [
    (sub, kat, [s.strip() for s in seeds.split(",")])
    for sub, kat, seeds in TAXONOMY_RULES
]

# Candidate labels for zero-shot classification (sub_kategori → description)
CANDIDATE_LABELS = {
    "IPH": "Integritas dan Penegakan Hukum — korupsi, transparansi, akuntabilitas lembaga negara",
    "KLP": "Kebijakan dan Layanan Publik — regulasi, implementasi kebijakan, e-government",
    "KPM": "Kinerja Pemerintah — evaluasi kinerja pejabat, kementerian, APBN",
    "KSD": "Keamanan Siber dan Ketertiban Digital — judi online, hoaks, data breach, perlindungan data",
    "KBS": "Kesejahteraan dan Bantuan Sosial — bansos, kemiskinan, perlindungan sosial",
    "ILT": "Infrastruktur dan Layanan Transportasi — jalan, kereta, internet desa, BTS",
    "EKD": "Ekonomi Digital — e-commerce, fintech, startup, kripto, pajak digital",
    "KTK": "Ketenagakerjaan — PHK, upah, pengangguran, Prakerja",
    "LKS": "Layanan Kesehatan — BPJS, wabah, pandemi, puskesmas",
    "PSD": "Pendidikan dan Pengembangan SDM — sekolah, beasiswa, literasi digital",
    "KSB": "Krisis Sosial dan Kebencanaan — banjir, gempa, bencana, konflik sosial",
}

PARENT_MAP = {
    "IPH": "POG", "KLP": "POG", "KPM": "POG", "KSD": "POG",
    "KBS": "ECD", "ILT": "ECD", "EKD": "ECD", "KTK": "ECD",
    "LKS": "SEH", "PSD": "SEH", "KSB": "SEH",
}

FALLBACK_SUB = "EKD"
FALLBACK_KAT = "ECD"

# ---------------------------------------------------------------------------
# Stage 0 — Relevance filter
# ---------------------------------------------------------------------------

# Hard-block patterns — anything that matches these is immediately dropped.
_BLOCK_PATTERNS = re.compile(
    r"""
    # Korean / Thai / Japanese Unicode blocks (fandom content)
    [\uAC00-\uD7A3\u0E00-\u0E7F\u3040-\u30FF\u4E00-\u9FFF]
    |
    # Twitter hashtags followed by fandom/event noise (no whitespace after #word)
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
    # Pure entertainment event codes: ALL-CAPS with X / AT / FAM / ON AIR etc.
    \b(?:ON AIR WITH|ONAIR|PRESSTOUR|FANDOM LIVE|LIVEHOUSE|AOUBOOM|NETJJ|TFO|DMD)
    """,
    re.IGNORECASE | re.VERBOSE,
)

# Allow-list — keyword must contain at least ONE of these signals to pass.
# Drawn from taxonomy seeds + broader Indonesian governance/public-interest vocab.
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
    # Broader governance & public-interest Indonesian terms
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
    # English gov-adjacent terms that appear in Indonesian trending
    |israel|palestina|ukraine|russia|nato|pbb|un.security|imf|worldbank
    |iran|netanyahu|trump|biden|zelensky
    """,
    re.IGNORECASE | re.VERBOSE,
)


def is_relevant(keyword: str) -> tuple[bool, str]:
    """
    Stage 0 relevance gate.
    Returns (True, '') if keyword should be classified,
    or (False, reason) if it should be skipped.
    """
    # Hard block: entertainment patterns
    if _BLOCK_PATTERNS.search(keyword):
        return False, "entertainment/fandom pattern"

    # Must contain at least one governance/public-interest signal
    if not _RELEVANCE_SIGNALS.search(keyword):
        return False, "no governance signal"

    return True, ""


# ---------------------------------------------------------------------------
# Sentiment heuristics
# ---------------------------------------------------------------------------

NEGATIVE_TERMS = re.compile(
    r"korupsi|suap|hoaks|hack|bocor|phishing|penipuan|scam|judi|ilegal|deepfake|"
    r"phk|kemiskinan|pandemi|wabah|banjir|gempa|longsor|erupsi|konflik|bencana|"
    r"defisit|pengangguran|tipikor|kriminal|darurat",
    re.IGNORECASE,
)
POSITIVE_TERMS = re.compile(
    r"beasiswa|inovasi|luncurkan|berhasil|capaian|sukses|rekrut|pelatihan|literasi|"
    r"prestasi|bantuan|program|tumbuh|naik|meningkat|positif",
    re.IGNORECASE,
)


def classify_sentiment(keyword: str) -> str:
    if NEGATIVE_TERMS.search(keyword):
        return "NEG"
    if POSITIVE_TERMS.search(keyword):
        return "POS"
    return "NET"


def classify_prioritas(sub_kat: str, sentimen: str) -> str:
    """Tinggi (T) for high-priority categories with NEG sentiment; else Sedang or Rendah."""
    high_priority_cats = {"IPH", "KSD", "LKS", "KSB"}
    if sub_kat in high_priority_cats and sentimen == "NEG":
        return "T"
    if sub_kat in high_priority_cats:
        return "S"
    return "S"


# ---------------------------------------------------------------------------
# Classification logic
# ---------------------------------------------------------------------------

_classifier = None  # Lazy-load


def get_classifier():
    global _classifier
    if _classifier is None:
        print("Loading mDeBERTa zero-shot classifier (first run may take a moment)…")
        _classifier = pipeline(
            "zero-shot-classification",
            model="MoritzLaurer/mDeBERTa-v3-base-mnli-xnli",
        )
    return _classifier


def classify_keyword(keyword: str) -> dict:
    """
    Classify a single keyword using the 2-stage pipeline.
    Returns dict with kategori_utama, sub_kategori, sentimen, prioritas,
    confidence_score, is_auto_labeled.
    """
    kw_lower = keyword.lower()

    # Stage 1 — Rule-based
    for sub_kat, kat_utama, seeds in _RULES:
        for seed in seeds:
            if seed in kw_lower:
                sentimen = classify_sentiment(keyword)
                return {
                    "kategori_utama": kat_utama,
                    "sub_kategori": sub_kat,
                    "sentimen": sentimen,
                    "prioritas": classify_prioritas(sub_kat, sentimen),
                    "confidence_score": None,  # rule-based; schema says null is ok here
                    "is_auto_labeled": True,
                }

    # Stage 2 — Zero-shot NLI
    try:
        clf = get_classifier()
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


# ---------------------------------------------------------------------------
# Scrapers
# ---------------------------------------------------------------------------

SCROLL_JS = """
async () => {
    let previousHeight = 0;
    while (true) {
        window.scrollBy(0, document.body.scrollHeight);
        await new Promise(r => setTimeout(r, 1500));
        let newHeight = document.body.scrollHeight;
        if (newHeight === previousHeight) break;
        previousHeight = newHeight;
        let rows = document.querySelectorAll('tr');
        if (rows.length >= 105) break;
    }
}
"""


async def scrape_google_trends(crawler: AsyncWebCrawler) -> list[dict]:
    """Scrape up to 100 keywords from Google Trends Indonesia."""
    print("\n[GTR] Starting Google Trends scrape…")
    run_conf = CrawlerRunConfig(
        cache_mode=CacheMode.BYPASS,
        magic=True,
        delay_before_return_html=2.0,
        js_code=SCROLL_JS,
        wait_for="js:() => document.querySelectorAll('tr').length >= 100",
    )
    result = await crawler.arun(
        url="https://trends.google.com/trending?geo=ID&category=10",
        config=run_conf,
    )
    if not result.success:
        print("[GTR] ERROR: Failed to crawl Google Trends page.")
        return []

    soup = BeautifulSoup(result.html, "html.parser")
    rows = soup.find_all("tr")

    raw: list[dict] = []
    for row in rows:
        kw_div = row.find("div", class_="mZ3RIc")
        if kw_div:
            keyword = kw_div.get_text(strip=True)
            if keyword:
                raw.append({"rank": len(raw) + 1, "keyword": keyword})
        if len(raw) >= 100:
            break

    print(f"[GTR] Collected {len(raw)} keywords.")
    return raw


async def scrape_trends24(crawler: AsyncWebCrawler) -> list[dict]:
    """Scrape up to 100 keywords from Trends24 Indonesia."""
    print("\n[T24] Starting Trends24 scrape…")
    config = CrawlerRunConfig(
        js_code=["document.getElementById('tab-link-table').click();"],
        wait_for="js:() => { const rows = document.querySelectorAll('#table tbody tr'); return rows.length > 0; }",
    )
    result = await crawler.arun(url="https://trends24.in/indonesia/", config=config)
    if not result.success:
        print("[T24] ERROR: Failed to crawl Trends24 page.")
        return []

    soup = BeautifulSoup(result.html, "html.parser")
    table = soup.find("table", {"class": "the-table"})
    if not table:
        print("[T24] ERROR: Could not find .the-table element.")
        return []

    df = None
    try:
        import pandas as pd
        df = pd.read_html(io.StringIO(str(table)))[0]
    except Exception as exc:
        print(f"[T24] ERROR parsing table: {exc}")
        return []

    if "Rank" not in df.columns or "Trending Topic" not in df.columns:
        print(f"[T24] ERROR unexpected columns: {df.columns.tolist()}")
        return []

    df = df[["Rank", "Trending Topic"]].head(100)
    raw = [
        {"rank": int(row["Rank"]), "keyword": str(row["Trending Topic"])}
        for _, row in df.iterrows()
    ]
    print(f"[T24] Collected {len(raw)} keywords.")
    return raw


# ---------------------------------------------------------------------------
# Schema mapper
# ---------------------------------------------------------------------------

def build_item(
    source: str,      # "GTR" or "T24"
    rank: int,
    keyword: str,
    scraped_at: str,
    url: str | None,
) -> dict:
    """Build a schema-compliant ScrapedItem dict."""
    labels = classify_keyword(keyword)
    return {
        "id": str(uuid.uuid4()),
        "source_platform": source,
        "keyword": keyword,
        "url": url,
        "scraped_at": scraped_at,
        "trend_date": scraped_at[:10],   # YYYY-MM-DD
        "rank": rank,
        "search_volume": None,
        "volume_label": None,
        "related_queries": None,
        "geo": {"country": URL_GEO, "region": None},
        "kategori_utama": labels["kategori_utama"],
        "sub_kategori": labels["sub_kategori"],
        "sentimen": labels["sentimen"],
        "prioritas": labels["prioritas"],
        "is_auto_labeled": labels["is_auto_labeled"],
        "confidence_score": labels["confidence_score"],
        "ews_flag": False,
        "ews_reason": None,
        "raw_payload": None,
        "created_at": scraped_at,
        "updated_at": None,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def run():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    scraped_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    browser_conf = BrowserConfig(headless=True)

    async with AsyncWebCrawler(config=browser_conf) as crawler:
        gtr_raw = await scrape_google_trends(crawler)
        t24_raw = await scrape_trends24(crawler)

    all_items: list[dict] = []

    def process_source(
        raw: list[dict],
        source: str,
        url: str,
        label: str,
    ) -> tuple[int, int]:
        """Classify and filter keywords for one source. Returns (accepted, skipped)."""
        accepted = skipped = 0
        total = len(raw)
        print(f"\n[{label}] Running Stage 0 filter + classification ({total} raw keywords)…")
        for i, entry in enumerate(raw, 1):
            kw = entry["keyword"]
            ok, reason = is_relevant(kw)
            if not ok:
                print(f"  ✗ ({i:3}/{total}) SKIP [{reason}]  {kw}")
                skipped += 1
                continue
            print(f"  ✓ ({i:3}/{total}) KEEP  {kw}")
            item = build_item(
                source=source,
                rank=entry["rank"],
                keyword=kw,
                scraped_at=scraped_at,
                url=url,
            )
            all_items.append(item)
            accepted += 1
        return accepted, skipped

    gtr_ok, gtr_skip = process_source(
        gtr_raw, "GTR", "https://trends.google.com/trending?geo=ID", "GTR"
    )
    t24_ok, t24_skip = process_source(
        t24_raw, "T24", "https://trends24.in/indonesia/", "T24"
    )


    output_path = OUTPUT_DIR / f"merged_trends_{timestamp}.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(all_items, f, ensure_ascii=False, indent=2)

    print(f"\n✅ Done! {len(all_items)} items saved to {output_path}")
    print(f"   GTR  → accepted: {gtr_ok:3}  skipped: {gtr_skip:3}  (of {len(gtr_raw)})")
    print(f"   T24  → accepted: {t24_ok:3}  skipped: {t24_skip:3}  (of {len(t24_raw)})")


def main():
    asyncio.run(run())


if __name__ == "__main__":
    main()
