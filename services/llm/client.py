import asyncio
import os
import httpx
from loguru import logger

class LLMError(Exception):
    """Raised when OpenRouter returns a permanent failure after all retries."""

class OpenRouterClient:
    """
    Async client for OpenRouter chat completions API.
    Implements per-minute rate limiting and exponential retry.
    """
    BASE_URL = "https://openrouter.ai/api/v1/chat/completions"

    def __init__(self):
        self.api_key = os.environ.get("OPENROUTER_API_KEY", "")
        self.model = os.environ.get("LLM_MODEL", "anthropic/claude-3-haiku")
        
        calls_per_min = int(os.environ.get("LLM_MAX_CALLS_PER_MINUTE", "20"))
        self._semaphore = asyncio.Semaphore(calls_per_min)
        self._release_delay = 60.0
        
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://aitf.ugm.ac.id",
            "X-Title": "AITF-Tim1-KeywordManager",
        }

    async def _release_semaphore_later(self):
        await asyncio.sleep(self._release_delay)
        self._semaphore.release()

    async def chat(self, messages: list[dict]) -> str:
        """
        Send messages to OpenRouter. Returns assistant response as string.
        Rate-limited to LLM_MAX_CALLS_PER_MINUTE.
        Retries 3 times with 2s backoff on HTTP 429 or 5xx.
        Raises LLMError on permanent failure.
        """
        await self._semaphore.acquire()
        asyncio.ensure_future(self._release_semaphore_later())
        
        retries = 3
        delay = 2.0
        
        payload = {
            "model": self.model,
            "messages": messages,
        }
        
        for attempt in range(1, retries + 1):
            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    resp = await client.post(self.BASE_URL, headers=self.headers, json=payload)
                    
                    if resp.status_code in (429, 500, 502, 503, 504):
                        logger.warning(f"LLM API retrying {resp.status_code} on attempt {attempt}")
                        if attempt < retries:
                            await asyncio.sleep(delay ** attempt)
                            continue
                        raise LLMError(f"OpenRouter permanent failure after {retries} retries: {resp.status_code}")
                    
                    resp.raise_for_status()
                    data = resp.json()
                    
                    if "choices" in data and len(data["choices"]) > 0:
                        return data["choices"][0]["message"]["content"]
                    else:
                        raise LLMError("Unexpected response format from OpenRouter.")
                        
            except httpx.HTTPStatusError as e:
                # If we get here, it's not a 429/500/502/503/504
                raise LLMError(f"HTTP error: {e.response.status_code} - {e.response.text}")
            except httpx.RequestError as e:
                logger.warning(f"LLM API request error on attempt {attempt}: {e}")
                if attempt < retries:
                    await asyncio.sleep(delay ** attempt)
                    continue
                raise LLMError(f"OpenRouter permanent network failure: {e}")
                
        raise LLMError("Failed to fetch response from OpenRouter after retries.")
