"""Shared constants used across all services. Do not modify without updating SPEC.md."""


class KeywordStatus:
    RAW          = "raw"
    NEWS_SAMPLED = "news_sampled"
    ENRICHED     = "enriched"
    EXPIRED      = "expired"
    FAILED       = "failed"

    ALL = [RAW, NEWS_SAMPLED, ENRICHED, EXPIRED, FAILED]


class KeywordSource:
    TRENDS24      = "trends24"
    GOOGLE_TRENDS = "google_trends"


class ArticleSource:
    DETIK  = "detik"
    Kompas = "kompas"
    TRIBUN = "tribun"
    CNBC   = "cnbc"
    CNN    = "cnn"
    ANTARA = "antara"


ARTICLE_SOURCES = [ArticleSource.DETIK, ArticleSource.Kompas, ArticleSource.TRIBUN, ArticleSource.CNBC, ArticleSource.CNN, ArticleSource.ANTARA]

# Characters before body is replaced by a truncated summary
SUMMARY_CHAR_THRESHOLD = 3000

# Max articles fetched per individual crawler (2 per crawler x 3 crawlers = 6 candidates)
MAX_ARTICLES_PER_CRAWLER = 2

# Max total articles saved per keyword after merging all crawlers
MAX_ARTICLES_TOTAL_PER_KEYWORD = 5

# Hours with no new articles before an enriched keyword is marked expired
EXPIRY_THRESHOLD_HOURS = 6

# Hours before irrelevant (is_relevant=false) keywords are marked expired
IRRELEVANT_EXPIRY_HOURS = 24

# Minutes before a failed keyword is auto-retried (reset to raw)
FAILED_RETRY_MINUTES = 30
