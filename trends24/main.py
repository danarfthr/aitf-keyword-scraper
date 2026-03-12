import asyncio
import io
import pandas as pd
from datetime import datetime
from bs4 import BeautifulSoup
from crawl4ai import AsyncWebCrawler
from crawl4ai.async_configs import CrawlerRunConfig

async def scrape_trends24():
    print("Initializing Crawler...")
    async with AsyncWebCrawler() as crawler:
        # Configuration to click the "Table" tab and wait for rows to populate
        config = CrawlerRunConfig(
            js_code=["document.getElementById('tab-link-table').click();"],
            wait_for="js:() => { const rows = document.querySelectorAll('#table tbody tr'); return rows.length > 0; }"
        )
        
        url = "https://trends24.in/indonesia/"
        print(f"Fetching and executing JS on {url} ...")
        result = await crawler.arun(url=url, config=config)
        
        if not result.success:
            print("Failed to crawl the page.")
            return

        print("Parsing HTML...")
        soup = BeautifulSoup(result.html, "html.parser")
        
        # The table is expected to have class "the-table"
        table = soup.find("table", {"class": "the-table"})
        if not table:
            print("Could not find the table element with class 'the-table'.")
            return

        # Read HTML table into a pandas DataFrame
        df = pd.read_html(io.StringIO(str(table)))[0]
        
        # Select 'Rank' and 'Trending Topic' 
        if 'Rank' not in df.columns or 'Trending Topic' not in df.columns:
            print(f"Unexpected columns found: {df.columns.tolist()}")
            return
            
        df = df[['Rank', 'Trending Topic']]
        
        # Rename 'Trending Topic' to 'Keywords'
        df = df.rename(columns={'Trending Topic': 'Keywords'})
        
        # Keep only the first 100 rows
        df = df.head(100)
        
        # Generate the current date formatted as YYYY-MM-DD
        date_str = datetime.now()
        
        # Output DataFrame to CSV
        output_filename = f"trends24_indonesia_{date_str}.csv"
        df.to_csv(output_filename, index=False)
        print(f"Successfully scraped 100 trending keywords and saved to {output_filename}")

if __name__ == "__main__":
    asyncio.run(scrape_trends24())
