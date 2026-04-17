from pydantic import BaseModel
from typing import List, Optional

class ManualKeywordInput(BaseModel):
    keyword: str
    source: str = "manual"

class PostKeywordsRequest(BaseModel):
    keywords: List[ManualKeywordInput]

class PostScrapeRequest(BaseModel):
    source: str
