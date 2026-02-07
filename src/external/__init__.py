"""External data source integration modules.

This package provides integration with external medical literature databases
and APIs for the Medical KAG system.
"""

from .pubmed_client import (
    PubMedClient,
    PaperMetadata,
    PubMedError,
    APIError,
    RateLimitError,
)

__all__ = [
    "PubMedClient",
    "PaperMetadata",
    "PubMedError",
    "APIError",
    "RateLimitError",
]
