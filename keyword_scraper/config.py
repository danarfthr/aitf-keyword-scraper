"""
config.py
=========
Constants, taxonomy rules, candidate labels, and parent mappings.
"""

from pathlib import Path

# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

OUTPUT_DIR = Path(__file__).parent.parent / "data"
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

# Pre-processed rules: list of (sub_kat, kat_utama, [seed, ...])
RULES: list[tuple[str, str, list[str]]] = [
    (sub, kat, [s.strip() for s in seeds.split(",")])
    for sub, kat, seeds in TAXONOMY_RULES
]

# ---------------------------------------------------------------------------
# Zero-shot candidate labels — Stage 2
# ---------------------------------------------------------------------------

CANDIDATE_LABELS: dict[str, str] = {
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

PARENT_MAP: dict[str, str] = {
    "IPH": "POG", "KLP": "POG", "KPM": "POG", "KSD": "POG",
    "KBS": "ECD", "ILT": "ECD", "EKD": "ECD", "KTK": "ECD",
    "LKS": "SEH", "PSD": "SEH", "KSB": "SEH",
}

FALLBACK_SUB = "EKD"
FALLBACK_KAT = "ECD"
