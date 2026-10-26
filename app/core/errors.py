"""
Typed exceptions and standardized error definitions for Review Intelligence MVP.

Purpose:
    Defines a coherent exception hierarchy corresponding directly to Section 8
    of the specification. Every error carries a machine-readable code, HTTP status,
    human-facing message, and retryable flag.

Design Decisions:
    - Never leak raw stack traces or internal secrets to API consumers.
    - Standard JSON payload: {"error": {"code": ..., "message": ..., "details": ...}}.
    - Error details provide actionable hints for UI banners and parameter refinement.
"""

from typing import Any, Dict, Optional
from fastapi import HTTPException, status


class ReviewIntelError(Exception):
    """Base exception for all domain errors in Review Intelligence."""

    def __init__(
        self,
        code: str,
        message: str,
        http_status: int = status.HTTP_500_INTERNAL_SERVER_ERROR,
        retryable: bool = False,
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status
        self.retryable = retryable
        self.details = details or {}

    def to_dict(self) -> Dict[str, Any]:
        """Serialize error for standard API responses and error.json artifacts."""
        return {
            "code": self.code,
            "message": self.message,
            "details": self.details,
            "retryable": self.retryable,
        }

    def to_http_exception(self) -> HTTPException:
        """Convert into FastAPI HTTPException."""
        return HTTPException(
            status_code=self.http_status,
            detail={"error": self.to_dict()},
        )


class AppNotFoundError(ReviewIntelError):
    """Raised when an app cannot be located on Google Play or Apple App Store."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            code="APP_NOT_FOUND",
            message=message,
            http_status=status.HTTP_404_NOT_FOUND,
            retryable=False,
            details=details,
        )


class InvalidConfigError(ReviewIntelError):
    """Raised when configuration filters, sample sizes, or country settings fail validation."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            code="INVALID_CONFIG",
            message=message,
            http_status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            retryable=False,
            details=details,
        )


class NoReviewsFoundError(ReviewIntelError):
    """Raised when zero reviews match the scrape filters."""

    def __init__(self, message: str = "Zero reviews found matching scrape filters. Consider widening date or star filters.", details: Optional[Dict[str, Any]] = None):
        super().__init__(
            code="NO_REVIEWS_FOUND",
            message=message,
            http_status=status.HTTP_400_BAD_REQUEST,
            retryable=False,
            details=details,
        )


class NotEnoughReviewsError(ReviewIntelError):
    """Raised when fewer than 30 reviews remain after text cleaning."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            code="NOT_ENOUGH_REVIEWS",
            message=message,
            http_status=status.HTTP_400_BAD_REQUEST,
            retryable=False,
            details=details,
        )


class SourceUnavailableError(ReviewIntelError):
    """Raised when an app store source cannot be reached after exponential backoff."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            code="SOURCE_UNAVAILABLE",
            message=message,
            http_status=status.HTTP_503_SERVICE_UNAVAILABLE,
            retryable=True,
            details=details,
        )


class LLMInvalidOutputError(ReviewIntelError):
    """Raised when LLM outputs fail schema validation after max retries."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            code="LLM_INVALID_OUTPUT",
            message=message,
            http_status=status.HTTP_502_BAD_GATEWAY,
            retryable=False,
            details=details,
        )


class LLMUnavailableError(ReviewIntelError):
    """Raised when Gemini API key is missing or quota/network fails after retry backoff."""

    def __init__(self, message: str, retryable: bool = False, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            code="LLM_UNAVAILABLE",
            message=message,
            http_status=status.HTTP_503_SERVICE_UNAVAILABLE,
            retryable=retryable,
            details=details,
        )


class LLMBlockedError(ReviewIntelError):
    """Raised when Gemini returns a safety block or empty candidates for a batch."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            code="LLM_BLOCKED",
            message=message,
            http_status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            retryable=False,
            details=details,
        )


class RunCancelledError(ReviewIntelError):
    """Raised when a run is cooperatively cancelled by user request."""

    def __init__(self, message: str = "Run was cancelled by user.", details: Optional[Dict[str, Any]] = None):
        super().__init__(
            code="RUN_CANCELLED",
            message=message,
            http_status=status.HTTP_409_CONFLICT,
            retryable=False,
            details=details,
        )
