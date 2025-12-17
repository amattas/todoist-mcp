"""Shared fixtures and configuration for tests"""

import os
from datetime import date, datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ============================================================================
# Mock Classes
# ============================================================================


class MockTodoistTask:
    """Mock Todoist Task object"""

    def __init__(self, **kwargs):
        self.id = kwargs.get("id", "123")
        self.content = kwargs.get("content", "Test Task")
        self.description = kwargs.get("description", "")
        self.is_completed = kwargs.get("is_completed", False)
        self.labels = kwargs.get("labels", [])
        self.priority = kwargs.get("priority", 1)
        self.comment_count = kwargs.get("comment_count", 0)
        self.created_at = kwargs.get("created_at", datetime.now(timezone.utc).isoformat())
        self.creator_id = kwargs.get("creator_id", "user123")
        self.assignee_id = kwargs.get("assignee_id")
        self.assigner_id = kwargs.get("assigner_id")
        self.project_id = kwargs.get("project_id", "proj123")
        self.section_id = kwargs.get("section_id")
        self.parent_id = kwargs.get("parent_id")
        self.order = kwargs.get("order", 0)
        self.url = kwargs.get("url", f"https://todoist.com/tasks/{self.id}")
        self.due = kwargs.get("due")
        self.duration = kwargs.get("duration")


class MockTodoistDue:
    """Mock Todoist Due object"""

    def __init__(self, **kwargs):
        self.date = kwargs.get("date", date.today())
        self.string = kwargs.get("string", "today")
        self.datetime = kwargs.get("datetime")
        self.timezone = kwargs.get("timezone")
        self.is_recurring = kwargs.get("is_recurring", False)


class MockTodoistProject:
    """Mock Todoist Project object"""

    def __init__(self, **kwargs):
        self.id = kwargs.get("id", "proj123")
        self.name = kwargs.get("name", "Test Project")
        self.color = kwargs.get("color", "blue")
        self.parent_id = kwargs.get("parent_id")
        self.order = kwargs.get("order", 0)
        self.is_shared = kwargs.get("is_shared", False)
        self.is_favorite = kwargs.get("is_favorite", False)
        self.is_inbox_project = kwargs.get("is_inbox_project", False)
        self.is_archived = kwargs.get("is_archived", False)
        self.is_collapsed = kwargs.get("is_collapsed", False)
        self.view_style = kwargs.get("view_style", "list")
        self.url = kwargs.get("url", f"https://todoist.com/projects/{self.id}")
        self.description = kwargs.get("description", "")
        self.workspace_id = kwargs.get("workspace_id")
        self.folder_id = kwargs.get("folder_id")


class MockTodoistLabel:
    """Mock Todoist Label object"""

    def __init__(self, **kwargs):
        self.id = kwargs.get("id", "label123")
        self.name = kwargs.get("name", "test-label")
        self.color = kwargs.get("color", "red")
        self.order = kwargs.get("order", 0)
        self.is_favorite = kwargs.get("is_favorite", False)


class MockTodoistSection:
    """Mock Todoist Section object"""

    def __init__(self, **kwargs):
        self.id = kwargs.get("id", "section123")
        self.name = kwargs.get("name", "Test Section")
        self.project_id = kwargs.get("project_id", "proj123")
        self.order = kwargs.get("order", 0)


class MockTodoistComment:
    """Mock Todoist Comment object"""

    def __init__(self, **kwargs):
        self.id = kwargs.get("id", "comment123")
        self.content = kwargs.get("content", "Test comment")
        self.posted_at = kwargs.get("posted_at", datetime.now(timezone.utc).isoformat())
        self.task_id = kwargs.get("task_id")
        self.project_id = kwargs.get("project_id")
        self.attachment = kwargs.get("attachment")


class MockTodoistCollaborator:
    """Mock Todoist Collaborator object"""

    def __init__(self, **kwargs):
        self.id = kwargs.get("id", "collab123")
        self.name = kwargs.get("name", "Test User")
        self.email = kwargs.get("email", "test@example.com")


class MockCompletedTasksResult:
    """Mock result for completed tasks API"""

    def __init__(self, items=None, cursor=None, has_more=False):
        self.items = items or []
        self.cursor = cursor
        self.has_more = has_more


# ============================================================================
# Todoist Fixtures
# ============================================================================


