import asyncio
from datetime import datetime
import pandas as pd
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode
from bs4 import BeautifulSoup

scroll_js = """
async () => {
    let previousHeight = 0;
    while (true) {
        window.scrollBy(0, document.body.scrollHeight);
        await new Promise(r => setTimeout(r, 1500));
        let newHeight = document.body.scrollHeight;
        if (newHeight === previousHeight) break;
        previousHeight = newHeight;
        
        // Stop early if we have enough rows
        let rows = document.querySelectorAll('tr');
        if (rows.length >= 105) break;
    }
}
"""

async def main():
    print("Starting crawler...")
    browser_conf = BrowserConfig(headless=True)
    
    run_conf = CrawlerRunConfig(
        cache_mode=CacheMode.BYPASS,
        magic=True,
        delay_before_return_html=2.0,
        js_code=scroll_js,
        wait_for="js:() => document.querySelectorAll('tr').length >= 100"
    )

    async with AsyncWebCrawler(config=browser_conf) as crawler:
        result = await crawler.arun(
            url="https://trends.google.com/trending?geo=ID&category=10",
            config=run_conf
        )
        
        if not result.success:
            print("Failed to crawl the page")
            return

        print("Page crawled successfully! Parsing HTML...")
        soup = BeautifulSoup(result.html, 'html.parser')
        rows = soup.find_all('tr')
        
        trends_data = []
        for row in rows:
            keyword_div = row.find('div', class_='mZ3RIc')
            if keyword_div:
                keyword = keyword_div.get_text(strip=True)
                if keyword:
                    trends_data.append({
                        "Rank": len(trends_data) + 1,
                        "Keywords": keyword
                    })
            
            if len(trends_data) >= 100:
                break
                
        if not trends_data:
            print("No trends found.")
            return

        # Export to CSV
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"trends_{timestamp}.csv"
        
        df = pd.DataFrame(trends_data)
        df.to_csv(filename, index=False)
        print(f"Successfully exported {len(df)} rows to {filename}")
        print(df.head(10))

if __name__ == "__main__":
    asyncio.run(main())
