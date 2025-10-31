# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a **Model Context Protocol (MCP) server** for Todoist task management. The server provides task, project, label, and comment management with optional Redis caching.

**Core Service:**
- **Todoist**: Full task management with advanced filtering, deadline support, and caching

**Deployment:**
- **HTTP mode** (`src/server_remote.py`): HTTP API with dual-factor authentication

## Quick Reference

**For user documentation**, see [README.md](README.md)

## Architecture

### Main Entry Points
- `src/server.py` - stdio MCP server
- `src/server_remote.py` - HTTP API server with dual-factor authentication

### Service Layer (`src/services/`)
- `src/services/todoist.py` - Todoist API integration with filtering and deadline management
- `src/services/cache.py` - Redis caching layer with cache-aside pattern

### Key Design Patterns
- Services initialized lazily via `get_todoist_service()` (src/server.py:58-91)
- Configuration changes trigger service reinitialization (src/server.py:62-70)
- Tools registered via `@mcp.tool()` decorator
- Optional Redis caching with `@cache_aside` decorator

## Environment Configuration

The server loads from `.env` and `.env.local` (`.env.local` takes precedence).

**Required:**
- `TODOIST_API_TOKEN` - Your Todoist API token

**Optional:**
- `TIMEZONE` - IANA timezone name (default: "US/Eastern")
- `DEBUG` - Enable debug logging (default: false)

**HTTP Mode:**
- `MCP_API_KEY` - API key for authentication (strongly recommended)
- `HOST` - Bind address (default: "0.0.0.0")
- `PORT` - Listen port (default: 8080)

**Redis Cache:**
- `REDIS_HOST` / `REDIS_SSL_PORT` / `REDIS_KEY` - Optional caching
- `CACHE_TTL_*` - Per-operation TTL overrides

## Development Commands

### Running Locally

**stdio mode:**
```bash
python -m src.server
```

**HTTP mode:**
```bash
MCP_API_KEY=test-key python -m src.server_remote
```

### Testing

```bash
# Run all tests
./scripts/run_tests.sh

# Specific test file
python -m pytest tests/test_todoist.py -v

# With coverage
python -m pytest tests/ --cov=src/services --cov-report=term-missing

# By marker
pytest -m todoist        # Todoist tests
pytest -m unit           # Unit tests
```

### Docker

```bash
docker build -t todoist-mcp .
docker run -e TODOIST_API_TOKEN=xxx -e MCP_API_KEY=yyy todoist-mcp
```

## Testing Architecture

Tests use pytest with extensive mocking via `conftest.py`. Key fixtures:
- `mock_todoist_api` - Mocked Todoist API responses
- `mock_redis` - Mocked Redis client
- `temp_todoist_service` - Temporary service instance

All tests avoid real API calls or live tokens.

## Key Implementation Details

### Todoist Service (`src/services/todoist.py`)

- Full CRUD operations for tasks, projects, labels, sections, comments
- Native Todoist filtering with fallback to manual filtering
- Deadline field support (separate from due_date)
- Cache-aside pattern with configurable TTLs
- Timezone-aware date handling
- Tools registered via `_register_mcp_tools()` when mcp instance provided

**Date Semantics:**
- `due_date`: When to START working on the task
- `deadline`: Drop-dead completion date (native Todoist field)

### Authentication (src/server_remote.py)

When `MCP_API_KEY` is set:
- **Dual-factor path**: `/app/{api_key}/{md5_hash}/mcp`
- MD5 hash: `hashlib.md5(api_key.encode()).hexdigest()`
- Endpoints:
  - MCP: `/app/{key}/{hash}/mcp` (authenticated)
  - Health: `/app/health` (public, no auth, fast)
- Use `scripts/verify_auth.py` to calculate correct URLs
- Security headers added automatically
- Access logs disabled to prevent key leakage
- Lazy service initialization on first authenticated request

### Caching Strategy

Redis cache-aside pattern with TTLs:
- Tasks: 60s
- Projects: 300s (5 min)
- Labels: 600s (10 min)
- Sections: 300s (5 min)

Cache keys: `todoist:{operation}:{identifier}`

## Common Gotchas

1. **Configuration hot-reload**: Service detects token changes and reinitializes (src/server.py:62-70)

2. **Service initialization**: Services are lazy-loaded. Always check for `None`:
   ```python
   service = get_todoist_service()
   if not service:
       return {"error": "Service not initialized"}
   ```

3. **MCP tool registration**:
   - Service tools: `todoist.py:_register_mcp_tools()`
   - Server tools: `server.py:@mcp.tool()`

4. **Relative imports**: Inside `src/`, use relative imports:
   ```python
   from .services.todoist import TodoistService  # Correct
   from services.todoist import TodoistService   # Wrong
   ```

5. **Docker deployment**: Multi-stage Dockerfile optimized for fast cold starts and small image size

## Server-Level Tools

Always available:
- `get_current_datetime` - Current date/time in configured timezone
- `get_server_status` - Service health and status
- `get_server_config` - Configuration (non-sensitive)

