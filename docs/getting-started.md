# Getting Started

This guide walks through running the Todoist MCP server and connecting it to Todoist.

## Prerequisites

- Docker and Docker Compose (for containerized deployment)
- A Todoist account and API token
- Optionally, Claude Desktop for MCP integration

## Clone and Configure

```bash
cd todoist-mcp
cp .env.example .env.local
```

Edit `.env.local` and set at least:

```env
TODOIST_API_TOKEN=your-todoist-api-token-here
DEBUG=false
```

You can also configure optional Redis caching variables here.

## Run with Docker Compose

```bash
docker-compose up --build
```

The server will start in stdio mode inside the container, ready to accept MCP connections.

## Connect to Claude Desktop

Update your Claude Desktop configuration file:

- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
- Windows: `%APPDATA%\\Claude\\claude_desktop_config.json`

Example configuration:

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
