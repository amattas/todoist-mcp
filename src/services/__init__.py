"""
Todoist MCP Services Package
Contains service integrations for Todoist task management and caching.
"""

from .cache import (
    CacheConfig,
    CacheStats,
    CacheTTL,
    RedisCache,
    cache_aside,
    cache_key_generator,
)

# Import from the todoist module (service is in todoist.py, constants in todoist/)
from .todoist import TodoistService
from .todoist_constants import (
    COLOR_DESCRIPTIONS,
    PRIORITY_LABELS,
    VALID_COLORS,
    VALID_DURATION_UNITS,
    VALID_PRIORITIES,
    VALID_VIEW_STYLES,
)

__all__ = [
    "COLOR_DESCRIPTIONS",
    "PRIORITY_LABELS",
    "VALID_COLORS",
    "VALID_DURATION_UNITS",
    "VALID_PRIORITIES",
    "VALID_VIEW_STYLES",
    "CacheConfig",
    "CacheStats",
    "CacheTTL",
    "RedisCache",
    "TodoistService",
    "cache_aside",
    "cache_key_generator",
]
