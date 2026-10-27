"""
Google Gemini LLM provider implementation using official google-genai SDK.

Purpose:
    Implements structured JSON generation using Gemini's native response_schema
    support, low concurrency queuing (MAX_LLM_CONCURRENCY=3), exponential backoff
    with jitter on 429/quota limits, and safety block handling.

Key Invariants:
    - Temperature locked to 0.0.
    - Model name is read dynamically from env (LLM_MODEL), never hardcoded.
    - Captures usage_metadata for run cost calculations.
"""

import json
import logging
import random
import threading
import time
from typing import Any, Dict, Optional, Tuple, Type, TypeVar

from pydantic import BaseModel

from app.core.config import settings
from app.core.errors import LLMBlockedError, LLMUnavailableError
from app.llm.client import LLMClient

logger = logging.getLogger("review_intel.llm.gemini")

T = TypeVar("T", bound=BaseModel)


class GeminiClient(LLMClient):
    """Client for Google Gemini models via google-genai SDK."""

    def __init__(self):
        api_key = settings.gemini_api_key
        if not api_key:
            raise LLMUnavailableError(
                "Missing GEMINI_API_KEY environment variable. "
                "Please configure GEMINI_API_KEY in your .env file or environment.",
                retryable=False,
            )

        try:
            from google import genai
            self.client = genai.Client(api_key=api_key)
        except Exception as exc:
            raise LLMUnavailableError(f"Failed to initialize google-genai client: {exc}")

        # Concurrency throttle for rate limits
        self._semaphore = threading.Semaphore(settings.max_llm_concurrency)

    def _call_raw_provider(
        self,
        prompt: str,
        schema: Type[T],
        temperature: float,
        model_name: str,
    ) -> Tuple[Dict[str, Any], Dict[str, int]]:
        """Invokes Gemini generate_content with structured JSON output."""
        from google.genai import types

        config = types.GenerateContentConfig(
            temperature=temperature,
            response_mime_type="application/json",
            response_schema=schema,
        )

        max_quota_retries = 4
        last_quota_error = None

        with self._semaphore:
            for attempt in range(max_quota_retries):
                try:
                    logger.debug("Calling Gemini model %s (attempt %d/%d)", model_name, attempt + 1, max_quota_retries)
                    response = self.client.models.generate_content(
                        model=model_name,
                        contents=prompt,
                        config=config,
                    )

                    # Inspect candidates and safety blocks
                    if not response.candidates:
                        raise LLMBlockedError("Gemini returned empty candidates list (possible safety block).")

                    candidate = response.candidates[0]
                    finish_reason = getattr(candidate, "finish_reason", None)
                    if finish_reason and "SAFETY" in str(finish_reason).upper():
                        raise LLMBlockedError(f"Gemini generation blocked by safety filters: {finish_reason}")

                    raw_text = response.text
                    if not raw_text:
                        raise LLMBlockedError("Gemini returned null text in response candidate.")

                    parsed_json = json.loads(raw_text)

                    # Extract token usage metadata
                    usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
                    if hasattr(response, "usage_metadata") and response.usage_metadata:
                        p_tokens = getattr(response.usage_metadata, "prompt_token_count", 0) or 0
                        c_tokens = getattr(response.usage_metadata, "candidates_token_count", 0) or 0
                        usage = {
                            "prompt_tokens": p_tokens,
                            "completion_tokens": c_tokens,
                            "total_tokens": p_tokens + c_tokens,
                        }

                    return parsed_json, usage

                except LLMBlockedError:
                    raise
                except Exception as exc:
                    err_msg = str(exc).lower()
                    # Detect 429 quota / rate limit errors
                    if "429" in err_msg or "quota" in err_msg or "rate limit" in err_msg:
                        last_quota_error = exc
                        sleep_time = (2 ** attempt) + random.uniform(0.5, 1.5)
                        logger.warning(
                            "Gemini rate limit / quota encountered (attempt %d/%d). Sleeping %.2fs...",
                            attempt + 1, max_quota_retries, sleep_time
                        )
                        time.sleep(sleep_time)
                    else:
                        logger.error("Gemini call error: %s", exc)
                        raise

            raise LLMUnavailableError(
                f"Gemini rate limit or quota exceeded after {max_quota_retries} retries: {last_quota_error}",
                retryable=True,
                details={"last_error": str(last_quota_error)},
            )
