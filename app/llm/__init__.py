"""
LLM abstraction package with provider interface, Gemini, Fake LLM, schemas, and prompts.
"""

from app.llm.client import LLMClient, get_llm_client
from app.llm.schemas import (
    BatchClassificationOutput,
    CategoryAssignment,
    CategoryDefinition,
    CategorySummaryOutput,
    ExecutiveSummaryOutput,
    NullCategory,
    ReconciliationOutput,
    ReviewClassification,
    ReviewType,
    TaxonomyOutput,
)

__all__ = [
    "BatchClassificationOutput",
    "CategoryAssignment",
    "CategoryDefinition",
    "CategorySummaryOutput",
    "ExecutiveSummaryOutput",
    "LLMClient",
    "NullCategory",
    "ReconciliationOutput",
    "ReviewClassification",
    "ReviewType",
    "TaxonomyOutput",
    "get_llm_client",
]
