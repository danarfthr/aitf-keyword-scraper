import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

DB_URL = os.getenv("DATABASE_URL", "sqlite:///./keyword_scraper.db")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
