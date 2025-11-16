# MCP Tools

The Todoist MCP server exposes MCP tools for task, project, and label management, as well as server and cache introspection.

Key categories include:

- **Task Operations**
  - `create_task`, `update_task`, `complete_task`, `delete_task`, `uncomplete_task`

- **Task Queries**
  - `get_tasks_today`, `get_overdue_tasks`
  - `get_tasks_by_project`, `get_tasks_by_label`, `get_tasks_by_priority`, `get_tasks_by_filter`

- **Project Management**
  - `get_projects`, `create_project`, `update_project`, `delete_project`

- **Label Management**
  - `get_labels`, `create_label`, `update_label`, `delete_label`

- **Server and Cache Management**
  - `get_server_status`, `get_server_config`
  - `get_cache_stats`, `clear_cache`, `get_cache_info`

See `src/server.py` and `src/services/todoist.py` for implementation details and full parameter lists.
