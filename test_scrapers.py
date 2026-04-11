import asyncio
from services.scraper.trends24 import scrape_trends24
from services.scraper.google_trends import scrape_google_trends

async def main():
    t24 = await scrape_trends24()
    print("Trends24:", t24[:2])
    gtr = await scrape_google_trends()
    print("Google Trends:", gtr[:2])

if __name__ == "__main__":
    asyncio.run(main())