@pytest.fixture
def mock_todoist_api():
    """Mock TodoistAPI client"""
    with patch("src.services.todoist.TodoistAPI") as mock_api_class:
        mock_api = MagicMock()
        mock_api_class.return_value = mock_api

        # Setup default responses for common operations
        mock_api.get_projects.return_value = iter(
            [
                [
                    MockTodoistProject(id="1", name="Work"),
                    MockTodoistProject(id="2", name="Personal", is_inbox_project=True),
                ]
            ]
        )

        mock_api.get_labels.return_value = iter(
            [
                [
                    MockTodoistLabel(id="1", name="urgent"),
                    MockTodoistLabel(id="2", name="work"),
                ]
            ]
        )

        mock_api.get_tasks.return_value = iter(
            [
                [
                    MockTodoistTask(id="1", content="Task 1"),
                    MockTodoistTask(id="2", content="Task 2", priority=4),
                ]
            ]
        )

        mock_api.add_task.return_value = MockTodoistTask(id="new123", content="New Task")

        mock_api.update_task.return_value = MockTodoistTask(id="123", content="Updated Task")

        mock_api.complete_task.return_value = True
        mock_api.uncomplete_task.return_value = True
        mock_api.delete_task.return_value = True

        mock_api.get_project.return_value = MockTodoistProject(id="1", name="Work")
        mock_api.get_section.return_value = MockTodoistSection(id="1", name="In Progress")
        mock_api.get_label.return_value = MockTodoistLabel(id="1", name="urgent")

        # Task operations
        mock_api.add_task_quick.return_value = MockTodoistTask(id="quick123", content="Quick Task")
        mock_api.move_task.return_value = MockTodoistTask(
            id="123", content="Moved Task", project_id="new_proj"
        )
        mock_api.get_completed_tasks_by_completion_date.return_value = MockCompletedTasksResult(
            items=[MockTodoistTask(id="done1", content="Done Task", is_completed=True)],
            has_more=False,
        )
        mock_api.get_completed_tasks_by_due_date.return_value = MockCompletedTasksResult(
            items=[MockTodoistTask(id="done2", content="Done Task 2", is_completed=True)],
            has_more=False,
        )

        # Project operations
        mock_api.add_project.return_value = MockTodoistProject(id="new_proj", name="New Project")
        mock_api.update_project.return_value = MockTodoistProject(id="1", name="Updated Project")
        mock_api.delete_project.return_value = True
        mock_api.archive_project.return_value = True
        mock_api.unarchive_project.return_value = True
        mock_api.get_collaborators.return_value = [
            MockTodoistCollaborator(id="user1", name="Alice", email="alice@example.com"),
            MockTodoistCollaborator(id="user2", name="Bob", email="bob@example.com"),
        ]

        # Section operations
        mock_api.get_sections.return_value = iter(
            [
                [
                    MockTodoistSection(id="1", name="To Do", project_id="proj123"),
                    MockTodoistSection(id="2", name="In Progress", project_id="proj123"),
                ]
            ]
        )
        mock_api.add_section.return_value = MockTodoistSection(id="new_sec", name="New Section")
        mock_api.update_section.return_value = MockTodoistSection(id="1", name="Updated Section")
        mock_api.delete_section.return_value = True

        # Label operations
        mock_api.add_label.return_value = MockTodoistLabel(id="new_label", name="new-label")
        mock_api.update_label.return_value = MockTodoistLabel(id="1", name="updated-label")
        mock_api.delete_label.return_value = True
        mock_api.get_shared_labels.return_value = ["shared1", "shared2"]
        mock_api.rename_shared_label.return_value = True
        mock_api.remove_shared_label.return_value = True

        # Comment operations
        mock_api.get_comments.return_value = iter(
            [
                [
                    MockTodoistComment(id="1", content="Comment 1", task_id="task123"),
                    MockTodoistComment(id="2", content="Comment 2", task_id="task123"),
                ]
            ]
        )
        mock_api.get_comment.return_value = MockTodoistComment(id="1", content="Single Comment")
        mock_api.add_comment.return_value = MockTodoistComment(
            id="new_comment", content="New Comment"
        )
        mock_api.update_comment.return_value = MockTodoistComment(id="1", content="Updated Comment")
        mock_api.delete_comment.return_value = True

        yield mock_api


@pytest.fixture
def todoist_service(mock_todoist_api):
    """Create TodoistService with mocked API"""
    with patch.dict(os.environ, {"TODOIST_API_TOKEN": "test_token", "TIMEZONE": "UTC"}):
        from src.services.todoist import TodoistService

        service = TodoistService("test_token")
        return service


# ============================================================================
# Server/MCP Fixtures
# ============================================================================


@pytest.fixture
def mock_fastmcp():
    """Mock FastMCP server"""
    mock_mcp = MagicMock()
    mock_mcp.tool = MagicMock(return_value=lambda func: func)
    mock_mcp.resource = MagicMock(return_value=lambda func: func)
    mock_mcp.prompt = MagicMock(return_value=lambda func: func)
    return mock_mcp


@pytest.fixture
def mock_env_vars():
    """Set up environment variables for testing"""
    env_vars = {
        "TODOIST_API_TOKEN": "test_todoist_token",
        "MCP_API_KEY": "test_mcp_key",
        "TIMEZONE": "US/Eastern",
    }
    with patch.dict(os.environ, env_vars):
        yield env_vars


# ============================================================================
# Async Fixtures
# ============================================================================


@pytest.fixture
def async_mock():
    """Create an async mock function"""
    return AsyncMock()


# ============================================================================
# Test Data Fixtures
# ============================================================================


@pytest.fixture
def test_dates():
    """Common test dates"""
    now = datetime.now(timezone.utc)
    return {
        "today": now.date(),
        "tomorrow": (now + timedelta(days=1)).date(),
        "yesterday": (now - timedelta(days=1)).date(),
        "next_week": (now + timedelta(days=7)).date(),
        "last_week": (now - timedelta(days=7)).date(),
        "now": now,
        "one_hour_ago": now - timedelta(hours=1),
        "one_hour_later": now + timedelta(hours=1),
    }


@pytest.fixture
def test_priorities():
    """Todoist priority mappings"""
    return {"urgent": 4, "high": 3, "medium": 2, "low": 1, "default": 1}


@pytest.fixture
def test_colors():
    """Todoist color options"""
    return [
        "berry_red",
        "red",
        "orange",
        "yellow",
        "olive_green",
        "lime_green",
        "green",
        "mint_green",
        "teal",
        "sky_blue",
        "light_blue",
        "blue",
        "grape",
        "violet",
        "lavender",
        "magenta",
        "salmon",
        "charcoal",
        "grey",
        "taupe",
    ]
