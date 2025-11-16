# Configuration

The Todoist MCP server is configured via environment variables, typically set in `.env.local` for Docker-based deployments.

## Core Environment Variables

| Variable            | Required | Default | Description                                 |
|---------------------|----------|---------|---------------------------------------------|
| `TODOIST_API_TOKEN` | Yes      | -       | Your Todoist API token                      |
| `DEBUG`             | No       | `false` | Enable debug logging                        |
| `REDIS_HOST`        | No       | -       | Redis server hostname (for caching)         |
| `REDIS_PORT`        | No       | `6379`  | Redis server port                           |
| `REDIS_PASSWORD`    | No       | -       | Redis password                              |
| `REDIS_USE_SSL`     | No       | `false` | Use SSL for Redis connection                |

When Redis is configured, the server uses `RedisCache` to cache Todoist responses and improve performance.

## Local Development

For local development without Docker:

1. Create and activate a virtual environment.
2. Install dependencies with `pip install -r requirements.txt`.
3. Export `TODOIST_API_TOKEN` (and other optional variables).
4. Run `python src/server.py`.
