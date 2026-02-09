<p align="center">
  <img src="docs/logo.svg" width="120" alt="Todoist MCP logo">
</p>

# Todoist MCP Server

[![Tests](https://github.com/amattas/todoist-mcp/actions/workflows/pythonpackage.yaml/badge.svg)](https://github.com/amattas/todoist-mcp/actions/workflows/pythonpackage.yaml)
[![codecov](https://codecov.io/gh/amattas/todoist-mcp/branch/main/graph/badge.svg)](https://codecov.io/gh/amattas/todoist-mcp)
[![CodeQL](https://github.com/amattas/todoist-mcp/actions/workflows/codeql.yml/badge.svg)](https://github.com/amattas/todoist-mcp/actions/workflows/codeql.yml)
[![Docs](https://github.com/amattas/todoist-mcp/actions/workflows/docs.yml/badge.svg)](https://github.com/amattas/todoist-mcp/actions/workflows/docs.yml)
[![Pages](https://img.shields.io/badge/docs-GitHub%20Pages-0A7ACC)](https://amattas.github.io/todoist-mcp/)
[![Python](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)

A specialized Model Context Protocol (MCP) server for Todoist task management. This Docker-based server enables Claude Desktop and other MCP clients to interact with Todoist for creating, updating, and querying tasks.

## Features

- **Task Management**: Create, update, complete, and delete tasks
- **Smart Queries**: Get tasks by project, label, priority, or filter
- **Project & Label Management**: Organize your tasks efficiently
- **Redis Caching**: Optional caching for improved performance
- **Docker Support**: Easy deployment with Docker and Docker Compose

## Prerequisites

- **Docker** and **Docker Compose** (for containerized deployment)
- **Todoist Account**: [Sign up for Todoist](https://todoist.com/)
- **Todoist API Token**: Get your token from [Todoist Integration Settings](https://todoist.com/prefs/integrations)
- **Claude Desktop** (optional): For MCP client integration

## Quick Start

### 1. Clone and Configure

```bash
cd todoist-mcp
cp .env.example .env.local
```

Edit `.env.local` and add your Todoist API token:

```env
TODOIST_API_TOKEN=your-todoist-api-token-here
DEBUG=false

# Optional Redis caching
REDIS_HOST=
REDIS_PORT=6379
REDIS_PASSWORD=
REDIS_USE_SSL=false
```

### 2. Run with Docker Compose

```bash
docker-compose up --build
```

The server will start in stdio mode, ready to accept MCP connections.

### 3. Connect to Claude Desktop

Add this configuration to your Claude Desktop config file:

**macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
**Windows**: `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "todoist": {
      "command": "docker",
      "args": ["compose", "-f", "/path/to/todoist-mcp/docker-compose.yml", "run", "--rm", "todoist-mcp"]
    }
  }
}
```

Restart Claude Desktop to activate the server.

## Configuration

### Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `TODOIST_API_TOKEN` | Yes | - | Your Todoist API token |
| `DEBUG` | No | `false` | Enable debug logging |
| `REDIS_HOST` | No | - | Redis server hostname (for caching) |
| `REDIS_PORT` | No | `6379` | Redis server port |
| `REDIS_PASSWORD` | No | - | Redis password |
| `REDIS_USE_SSL` | No | `false` | Use SSL for Redis connection |

## Available MCP Tools

The Todoist MCP server provides the following tools:

### Task Operations
- `create_task` - Create a new task
- `update_task` - Update an existing task
- `complete_task` - Mark a task as complete
- `delete_task` - Delete a task
- `uncomplete_task` - Reopen a completed task

### Task Queries
- `get_tasks_today` - Get all tasks due today
- `get_overdue_tasks` - Get all overdue tasks
- `get_tasks_by_project` - Get tasks from a specific project
- `get_tasks_by_label` - Get tasks with a specific label
- `get_tasks_by_priority` - Get tasks by priority level
- `get_tasks_by_filter` - Query tasks using Todoist filter syntax

### Project Management
- `get_projects` - List all projects
- `create_project` - Create a new project
- `update_project` - Update a project
- `delete_project` - Delete a project

### Label Management
- `get_labels` - List all labels
- `create_label` - Create a new label
- `update_label` - Update a label
- `delete_label` - Delete a label

### Server Management
- `get_server_status` - Check server health
- `get_server_config` - View server configuration
- `get_cache_stats` - View cache performance metrics
- `clear_cache` - Clear cached data
- `get_cache_info` - View Redis server information

## Local Development

### Without Docker

1. Create a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Set environment variables:
```bash
export TODOIST_API_TOKEN=your-api-token
```

4. Run the server:
```bash
python server.py
```

### With Docker

Build and run:
```bash
docker build -t todoist-mcp .
docker run -e TODOIST_API_TOKEN=your-token todoist-mcp
```

## Testing

### Test Server Status

You can test the server by connecting via Claude Desktop and asking:

> "What's the status of my Todoist server?"

### Test Task Operations

> "Create a task called 'Test task' in my Inbox"
> "Show me all tasks due today"
> "Mark task ID 12345 as complete"

## Troubleshooting

### "Todoist API token not configured"

**Solution**: Ensure `TODOIST_API_TOKEN` is set in your `.env.local` file or environment variables.

### Connection Issues

**Solution**:
- Verify your API token is correct
- Check your internet connection
- Ensure Docker container has network access

### Cache Not Working

**Solution**:
- Verify Redis connection settings
- Ensure Redis server is running
- Check Redis credentials and SSL settings

## Architecture

The Todoist MCP server follows this architecture:

```
Claude Desktop
     ↓ (stdio)
Docker Container
     ↓
MCP Server (FastMCP)
     ↓
Todoist Service
     ↓
Todoist API
```

Optional Redis caching layer improves performance by reducing API calls.

## Security Notes

- Never commit your `.env.local` file or API tokens to version control
- Use environment-specific `.env` files
- Consider using Docker secrets for production deployments
- API tokens are never exposed through MCP tool responses

## License

This project is provided as-is for personal use.

## Support

For Todoist API documentation, visit: https://developer.todoist.com/