If Redis configured:
- `get_cache_stats` - Cache performance metrics
- `get_cache_info` - Redis server info
- `clear_cache` - Clear cache by pattern
- `reset_cache_stats` - Reset statistics

## Adding New Features

### New Todoist Tool
1. Add method to `TodoistService` (src/services/todoist.py)
2. Register in `_register_mcp_tools()`
3. Add tests in `tests/test_todoist.py`
4. Update documentation

### New Server Tool
1. Add to `src/server.py` with `@mcp.tool()` decorator
2. Add tests
3. Update documentation

### New Environment Variable
1. Add to initialization in `src/server.py`
2. Update `.env.example`
3. Update documentation

## Dependencies

- **fastmcp** - MCP server framework
- **todoist-api-python** - Official Todoist API client
- **redis** - Optional caching
- **fastapi** / **uvicorn** - HTTP server (server_remote.py)
- **python-dotenv** - Environment management

## Code Style

- Use type hints for parameters and returns
- Document with docstrings (Google style)
- Descriptive variable names
- Single responsibility functions
- Graceful error handling with try/except
- Consistent response format: `Dict[str, Any]`

## Error Response Format

```python
{
    "error": "Error description",
    "details": "Additional context"  # optional
}
```

Always catch and return error dicts:
```python
try:
    result = operation()
    return {"success": True, "data": result}
except Exception as e:
    logger.error(f"Failed: {e}")
    return {"error": str(e)}
```

## Logging

```python
import logging
logger = logging.getLogger(__name__)

logger.debug("Detail")     # DEBUG mode only
logger.info("Normal")       # Always
logger.warning("Warning")   # Warnings
logger.error("Error")       # Errors

# Enable via DEBUG env var
DEBUG=true
```

## Security Notes

1. **API Keys**: Never log full keys (truncate to 8 chars)
2. **Dual-Factor Auth**: MD5 hash adds second authentication factor
3. **Access Logs**: Disabled in HTTP mode to prevent key exposure
4. **Input Validation**: Validate all user inputs
5. **Error Messages**: Don't expose internal paths or tokens

## Debugging Tips

```python
# Check service status
from src.server import get_todoist_service
service = get_todoist_service()
if service:
    print(f"Projects: {len(service.get_projects())}")

# Enable debug logging
DEBUG=true python -m src.server

# Calculate auth URL
python scripts/verify_auth.py --api-key your-key --domain your-domain.com

# Test API connection
from todoist_api_python.api import TodoistAPI
api = TodoistAPI("your-token")
print(api.get_projects())
```

## File Structure

```
todoist-mcp/
├── src/
│   ├── server.py            # stdio entry (MCP tools)
│   ├── server_remote.py     # HTTP entry (with auth)
│   └── services/
│       ├── todoist.py       # Todoist service
│       └── cache.py         # Redis cache
├── tests/
│   ├── conftest.py          # Fixtures
│   ├── test_todoist.py      # Todoist tests
│   └── test_todoist_week.py # Weekly task tests
├── scripts/
│   ├── verify_auth.py       # Auth URL calculator
│   └── run_tests.sh         # Test runner
├── Dockerfile               # Multi-stage build (optimized)
├── docker-compose.yml       # Docker compose config
├── .env.example             # Config template
├── requirements.txt         # Dependencies
├── CLAUDE.md                # This file
└── README.md                # User documentation
```

## Documentation

- **README.md** - User documentation and deployment guides
- **CLAUDE.md** - This file, Claude Code specific guidance
- `.env.example` - Environment variable documentation

## Useful References

- **Todoist API**: https://developer.todoist.com/rest/v2/
- **FastMCP**: Framework documentation
- **MCP Protocol**: Model Context Protocol specification
- **Redis**: Cache backend documentation

## Configuration Change Detection

The server monitors `TODOIST_API_TOKEN` and reinitializes the service when it changes (src/server.py:62-70). This enables hot-reload without restarting the server.

## Dual-Factor Authentication

The HTTP server uses a two-part path authentication:
1. **API Key**: Secret key set via `MCP_API_KEY`
2. **MD5 Hash**: `hashlib.md5(api_key.encode()).hexdigest()`

Path pattern: `/app/{api_key}/{md5_hash}/mcp`

This prevents simple path enumeration attacks. Use `scripts/verify_auth.py` to calculate the correct URL.

## Docker Optimizations

The multi-stage Dockerfile:
1. **Build stage**: Compiles dependencies to wheels
2. **Runtime stage**: Installs from wheels (much faster)
3. **Bytecode**: Precompiled Python for faster startup
4. **Health check**: Fast endpoint that doesn't initialize services
5. **uvloop + httptools**: High-performance event loop and HTTP parser
6. **Single worker**: Optimized for serverless/scale-to-zero scenarios

When in doubt, consult:
1. This file for quick reference
2. README.md for deployment information
3. Test suite for usage examples
