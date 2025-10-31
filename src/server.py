#!/usr/bin/env python3
"""
Todoist MCP Server
A specialized MCP server for Todoist task management
"""

import os
import sys
import logging
from typing import Optional, Dict, Any
from dotenv import dotenv_values
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo

from fastmcp import FastMCP

# Import our service modules
from .services.todoist import TodoistService
from .services.cache import RedisCache

# Load environment variables with correct precedence
config: Dict[str, str] = {}

# Load from project directory if available
for filename in ('.env', '.env.local'):
    path = Path(filename)
    if path.exists():
        config.update(dotenv_values(path))

# Also check the script's directory (supports running from elsewhere)
script_dir = Path(__file__).parent
for filename in ('.env', '.env.local'):
    path = script_dir / filename
    if path.exists():
        config.update(dotenv_values(path))

# Apply loaded values without overriding existing environment vars
for key, value in config.items():
    os.environ.setdefault(key, value)

# Configure logging
logging.basicConfig(
    level=logging.DEBUG if os.getenv('DEBUG', 'false').lower() == 'true' else logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize MCP server
mcp = FastMCP(name="TodoistMCP")

# Service instances (will be initialized on first use)
_todoist_service: Optional[TodoistService] = None
_todoist_service_config: Optional[str] = None  # Track the config used to create the service
_cache_service: Optional[RedisCache] = None


def get_todoist_service() -> Optional[TodoistService]:
    """Get or initialize the Todoist service"""
    global _todoist_service, _todoist_service_config

    # Get current configuration
    current_config = os.getenv('TODOIST_API_TOKEN', '')

    # Check if configuration has changed or service doesn't exist
    if _todoist_service is None or _todoist_service_config != current_config:
        # Clean up old service if it exists
        if _todoist_service is not None:
            logger.info("Configuration changed, reinitializing Todoist service")
            _todoist_service = None

        api_token = os.getenv('TODOIST_API_TOKEN')
        if not api_token or api_token == 'your-todoist-api-token-here':
            logger.warning("Todoist API token not configured")
            return None

        try:
            # Get cache service if available
            cache = get_cache_service()
            _todoist_service = TodoistService(
                api_token=api_token,
                mcp=mcp,  # Pass MCP instance to service
                cache=cache  # Pass cache instance to service
            )
            _todoist_service_config = current_config  # Save the config that was used
            logger.info("Initialized Todoist service" + (" with caching" if cache else ""))
        except Exception as e:
            logger.error(f"Failed to initialize Todoist service: {e}")
            return None

    return _todoist_service


def get_cache_service() -> Optional[RedisCache]:
    """Get or initialize the Redis cache service"""
    global _cache_service

    if _cache_service is None:
        try:
            _cache_service = RedisCache.from_env()
            if _cache_service and _cache_service.is_connected():
                logger.info("Redis cache service initialized successfully")
            else:
                _cache_service = None
                logger.warning("Redis cache service not available")
        except Exception as e:
            logger.error(f"Failed to initialize Redis cache: {e}")
            _cache_service = None

    return _cache_service


# Register additional server-level tools
@mcp.tool(
    name="get_server_status",
    description="""Get the current status of the Todoist service.

## Returns
• Service status for Todoist integration
• Connection status and project count
• Overall server version

## Use Cases
• Health check
• Service monitoring
• Troubleshooting connections

## Related Tools
• Use `get_server_config` for configuration details""",
    title="Server Status",
    annotations={"title": "Server Status"}
)
def get_server_status() -> Dict[str, Any]:
    """Get the status of the Todoist service"""
    status = {
        "server": "TodoistMCP",
        "version": "1.0.0",
        "services": {}
    }

    # Check Todoist service
    todoist_service = get_todoist_service()
    if todoist_service:
        try:
            projects = todoist_service.get_projects()
            status["services"]["todoist"] = {
                "status": "active",
                "projects": len(projects)
            }
        except:
            status["services"]["todoist"] = {"status": "error"}
    else:
        status["services"]["todoist"] = {"status": "not_configured"}

    return status


@mcp.tool(
    name="get_server_config",
    description="""Get the current server configuration (non-sensitive values only).

## Returns
• Debug mode status
• Service configuration status
• Timezone configuration

## Use Cases
• Check configuration
• Verify settings
• Debug issues

## Related Tools
• Use `get_server_status` for service health

⚠️ **Note**: Sensitive values like API keys are not exposed""",
    title="Server Configuration",
    annotations={"title": "Server Configuration"}
)
def get_server_config() -> Dict[str, Any]:
    """Get the current server configuration (non-sensitive)"""
    return {
        "debug_mode": os.getenv('DEBUG', 'false').lower() == 'true',
        "todoist_configured": bool(os.getenv('TODOIST_API_TOKEN')),
        "timezone": os.getenv('TIMEZONE', 'US/Eastern')
    }


# ==================== Current DateTime Tool ====================

@mcp.tool(
    name="get_current_datetime",
    description="""Get the current date and time in the configured timezone.

## Returns
• Current date (YYYY-MM-DD format)
• Current time (HH:MM:SS format)
• Current datetime (ISO 8601 format)
• Configured timezone name
• UTC offset
• Day of week
• Unix timestamp

## Use Cases
• Reference current date/time for task scheduling
• Understand timezone context for deadlines
• Schedule tasks relative to current time

## Related Tools
• Use Todoist task creation tools with due dates
• Use `get_server_config` to see configured timezone

⚠️ **Note**: The timezone is configured via the TIMEZONE environment variable (default: US/Eastern)""",
    title="Current Date & Time",
    annotations={"title": "Current Date & Time"}
)
def get_current_datetime() -> Dict[str, Any]:
    """Get the current date and time in the configured timezone"""
    # Get timezone from environment variable, default to US/Eastern
    timezone_str = os.getenv('TIMEZONE', 'US/Eastern')

    try:
        tz = ZoneInfo(timezone_str)
    except Exception as e:
        logger.warning(f"Invalid timezone '{timezone_str}': {e}. Falling back to US/Eastern.")
        tz = ZoneInfo('US/Eastern')
        timezone_str = 'US/Eastern'

    # Get current datetime in the configured timezone
    now = datetime.now(tz)

    return {
        "date": now.strftime("%Y-%m-%d"),
        "time": now.strftime("%H:%M:%S"),
        "datetime": now.isoformat(),
        "timezone": timezone_str,
        "utc_offset": now.strftime("%z"),
        "timezone_abbr": now.strftime("%Z"),
        "day_of_week": now.strftime("%A"),
        "timestamp": int(now.timestamp())
    }


# ==================== Cache Management Tools ====================

@mcp.tool(
    name="get_cache_stats",
    description="""Get Redis cache statistics and performance metrics.

## Returns
• Hit/miss rates
• Average response times
• Error counts
• Total requests
• Uptime

## Use Cases
• Monitor cache performance
• Debug caching issues
• Optimize cache configuration

## Related Tools
• Use `clear_cache` to clear cache entries
• Use `get_cache_info` for Redis server info""",
    title="Cache Statistics",
    annotations={"title": "Cache Statistics"}
)
def get_cache_stats() -> Dict[str, Any]:
    """Get cache statistics"""
    cache = get_cache_service()
    if not cache:
        return {"error": "Cache service not available"}

    stats = cache.get_stats()
    return stats.to_dict()


@mcp.tool(
    name="clear_cache",
    description="""Clear cache entries by pattern or all cache data.

## Parameters
• pattern: Pattern to match keys (e.g., "todoist:*"). If not provided, clears ALL cache.

## Use Cases
• Clear stale data
• Force refresh of cached data
• Debug caching issues

## Related Tools
• Use `get_cache_stats` to view cache metrics
• Use `get_cache_info` for Redis server info

⚠️ **Warning**: Clearing all cache may impact performance temporarily""",
    title="Clear Cache",
    annotations={"title": "Clear Cache"}
)
def clear_cache(pattern: Optional[str] = None) -> Dict[str, Any]:
    """Clear cache entries"""
    cache = get_cache_service()
    if not cache:
        return {"error": "Cache service not available"}

    if pattern:
        # Clear by pattern
        deleted = cache.delete_pattern(pattern)
        return {
            "status": "success",
            "pattern": pattern,
            "keys_deleted": deleted
        }
    else:
        # Clear all cache
        if cache.flush_all():
            return {
                "status": "success",
                "message": "All cache cleared"
            }
        else:
            return {
                "status": "error",
                "message": "Failed to clear cache"
            }


@mcp.tool(
    name="get_cache_info",
    description="""Get Redis server information and cache configuration.

## Returns
• Redis version
• Memory usage
• Connected clients
• Keyspace info
• Configuration details

## Use Cases
• Monitor cache health
• Check Redis server status
• View cache configuration

## Related Tools
• Use `get_cache_stats` for performance metrics
• Use `clear_cache` to clear cache entries""",
    title="Cache Information",
    annotations={"title": "Cache Information"}
)
def get_cache_info() -> Dict[str, Any]:
    """Get Redis server information"""
    cache = get_cache_service()
    if not cache:
        return {"error": "Cache service not available"}

    info = cache.info()

    # Extract key information
    return {
        "connected": cache.is_connected(),
        "host": cache.host,
        "port": cache.port,
        "ssl_enabled": cache.use_ssl,
        "server": {
            "redis_version": info.get("redis_version", "unknown"),
            "uptime_seconds": info.get("uptime_in_seconds", 0),
            "connected_clients": info.get("connected_clients", 0),
            "used_memory_human": info.get("used_memory_human", "unknown"),
            "used_memory_peak_human": info.get("used_memory_peak_human", "unknown")
        },
        "keyspace": {
            db: stats for db, stats in info.items()
            if db.startswith("db")
        }
    }


@mcp.tool(
    name="reset_cache_stats",
    description="""Reset cache performance statistics.

## Use Cases
• Start fresh monitoring period
• Clear old statistics
• Begin new performance measurement

## Related Tools
• Use `get_cache_stats` to view current statistics""",
    title="Reset Cache Statistics",
    annotations={"title": "Reset Cache Statistics"}
)
def reset_cache_stats() -> Dict[str, Any]:
    """Reset cache statistics"""
    cache = get_cache_service()
    if not cache:
        return {"error": "Cache service not available"}

    cache.reset_stats()
    return {
        "status": "success",
        "message": "Cache statistics reset"
    }


# Initialize services on startup
def initialize_services():
    """Initialize all configured services"""
    logger.info("Initializing Todoist service...")

    # Initialize Todoist service
    todoist = get_todoist_service()
    if todoist:
        logger.info("✓ Todoist service initialized")


if __name__ == "__main__":
    # Run the MCP server
    logger.info("Starting TodoistMCP server...")

    # Initialize services
    initialize_services()

    # Check configuration
    if not os.getenv('TODOIST_API_TOKEN') or os.getenv('TODOIST_API_TOKEN') == 'your-todoist-api-token-here':
        logger.warning("Todoist API token not configured. Set TODOIST_API_TOKEN in .env.local or .env")

    # Run the server using stdio transport
    mcp.run()
