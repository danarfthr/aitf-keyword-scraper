import httpx
from bs4 import BeautifulSoup
from loguru import logger
from typing import List, Dict

from shared.shared.constants import MAX_ARTICLES_PER_CRAWLER, ArticleSource

# Detik
DETIK_SEARCH   = "https://www.detik.com/search/searchall?query={keyword}"
DETIK_LINKS    = "article a"
DETIK_TITLE    = "h1.detail__title"
DETIK_BODY     = "div.detail__body-text"

# Kompas
KOMPAS_SEARCH  = "https://search.kompas.com/search/?q={keyword}"
KOMPAS_LINKS   = ".article__list a"
KOMPAS_TITLE   = "h1.read__title"
KOMPAS_BODY    = "div.read__content"

# Tribun
TRIBUN_SEARCH  = "https://www.tribunnews.com/search?q={keyword}"
TRIBUN_LINKS   = ".lsi a"
TRIBUN_TITLE   = "h1.f40"
TRIBUN_BODY    = "div#article-2 p"

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}

async def crawl_detik(keyword: str) -> List[Dict]:
    return await _crawl_site(
        keyword, 
        ArticleSource.DETIK,
        DETIK_SEARCH,
        DETIK_LINKS,
        DETIK_TITLE,
        DETIK_BODY
    )

async def crawl_kompas(keyword: str) -> List[Dict]:
    return await _crawl_site(
        keyword, 
        ArticleSource.KOMPAS,
        KOMPAS_SEARCH,
        KOMPAS_LINKS,
        KOMPAS_TITLE,
        KOMPAS_BODY
    )

async def crawl_tribun(keyword: str) -> List[Dict]:
    return await _crawl_site(
        keyword, 
        ArticleSource.TRIBUN,
        TRIBUN_SEARCH,
        TRIBUN_LINKS,
        TRIBUN_TITLE,
        TRIBUN_BODY
    )

async def _crawl_site(keyword: str, source: str, search_url_template: str, links_selector: str, title_selector: str, body_selector: str) -> List[Dict]:
    # TODO: verify selectors are current
    import urllib.parse
    url = search_url_template.format(keyword=urllib.parse.quote(keyword))
    results = []
    
    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            resp = await client.get(url, headers=HEADERS)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")
            
            link_els = soup.select(links_selector)
            links = []
            for el in link_els:
                href = el.get("href")
                if href and href not in links:
                    links.append(href)
                    
            for link in links[:MAX_ARTICLES_PER_CRAWLER]:
                try:
                    art_resp = await client.get(link, headers=HEADERS)
                    art_resp.raise_for_status()
                    art_soup = BeautifulSoup(art_resp.text, "html.parser")
                    
                    title_el = art_soup.select_one(title_selector)
                    title = title_el.get_text(strip=True) if title_el else ""
                    
                    body_els = art_soup.select(body_selector)
                    body = "\\n".join(b.get_text(strip=True) for b in body_els if b.get_text(strip=True))
                    
                    results.append({
                        "source_site": source,
                        "url": link,
                        "title": title,
                        "body": body
                    })
                except (httpx.TimeoutException, httpx.HTTPStatusError) as e:
                    logger.warning(f"Error fetching article {link} from {source}: {e}")
                except Exception as e:
                    logger.warning(f"Unexpected error parsing article {link} from {source}: {e}")
                    
    except (httpx.TimeoutException, httpx.HTTPStatusError) as e:
        logger.warning(f"Error fetching search results for {keyword} from {source}: {e}")
    except Exception as e:
        logger.warning(f"Unexpected error in {source} crawler for {keyword}: {e}")
        
    return results
