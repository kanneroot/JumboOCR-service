"""
Vision-Language Model (VLM) OCR Service
Handles asynchronous concurrent API calls to Alibaba Cloud Qwen3.7-Flash VLM
via the official OpenAI-compatible SDK with automatic exponential backoff retry.
"""

import asyncio
import base64
import logging
import random
import time
from typing import Dict, Any, List
from openai import AsyncOpenAI

from app.config import settings

logger = logging.getLogger(__name__)


class VLMExtractionError(Exception):
    """Raised when VLM OCR processing fails after max retries."""
    pass


class VLMExtractor:
    """
    Asynchronous VLM OCR extractor using Alibaba Cloud Qwen3.7-Flash.
    """

    def __init__(self):
        if not settings.dashscope_api_key:
            logger.warning("DASHSCOPE_API_KEY is not configured! OCR requests will fail until configured.")

        # Initialize Async OpenAI client pointing to DashScope endpoint
        self.client = AsyncOpenAI(
            api_key=settings.dashscope_api_key or "sk-dummy",
            base_url=settings.dashscope_base_url
        )
        self.model_name = settings.model_name
        self.ocr_prompt = settings.ocr_prompt
        self.semaphore = asyncio.Semaphore(settings.max_concurrent_pages)

    async def _process_single_page(
        self,
        page_num: int,
        total_pages: int,
        png_bytes: bytes,
        max_retries: int = 5
    ) -> Dict[str, Any]:
        """
        Calls Qwen3.7-Flash VLM API for a single page with exponential backoff retry.
        """
        # Encode in-memory PNG to base64
        b64_img = base64.b64encode(png_bytes).decode("utf-8")
        data_uri = f"data:image/png;base64,{b64_img}"

        delay = 2.0
        last_error = None

        async with self.semaphore:
            for attempt in range(1, max_retries + 1):
                start_time = time.time()
                try:
                    logger.info("Sending Page %d/%d to %s (Attempt %d/%d)...",
                                page_num, total_pages, self.model_name, attempt, max_retries)

                    response = await self.client.chat.completions.create(
                        model=self.model_name,
                        messages=[
                            {
                                "role": "user",
                                "content": [
                                    {"type": "text", "text": self.ocr_prompt},
                                    {
                                        "type": "image_url",
                                        "image_url": {"url": data_uri}
                                    }
                                ]
                            }
                        ],
                        temperature=0.01,
                        max_tokens=4096
                    )

                    elapsed = round(time.time() - start_time, 3)
                    content = response.choices[0].message.content or ""
                    
                    usage = response.usage
                    prompt_tokens = usage.prompt_tokens if usage else 0
                    completion_tokens = usage.completion_tokens if usage else 0
                    total_tokens = usage.total_tokens if usage else 0

                    logger.info("Page %d/%d completed in %.2fs (%d tokens).",
                                page_num, total_pages, elapsed, total_tokens)

                    return {
                        "page_num": page_num,
                        "status": "success",
                        "markdown": content.strip(),
                        "elapsed_sec": elapsed,
                        "prompt_tokens": prompt_tokens,
                        "completion_tokens": completion_tokens,
                        "total_tokens": total_tokens
                    }

                except Exception as e:
                    last_error = str(e)
                    logger.warning("Page %d/%d attempt %d failed: %s",
                                   page_num, total_pages, attempt, last_error)

                    if attempt == max_retries:
                        break

                    # Exponential backoff with jitter
                    sleep_time = delay + random.uniform(0.1, 0.5)
                    await asyncio.sleep(sleep_time)
                    delay *= 2.0

            error_msg = f"Failed to OCR Page {page_num} after {max_retries} attempts. Error: {last_error}"
            logger.error(error_msg)
            raise VLMExtractionError(error_msg)

    async def extract_document(self, rendered_pages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Concurrently extracts Markdown from all rendered pages of a document.
        """
        if not settings.dashscope_api_key:
            raise VLMExtractionError(
                "DASHSCOPE_API_KEY is not configured. "
                "Set it in the .env file or as an environment variable."
            )

        total_pages = len(rendered_pages)
        tasks = [
            asyncio.create_task(
                self._process_single_page(
                    page_num=page["page_num"],
                    total_pages=total_pages,
                    png_bytes=page["png_bytes"]
                )
            )
            for page in rendered_pages
        ]

        try:
            # Process all pages concurrently respecting the semaphore
            results = await asyncio.gather(*tasks)
        except Exception:
            # Cancel any remaining in-flight tasks to avoid dangling API calls
            for task in tasks:
                if not task.done():
                    task.cancel()
            # Wait for cancellations to complete
            await asyncio.gather(*tasks, return_exceptions=True)
            raise

        # Sort results by page number to preserve natural document ordering
        results.sort(key=lambda x: x["page_num"])
        return results
