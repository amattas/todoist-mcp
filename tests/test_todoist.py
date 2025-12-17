"""Unit tests for Todoist service"""

from datetime import date
from unittest.mock import patch

import pytest

from src.services.todoist import TodoistService
from tests.conftest import (
    MockTodoistDue,
    MockTodoistLabel,
    MockTodoistProject,
    MockTodoistTask,
)


class TestTodoistService:
    """Test suite for TodoistService"""

    # ========== INITIALIZATION TESTS ==========

    def test_init_with_token(self):
        """Test service initialization with API token"""
        with patch("src.services.todoist.TodoistAPI") as mock_api:
            service = TodoistService(api_token="test_token")
            assert service.api_token == "test_token"
            mock_api.assert_called_once_with("test_token")

    def test_init_with_env_token(self):
        """Test service initialization with environment variable"""
        with (
            patch.dict("os.environ", {"TODOIST_API_TOKEN": "env_token"}),
            patch("src.services.todoist.TodoistAPI") as mock_api,
        ):
            service = TodoistService()
            assert service.api_token == "env_token"
            mock_api.assert_called_once_with("env_token")

    def test_init_without_token_raises_error(self):
        """Test that initialization without token raises ValueError"""
        with (
            patch.dict("os.environ", {}, clear=True),
            pytest.raises(ValueError, match="Todoist API token is required"),
        ):
            TodoistService()

    # ========== VALIDATION TESTS ==========

    @pytest.mark.parametrize(
        "priority,expected",
        [("1", 1), ("2", 2), ("3", 3), ("4", 4), (1, 1), (4, 4), (None, None)],
    )
    def test_validate_priority_valid(self, todoist_service, priority, expected):
        """Test priority validation with valid values"""
        result = todoist_service._validate_priority(priority)
        assert result == expected

    @pytest.mark.parametrize("priority", ["5", "0", "-1", "invalid", 5, 0])
    def test_validate_priority_invalid(self, todoist_service, priority):
        """Test priority validation with invalid values"""
        with pytest.raises(ValueError, match="Invalid priority"):
            todoist_service._validate_priority(priority)

    @pytest.mark.parametrize("duration_unit", ["minute", "day", None])
    def test_validate_duration_unit_valid(self, todoist_service, duration_unit):
        """Test duration unit validation with valid values"""
        todoist_service._validate_duration_unit(duration_unit)  # Should not raise

    @pytest.mark.parametrize("duration_unit", ["hour", "week", "invalid"])
    def test_validate_duration_unit_invalid(self, todoist_service, duration_unit):
        """Test duration unit validation with invalid values"""
        with pytest.raises(ValueError, match="Invalid duration_unit"):
            todoist_service._validate_duration_unit(duration_unit)

    def test_validate_project_id_valid(self, todoist_service, mock_todoist_api):
        """Test project ID validation with existing project"""
        mock_todoist_api.get_project.return_value = MockTodoistProject(id="proj123")
        todoist_service._validate_project_id("proj123")  # Should not raise
        mock_todoist_api.get_project.assert_called_once_with("proj123")

    def test_validate_project_id_invalid(self, todoist_service, mock_todoist_api):
        """Test project ID validation with non-existent project"""
        mock_todoist_api.get_project.side_effect = Exception("Project not found")
        with pytest.raises(ValueError, match="Invalid project_id"):
            todoist_service._validate_project_id("invalid_id")

    def test_validate_section_id_valid(self, todoist_service, mock_todoist_api):
        """Test section ID validation with existing section"""
        from tests.conftest import MockTodoistSection

        mock_todoist_api.get_section.return_value = MockTodoistSection(id="sec123")
        todoist_service._validate_section_id("sec123")  # Should not raise
        mock_todoist_api.get_section.assert_called_once_with("sec123")

    def test_validate_label_names_valid(self, todoist_service):
        """Test label validation with existing labels"""
        todoist_service._validate_label_names(["urgent", "work"])  # Should not raise

    def test_validate_label_names_invalid(self, todoist_service):
        """Test label validation with non-existent labels"""
        with pytest.raises(ValueError, match="Invalid label"):
            todoist_service._validate_label_names(["nonexistent"])

    @pytest.mark.parametrize("date_str", ["2024-12-31", "2024-01-01", "2025-06-15"])
    def test_validate_due_date_format_valid(self, todoist_service, date_str):
        """Test due date format validation with valid dates"""
        todoist_service._validate_due_date_format(date_str)  # Should not raise

    @pytest.mark.parametrize("date_str", ["12/31/2024", "2024-13-01", "invalid", "tomorrow"])
    def test_validate_due_date_format_invalid(self, todoist_service, date_str):
        """Test due date format validation with invalid dates"""
        with pytest.raises(ValueError, match="Invalid due_date format"):
            todoist_service._validate_due_date_format(date_str)

    def test_validate_color_valid(self, todoist_service, test_colors):
        """Test color validation with valid colors"""
        for color in test_colors:
            todoist_service._validate_color(color)  # Should not raise

    def test_validate_color_invalid(self, todoist_service):
        """Test color validation with invalid color"""
        with pytest.raises(ValueError, match="Invalid color"):
            todoist_service._validate_color("invalid_color")

    @pytest.mark.parametrize("view_style", ["list", "board", None])
    def test_validate_view_style_valid(self, todoist_service, view_style):
        """Test view style validation with valid values"""
        todoist_service._validate_view_style(view_style)  # Should not raise

    def test_validate_view_style_invalid(self, todoist_service):
        """Test view style validation with invalid value"""
        with pytest.raises(ValueError, match="Invalid view_style"):
            todoist_service._validate_view_style("kanban")

    # ========== TASK OPERATION TESTS ==========

    def test_get_tasks(self, todoist_service, mock_todoist_api):
        """Test getting tasks"""
        tasks = todoist_service.get_tasks()
        assert len(tasks) == 2
        assert tasks[0]["content"] == "Task 1"
        assert tasks[1]["priority"] == 4

    def test_get_tasks_with_filters(self, todoist_service, mock_todoist_api):
        """Test getting tasks with filters"""
        todoist_service.get_tasks(project_id="proj123", label="urgent")
        mock_todoist_api.get_tasks.assert_called_once_with(
            project_id="proj123", section_id=None, label="urgent", ids=None
        )

    def test_get_tasks_with_pagination(self, todoist_service, mock_todoist_api):
        """Test getting tasks with pagination"""
        # Mock API returning 10 tasks
        mock_tasks = [
            MockTodoistTask(id=str(i), content=f"Task {i}", priority=1) for i in range(10)
        ]
        mock_todoist_api.get_tasks.return_value = iter([mock_tasks])

        # Get first 3 tasks
        tasks = todoist_service.get_tasks(limit=3, offset=0)
        assert len(tasks) == 3
        assert tasks[0]["id"] == "0"
        assert tasks[0]["content"] == "Task 0"
        assert tasks[2]["id"] == "2"

        # Get next 3 tasks
        mock_todoist_api.get_tasks.return_value = iter([mock_tasks])
        tasks = todoist_service.get_tasks(limit=3, offset=3)
        assert len(tasks) == 3
        assert tasks[0]["id"] == "3"
        assert tasks[0]["content"] == "Task 3"
        assert tasks[2]["id"] == "5"

        # Get tasks with offset only
        mock_todoist_api.get_tasks.return_value = iter([mock_tasks])
        tasks = todoist_service.get_tasks(offset=7)
        assert len(tasks) == 3
        assert tasks[0]["id"] == "7"
        assert tasks[2]["id"] == "9"

    def test_get_task(self, todoist_service, mock_todoist_api):
        """Test getting a specific task"""
        mock_todoist_api.get_task.return_value = MockTodoistTask(id="123", content="Specific Task")
        task = todoist_service.get_task("123")
        assert task["id"] == "123"
        assert task["content"] == "Specific Task"
        mock_todoist_api.get_task.assert_called_once_with("123")

    def test_create_task_basic(self, todoist_service, mock_todoist_api):
        """Test creating a basic task"""
        task = todoist_service.create_task(content="New Task")
        assert task["content"] == "New Task"
        mock_todoist_api.add_task.assert_called_once()

    def test_create_task_with_validation(self, todoist_service, mock_todoist_api):
        """Test creating a task with all validations"""
        mock_todoist_api.get_project.return_value = MockTodoistProject()

        task = todoist_service.create_task(
            content="Complex Task",
            priority=3,
            project_id="proj123",
            labels=["urgent"],
            due_date="2024-12-31",
            duration=30,
            duration_unit="minute",
        )

        assert task["content"] == "New Task"
        call_args = mock_todoist_api.add_task.call_args
        assert call_args.kwargs["priority"] == 3
        # due_date is now converted to a date object

        assert call_args.kwargs["due_date"] == date(2024, 12, 31)

    def test_create_task_for_mcp_type_conversion(self, todoist_service, mock_todoist_api):
        """Test MCP wrapper handles string type conversion"""
        todoist_service.create_task_for_mcp(
            content="MCP Task",
            priority="4",  # String instead of int
            duration="60",  # String instead of int
            order="5",  # String instead of int
        )

        call_args = mock_todoist_api.add_task.call_args
        assert call_args.kwargs["priority"] == 4  # Converted to int
        assert call_args.kwargs["duration"] == 60  # Converted to int
        assert call_args.kwargs["order"] == 5  # Converted to int

    def test_update_task(self, todoist_service, mock_todoist_api):
        """Test updating a task"""
        task = todoist_service.update_task(task_id="123", content="Updated Content", priority=2)

        assert task["content"] == "Updated Task"
        mock_todoist_api.update_task.assert_called_once()
        call_args = mock_todoist_api.update_task.call_args
        assert call_args.kwargs["task_id"] == "123"
        assert call_args.kwargs["priority"] == 2

    def test_close_task(self, todoist_service, mock_todoist_api):
        """Test completing a task"""
        result = todoist_service.close_task("123")
        assert result is True
        mock_todoist_api.complete_task.assert_called_once_with(task_id="123")

    def test_reopen_task(self, todoist_service, mock_todoist_api):
        """Test reopening a task"""
        result = todoist_service.reopen_task("123")
        assert result is True
        mock_todoist_api.uncomplete_task.assert_called_once_with(task_id="123")

    def test_delete_task(self, todoist_service, mock_todoist_api):
        """Test deleting a task"""
        result = todoist_service.delete_task("123")
        assert result is True
        mock_todoist_api.delete_task.assert_called_once_with("123")

    # ========== PROJECT OPERATION TESTS ==========

    def test_get_projects(self, todoist_service, mock_todoist_api):
        """Test getting all projects"""
        projects = todoist_service.get_projects()
        assert len(projects) == 2
        assert projects[0]["name"] == "Work"
        assert projects[1]["is_inbox_project"] is True

    def test_get_project(self, todoist_service, mock_todoist_api):
        """Test getting a specific project"""
        project = todoist_service.get_project("1")
        assert project["name"] == "Work"
        mock_todoist_api.get_project.assert_called_once_with("1")

    def test_create_project(self, todoist_service, mock_todoist_api):
        """Test creating a project"""
        mock_todoist_api.add_project.return_value = MockTodoistProject(
            id="new_proj", name="New Project"
        )

        project = todoist_service.create_project(name="New Project", color="blue", is_favorite=True)

        assert project["name"] == "New Project"
        mock_todoist_api.add_project.assert_called_once()

    def test_update_project(self, todoist_service, mock_todoist_api):
        """Test updating a project"""
        mock_todoist_api.update_project.return_value = MockTodoistProject(
            id="1", name="Updated Project"
        )

        project = todoist_service.update_project(project_id="1", name="Updated Project")

        assert project["name"] == "Updated Project"
        mock_todoist_api.update_project.assert_called_once()

    def test_delete_project(self, todoist_service, mock_todoist_api):
        """Test deleting a project"""
        # The Todoist API returns True for successful deletion
        mock_todoist_api.delete_project.return_value = True
        result = todoist_service.delete_project("1")
        assert result is True
        mock_todoist_api.delete_project.assert_called_once_with("1")

    # ========== LABEL OPERATION TESTS ==========

    def test_get_labels(self, todoist_service, mock_todoist_api):
        """Test getting all labels"""
        labels = todoist_service.get_labels()
        assert len(labels) == 2
        assert labels[0]["name"] == "urgent"
        assert labels[1]["name"] == "work"

    def test_create_label(self, todoist_service, mock_todoist_api):
        """Test creating a label"""
        mock_todoist_api.add_label.return_value = MockTodoistLabel(id="new_label", name="important")

        label = todoist_service.create_label(name="important", color="red")

        assert label["name"] == "important"
        mock_todoist_api.add_label.assert_called_once()

    # ========== RESOURCE METHOD TESTS ==========

    def test_get_today_tasks_resource(self, todoist_service, mock_todoist_api, test_dates):
        """Test getting today's tasks"""
        today_task = MockTodoistTask(
            id="1", content="Today Task", due=MockTodoistDue(date=test_dates["today"])
        )
        mock_todoist_api.get_tasks.return_value = iter(
            [
                [
                    today_task,
                    MockTodoistTask(
                        id="2",
                        content="Tomorrow Task",
                        due=MockTodoistDue(date=test_dates["tomorrow"]),
                    ),
                    MockTodoistTask(id="3", content="No Due Date"),
                ]
            ]
        )
        # Mock filter_tasks to return only today's task
        mock_todoist_api.filter_tasks.return_value = iter([[today_task]])

        result = todoist_service.get_today_tasks_resource()
        assert result["tasks_count"] == 1
        assert result["tasks"][0]["content"] == "Today Task"
        assert "timezone" in result
        assert "date" in result

    def test_get_overdue_tasks_resource(self, todoist_service, mock_todoist_api, test_dates):
        """Test getting overdue tasks"""
        overdue_task = MockTodoistTask(
            id="1",
            content="Overdue Task",
            due=MockTodoistDue(date=test_dates["yesterday"]),
        )
        mock_todoist_api.get_tasks.return_value = iter(
            [
                [
                    overdue_task,
                    MockTodoistTask(
                        id="2",
                        content="Today Task",
                        due=MockTodoistDue(date=test_dates["today"]),
                    ),
                ]
            ]
        )
        # Mock filter_tasks to return only overdue task
        mock_todoist_api.filter_tasks.return_value = iter([[overdue_task]])

        result = todoist_service.get_overdue_tasks_resource()
        assert result["tasks_count"] == 1
        assert result["tasks"][0]["content"] == "Overdue Task"
        assert "timezone" in result
        assert "date" in result

    def test_get_priorities_resource(self, todoist_service):
        """Test getting priority information"""
        priorities = todoist_service.get_priorities_resource()
        assert "priorities" in priorities
        assert len(priorities["priorities"]) == 4
        assert priorities["default"] == 1

    def test_get_colors_resource(self, todoist_service):
        """Test getting color information"""
        colors = todoist_service.get_colors_resource()
        assert "colors" in colors
        assert len(colors["colors"]) == 20
        assert colors["colors"][0]["name"] == "berry_red"

    def test_get_common_filters_resource(self, todoist_service):
        """Test getting common filter strings"""
        filters = todoist_service.get_common_filters_resource()
        assert "filters" in filters
        assert len(filters["filters"]) > 0
        assert any(f["filter"] == "today" for f in filters["filters"])

    def test_get_task_stats_resource(self, todoist_service, mock_todoist_api, test_dates):
        """Test getting task statistics"""
        mock_todoist_api.get_tasks.return_value = iter(
            [
                [
                    MockTodoistTask(id="1", priority=4),
                    MockTodoistTask(id="2", priority=3),
                    MockTodoistTask(id="3", priority=1),
                    MockTodoistTask(id="4", due=MockTodoistDue(date=test_dates["yesterday"])),
                    MockTodoistTask(id="5", due=MockTodoistDue(date=test_dates["today"])),
                ]
            ]
        )

        stats = todoist_service.get_task_stats_resource()
        assert stats["total_active"] == 5
        assert stats["by_priority"]["urgent"] == 1
        assert stats["by_priority"]["high"] == 1
        assert stats["by_due"]["overdue"] == 1
        assert stats["by_due"]["today"] == 1

    # ========== ERROR HANDLING TESTS ==========

    def test_create_task_auth_error(self, todoist_service, mock_todoist_api):
        """Test authentication error handling"""
        mock_todoist_api.add_task.side_effect = Exception("401 Unauthorized")

        with pytest.raises(ValueError, match="Authentication failed"):
            todoist_service.create_task(content="Test")

    def test_create_task_not_found_error(self, todoist_service, mock_todoist_api):
        """Test resource not found error handling"""
        mock_todoist_api.add_task.side_effect = Exception("404 Not Found")

        with pytest.raises(ValueError, match="Resource not found"):
            todoist_service.create_task(content="Test")

    def test_update_task_not_found(self, todoist_service, mock_todoist_api):
        """Test updating non-existent task"""
        mock_todoist_api.update_task.side_effect = Exception("404 Not Found")

        with pytest.raises(ValueError, match=r"Task with ID .* not found"):
            todoist_service.update_task(task_id="nonexistent", content="Test")

    # ========== MCP WRAPPER TESTS ==========

    def test_close_task_for_mcp(self, todoist_service, mock_todoist_api):
        """Test MCP wrapper for closing task"""
        result = todoist_service.close_task_for_mcp("123")
        assert result["success"] is True
        assert "completed" in result["message"]
        mock_todoist_api.complete_task.assert_called_once_with(task_id="123")

    def test_reopen_task_for_mcp(self, todoist_service, mock_todoist_api):
        """Test MCP wrapper for reopening task"""
        result = todoist_service.reopen_task_for_mcp("123")
        assert result["success"] is True
        assert "reopened" in result["message"]
        mock_todoist_api.uncomplete_task.assert_called_once_with(task_id="123")

    def test_delete_task_for_mcp(self, todoist_service, mock_todoist_api):
        """Test MCP wrapper for deleting task"""
        result = todoist_service.delete_task_for_mcp("123")
        assert result["success"] is True
        assert "deleted" in result["message"]
        mock_todoist_api.delete_task.assert_called_once_with("123")

    def test_get_projects_for_mcp(self, todoist_service):
        """Test MCP wrapper for getting projects"""
        result = todoist_service.get_projects_for_mcp()
        assert "projects" in result
        assert result["count"] == 2

    def test_get_labels_for_mcp(self, todoist_service):
        """Test MCP wrapper for getting labels"""
        result = todoist_service.get_labels_for_mcp()
        assert "labels" in result
        assert result["count"] == 2

    # ========== NEW TASK OPERATION TESTS ==========

    def test_quick_add_task(self, todoist_service, mock_todoist_api):
        """Test quick add task with natural language"""
        task = todoist_service.quick_add_task("Buy milk tomorrow p1 #Shopping")
        assert task["content"] == "Quick Task"
        mock_todoist_api.add_task_quick.assert_called_once_with(
            text="Buy milk tomorrow p1 #Shopping"
        )

    def test_move_task_to_project(self, todoist_service, mock_todoist_api):
        """Test moving task to different project"""
        mock_todoist_api.get_project.return_value = MockTodoistProject(id="new_proj")
        mock_todoist_api.move_task.return_value = True
        mock_todoist_api.get_task.return_value = MockTodoistTask(id="123", project_id="new_proj")

        task = todoist_service.move_task(task_id="123", project_id="new_proj")

        assert task["project_id"] == "new_proj"
        mock_todoist_api.move_task.assert_called_once_with(
            task_id="123",
            project_id="new_proj",
            section_id=None,
            parent_id=None,
        )
        mock_todoist_api.get_task.assert_called_with("123")

    def test_move_task_to_section(self, todoist_service, mock_todoist_api):
        """Test moving task to different section"""
        from tests.conftest import MockTodoistSection

        mock_todoist_api.get_section.return_value = MockTodoistSection(id="sec123")
        mock_todoist_api.move_task.return_value = True
        mock_todoist_api.get_task.return_value = MockTodoistTask(id="123", section_id="sec123")

        todoist_service.move_task(task_id="123", section_id="sec123")

        mock_todoist_api.move_task.assert_called_once_with(
            task_id="123",
            project_id=None,
            section_id="sec123",
            parent_id=None,
        )

    def test_move_task_to_parent(self, todoist_service, mock_todoist_api):
        """Test making task a subtask"""
        mock_todoist_api.move_task.return_value = True
        mock_todoist_api.get_task.return_value = MockTodoistTask(id="123", parent_id="parent456")

        todoist_service.move_task(task_id="123", parent_id="parent456")

        mock_todoist_api.move_task.assert_called_once_with(
            task_id="123",
            project_id=None,
            section_id=None,
            parent_id="parent456",
        )

    def test_move_task_no_target_raises_error(self, todoist_service):
        """Test move_task with no target raises error"""
        with pytest.raises(ValueError, match="Exactly one of"):
            todoist_service.move_task(task_id="123")

    def test_move_task_multiple_targets_raises_error(self, todoist_service):
        """Test move_task with multiple targets raises error"""
        with pytest.raises(ValueError, match="Exactly one of"):
            todoist_service.move_task(task_id="123", project_id="proj1", section_id="sec1")

    def test_get_completed_tasks(self, todoist_service, mock_todoist_api):
        """Test getting completed tasks"""
        result = todoist_service.get_completed_tasks()

        assert "items" in result
        assert len(result["items"]) == 1
        assert result["items"][0]["content"] == "Done Task"
        assert result["has_more"] is False

    def test_get_completed_tasks_with_filters(self, todoist_service, mock_todoist_api):
        """Test getting completed tasks with filters"""
        todoist_service.get_completed_tasks(project_id="proj123", limit=10)

        mock_todoist_api.get_completed_tasks_by_completion_date.assert_called_once()
        call_kwargs = mock_todoist_api.get_completed_tasks_by_completion_date.call_args.kwargs
        assert call_kwargs["project_id"] == "proj123"
        assert call_kwargs["limit"] == 10

    def test_get_completed_tasks_by_due_date(self, todoist_service, mock_todoist_api):
        """Test getting completed tasks by due date"""
        result = todoist_service.get_completed_tasks_by_due_date(due_date="2024-12-15")

        assert "items" in result
        assert len(result["items"]) == 1
        mock_todoist_api.get_completed_tasks_by_due_date.assert_called_once()

    def test_move_task_for_mcp(self, todoist_service, mock_todoist_api):
        """Test MCP wrapper for moving task"""
        mock_todoist_api.get_project.return_value = MockTodoistProject(id="new_proj")
        mock_todoist_api.move_task.return_value = True
        mock_todoist_api.get_task.return_value = MockTodoistTask(id="123", project_id="new_proj")

        result = todoist_service.move_task_for_mcp(task_id="123", project_id="new_proj")

        assert result["success"] is True
        assert "task" in result

    def test_move_task_for_mcp_error(self, todoist_service, mock_todoist_api):
        """Test MCP wrapper for moving task with error"""
        result = todoist_service.move_task_for_mcp(task_id="123")  # No target

        assert "error" in result
        assert "Exactly one of" in result["error"]

    # ========== PROJECT OPERATION TESTS ==========

    def test_archive_project(self, todoist_service, mock_todoist_api):
        """Test archiving a project"""
        result = todoist_service.archive_project("1")
        assert result is True
        mock_todoist_api.archive_project.assert_called_once_with("1")

    def test_unarchive_project(self, todoist_service, mock_todoist_api):
        """Test unarchiving a project"""
        result = todoist_service.unarchive_project("1")
        assert result is True
        mock_todoist_api.unarchive_project.assert_called_once_with("1")

    def test_get_collaborators(self, todoist_service, mock_todoist_api):
        """Test getting project collaborators"""
        collaborators = todoist_service.get_collaborators("proj123")

        assert len(collaborators) == 2
        assert collaborators[0]["name"] == "Alice"
        assert collaborators[1]["email"] == "bob@example.com"

    def test_delete_project_for_mcp(self, todoist_service, mock_todoist_api):
        """Test MCP wrapper for deleting project"""
        result = todoist_service.delete_project_for_mcp("1")

        assert result["success"] is True
        assert "deleted" in result["message"]

    def test_archive_project_for_mcp(self, todoist_service, mock_todoist_api):
        """Test MCP wrapper for archiving project"""
        result = todoist_service.archive_project_for_mcp("1")

        assert result["success"] is True
        assert "archived" in result["message"]

    def test_unarchive_project_for_mcp(self, todoist_service, mock_todoist_api):
        """Test MCP wrapper for unarchiving project"""
        result = todoist_service.unarchive_project_for_mcp("1")

        assert result["success"] is True
        assert "unarchived" in result["message"]

    # ========== SECTION OPERATION TESTS ==========

    def test_get_sections(self, todoist_service, mock_todoist_api):
        """Test getting sections"""
        sections = todoist_service.get_sections()

        assert len(sections) == 2
        assert sections[0]["name"] == "To Do"
        assert sections[1]["name"] == "In Progress"

    def test_get_sections_by_project(self, todoist_service, mock_todoist_api):
        """Test getting sections filtered by project"""
        todoist_service.get_sections(project_id="proj123")

        mock_todoist_api.get_sections.assert_called_once_with(project_id="proj123")

    def test_create_section(self, todoist_service, mock_todoist_api):
        """Test creating a section"""
        section = todoist_service.create_section(name="New Section", project_id="proj123")

        assert section["name"] == "New Section"
        mock_todoist_api.add_section.assert_called_once()

    def test_update_section(self, todoist_service, mock_todoist_api):
        """Test updating a section"""
        section = todoist_service.update_section(section_id="1", name="Updated Section")

        assert section["name"] == "Updated Section"
        mock_todoist_api.update_section.assert_called_once_with(
            section_id="1", name="Updated Section"
        )

    def test_delete_section(self, todoist_service, mock_todoist_api):
        """Test deleting a section"""
        result = todoist_service.delete_section("1")
        assert result is True
        mock_todoist_api.delete_section.assert_called_once_with("1")

    def test_get_sections_for_mcp(self, todoist_service, mock_todoist_api):
        """Test MCP wrapper for getting sections"""
        result = todoist_service.get_sections_for_mcp()

        assert "sections" in result
        assert result["count"] == 2

    def test_create_section_for_mcp(self, todoist_service, mock_todoist_api):
        """Test MCP wrapper for creating section"""
        result = todoist_service.create_section_for_mcp(name="New Section", project_id="proj123")

        assert result["success"] is True
        assert "section" in result

    def test_update_section_for_mcp(self, todoist_service, mock_todoist_api):
        """Test MCP wrapper for updating section"""
        result = todoist_service.update_section_for_mcp(section_id="1", name="Updated")

        assert result["success"] is True
        assert "section" in result

    def test_delete_section_for_mcp(self, todoist_service, mock_todoist_api):
        """Test MCP wrapper for deleting section"""
        result = todoist_service.delete_section_for_mcp("1")

        assert result["success"] is True
        assert "deleted" in result["message"]

    # ========== LABEL OPERATION TESTS ==========

    def test_update_label(self, todoist_service, mock_todoist_api):
        """Test updating a label"""
        label = todoist_service.update_label(label_id="1", name="updated-label")

        assert label["name"] == "updated-label"
        mock_todoist_api.update_label.assert_called_once()

    def test_delete_label(self, todoist_service, mock_todoist_api):
        """Test deleting a label"""
        result = todoist_service.delete_label("1")
        assert result is True
        mock_todoist_api.delete_label.assert_called_once_with("1")

    def test_get_shared_labels(self, todoist_service, mock_todoist_api):
        """Test getting shared labels"""
        labels = todoist_service.get_shared_labels()

        assert len(labels) == 2
        assert "shared1" in labels
        assert "shared2" in labels

    def test_rename_shared_label(self, todoist_service, mock_todoist_api):
        """Test renaming a shared label"""
        result = todoist_service.rename_shared_label(old_name="old", new_name="new")
        assert result is True
        mock_todoist_api.rename_shared_label.assert_called_once_with(name="old", new_name="new")

    def test_remove_shared_label(self, todoist_service, mock_todoist_api):
        """Test removing a shared label"""
        result = todoist_service.remove_shared_label(name="shared1")
        assert result is True
        mock_todoist_api.remove_shared_label.assert_called_once_with(name="shared1")

    def test_update_label_for_mcp(self, todoist_service, mock_todoist_api):
        """Test MCP wrapper for updating label"""
        result = todoist_service.update_label_for_mcp(label_id="1", name="updated")

        assert result["success"] is True
        assert "label" in result

    def test_delete_label_for_mcp(self, todoist_service, mock_todoist_api):
        """Test MCP wrapper for deleting label"""
        result = todoist_service.delete_label_for_mcp("1")

        assert result["success"] is True
        assert "deleted" in result["message"]

    def test_get_shared_labels_for_mcp(self, todoist_service, mock_todoist_api):
        """Test MCP wrapper for getting shared labels"""
        result = todoist_service.get_shared_labels_for_mcp()

        assert "shared_labels" in result
        assert result["count"] == 2

    def test_rename_shared_label_for_mcp(self, todoist_service, mock_todoist_api):
        """Test MCP wrapper for renaming shared label"""
        result = todoist_service.rename_shared_label_for_mcp(old_name="old", new_name="new")

        assert result["success"] is True
        assert "renamed" in result["message"]

    def test_remove_shared_label_for_mcp(self, todoist_service, mock_todoist_api):
        """Test MCP wrapper for removing shared label"""
        result = todoist_service.remove_shared_label_for_mcp(name="shared1")

        assert result["success"] is True
        assert "removed" in result["message"]

    # ========== COMMENT OPERATION TESTS ==========

    def test_get_comments(self, todoist_service, mock_todoist_api):
        """Test getting comments"""
        comments = todoist_service.get_comments(task_id="task123")

        assert len(comments) == 2
        assert comments[0]["content"] == "Comment 1"

    def test_get_comment(self, todoist_service, mock_todoist_api):
        """Test getting a single comment"""
        comment = todoist_service.get_comment("1")

        assert comment["content"] == "Single Comment"
        mock_todoist_api.get_comment.assert_called_once_with("1")

    def test_create_comment(self, todoist_service, mock_todoist_api):
        """Test creating a comment"""
        comment = todoist_service.create_comment(content="New Comment", task_id="task123")

        assert comment["content"] == "New Comment"
        mock_todoist_api.add_comment.assert_called_once()

    def test_update_comment(self, todoist_service, mock_todoist_api):
        """Test updating a comment"""
        comment = todoist_service.update_comment(comment_id="1", content="Updated Comment")

        assert comment["content"] == "Updated Comment"
        mock_todoist_api.update_comment.assert_called_once_with(
            comment_id="1", content="Updated Comment"
        )

    def test_delete_comment(self, todoist_service, mock_todoist_api):
        """Test deleting a comment"""
        result = todoist_service.delete_comment("1")
        assert result is True
        mock_todoist_api.delete_comment.assert_called_once_with("1")

    def test_get_comments_for_mcp(self, todoist_service, mock_todoist_api):
        """Test MCP wrapper for getting comments"""
        result = todoist_service.get_comments_for_mcp(task_id="task123")

        assert "comments" in result
        assert result["count"] == 2

    def test_create_comment_for_mcp(self, todoist_service, mock_todoist_api):
        """Test MCP wrapper for creating comment"""
        result = todoist_service.create_comment_for_mcp(content="New Comment", task_id="task123")

        assert result["success"] is True
        assert "comment" in result

    def test_update_comment_for_mcp(self, todoist_service, mock_todoist_api):
        """Test MCP wrapper for updating comment"""
        result = todoist_service.update_comment_for_mcp(comment_id="1", content="Updated")

        assert result["success"] is True
        assert "comment" in result

    def test_delete_comment_for_mcp(self, todoist_service, mock_todoist_api):
        """Test MCP wrapper for deleting comment"""
        result = todoist_service.delete_comment_for_mcp("1")

        assert result["success"] is True
        assert "deleted" in result["message"]

    # ========== ERROR HANDLING TESTS ==========

    def test_archive_project_error(self, todoist_service, mock_todoist_api):
        """Test archive project error handling"""
        mock_todoist_api.archive_project.side_effect = Exception("Archive failed")

        with pytest.raises(Exception, match="Archive failed"):
            todoist_service.archive_project("1")

    def test_get_sections_for_mcp_error(self, todoist_service, mock_todoist_api):
        """Test MCP wrapper error handling for sections"""
        mock_todoist_api.get_sections.side_effect = Exception("API Error")

        result = todoist_service.get_sections_for_mcp()

        assert "error" in result

    def test_create_comment_for_mcp_error(self, todoist_service, mock_todoist_api):
        """Test MCP wrapper error handling for comments"""
        mock_todoist_api.add_comment.side_effect = Exception("Comment failed")

        result = todoist_service.create_comment_for_mcp(content="Test", task_id="task123")

        assert "error" in result

    # ========== ADDITIONAL COVERAGE TESTS ==========

    def test_quick_add_task_error(self, todoist_service, mock_todoist_api):
        """Test quick add task error handling"""
        mock_todoist_api.add_task_quick.side_effect = Exception("Quick add failed")

        with pytest.raises(Exception, match="Quick add failed"):
            todoist_service.quick_add_task("Test task")

    def test_get_completed_tasks_error(self, todoist_service, mock_todoist_api):
        """Test get completed tasks error handling"""
        mock_todoist_api.get_completed_tasks_by_completion_date.side_effect = Exception("API Error")

        with pytest.raises(Exception, match="API Error"):
            todoist_service.get_completed_tasks()

    def test_move_task_api_error(self, todoist_service, mock_todoist_api):
        """Test move task with API error"""
        mock_todoist_api.get_project.return_value = MockTodoistProject(id="new_proj")
        mock_todoist_api.move_task.side_effect = Exception("404 not found")

        with pytest.raises(ValueError, match="not found"):
            todoist_service.move_task(task_id="123", project_id="new_proj")

    def test_unarchive_project_error(self, todoist_service, mock_todoist_api):
        """Test unarchive project error handling"""
        mock_todoist_api.unarchive_project.side_effect = Exception("Unarchive failed")

        with pytest.raises(Exception, match="Unarchive failed"):
            todoist_service.unarchive_project("1")

    def test_get_collaborators_error(self, todoist_service, mock_todoist_api):
        """Test get collaborators error handling"""
        mock_todoist_api.get_collaborators.side_effect = Exception("Not found")

        with pytest.raises(Exception, match="Not found"):
            todoist_service.get_collaborators("proj123")

    def test_create_section_error(self, todoist_service, mock_todoist_api):
        """Test create section error handling"""
        mock_todoist_api.add_section.side_effect = Exception("Section failed")

        with pytest.raises(Exception, match="Section failed"):
            todoist_service.create_section(name="Test", project_id="proj123")

    def test_update_section_error(self, todoist_service, mock_todoist_api):
        """Test update section error handling"""
        mock_todoist_api.update_section.side_effect = Exception("Update failed")

        with pytest.raises(Exception, match="Update failed"):
            todoist_service.update_section(section_id="1", name="Test")

    def test_delete_section_error(self, todoist_service, mock_todoist_api):
        """Test delete section error handling"""
        mock_todoist_api.delete_section.side_effect = Exception("Delete failed")

        with pytest.raises(Exception, match="Delete failed"):
            todoist_service.delete_section("1")

    def test_update_label_error(self, todoist_service, mock_todoist_api):
        """Test update label error handling"""
        mock_todoist_api.update_label.side_effect = Exception("Update failed")

        with pytest.raises(Exception, match="Update failed"):
            todoist_service.update_label(label_id="1", name="test")

    def test_delete_label_error(self, todoist_service, mock_todoist_api):
        """Test delete label error handling"""
        mock_todoist_api.delete_label.side_effect = Exception("Delete failed")

        with pytest.raises(Exception, match="Delete failed"):
            todoist_service.delete_label("1")

    def test_get_shared_labels_error(self, todoist_service, mock_todoist_api):
        """Test get shared labels error handling"""
        mock_todoist_api.get_shared_labels.side_effect = Exception("API Error")

        with pytest.raises(Exception, match="API Error"):
            todoist_service.get_shared_labels()

    def test_rename_shared_label_error(self, todoist_service, mock_todoist_api):
        """Test rename shared label error handling"""
        mock_todoist_api.rename_shared_label.side_effect = Exception("Rename failed")

        with pytest.raises(Exception, match="Rename failed"):
            todoist_service.rename_shared_label(old_name="old", new_name="new")

    def test_remove_shared_label_error(self, todoist_service, mock_todoist_api):
        """Test remove shared label error handling"""
        mock_todoist_api.remove_shared_label.side_effect = Exception("Remove failed")

        with pytest.raises(Exception, match="Remove failed"):
            todoist_service.remove_shared_label(name="test")

    def test_get_comments_error(self, todoist_service, mock_todoist_api):
        """Test get comments error handling"""
        mock_todoist_api.get_comments.side_effect = Exception("Comments failed")

        with pytest.raises(Exception, match="Comments failed"):
            todoist_service.get_comments(task_id="123")

    def test_get_comment_error(self, todoist_service, mock_todoist_api):
        """Test get single comment error handling"""
        mock_todoist_api.get_comment.side_effect = Exception("Not found")

        with pytest.raises(Exception, match="Not found"):
            todoist_service.get_comment("1")

    def test_create_comment_error(self, todoist_service, mock_todoist_api):
        """Test create comment error handling"""
        mock_todoist_api.add_comment.side_effect = Exception("Create failed")

        with pytest.raises(Exception, match="Create failed"):
            todoist_service.create_comment(content="Test", task_id="123")

    def test_update_comment_error(self, todoist_service, mock_todoist_api):
        """Test update comment error handling"""
        mock_todoist_api.update_comment.side_effect = Exception("Update failed")

        with pytest.raises(Exception, match="Update failed"):
            todoist_service.update_comment(comment_id="1", content="Test")

    def test_delete_comment_error(self, todoist_service, mock_todoist_api):
        """Test delete comment error handling"""
        mock_todoist_api.delete_comment.side_effect = Exception("Delete failed")

        with pytest.raises(Exception, match="Delete failed"):
            todoist_service.delete_comment("1")

    # ========== MCP WRAPPER ERROR TESTS ==========

    def test_delete_project_for_mcp_error(self, todoist_service, mock_todoist_api):
        """Test MCP wrapper for deleting project with error"""
        mock_todoist_api.delete_project.side_effect = Exception("Delete failed")

        result = todoist_service.delete_project_for_mcp("1")

        assert "error" in result

    def test_archive_project_for_mcp_error(self, todoist_service, mock_todoist_api):
        """Test MCP wrapper for archiving project with error"""
        mock_todoist_api.archive_project.side_effect = Exception("Archive failed")

        result = todoist_service.archive_project_for_mcp("1")

        assert "error" in result

    def test_unarchive_project_for_mcp_error(self, todoist_service, mock_todoist_api):
        """Test MCP wrapper for unarchiving project with error"""
        mock_todoist_api.unarchive_project.side_effect = Exception("Unarchive failed")

        result = todoist_service.unarchive_project_for_mcp("1")

        assert "error" in result

    def test_create_section_for_mcp_error(self, todoist_service, mock_todoist_api):
        """Test MCP wrapper for creating section with error"""
        mock_todoist_api.add_section.side_effect = Exception("Create failed")

        result = todoist_service.create_section_for_mcp(name="Test", project_id="proj123")

        assert "error" in result

    def test_update_section_for_mcp_error(self, todoist_service, mock_todoist_api):
        """Test MCP wrapper for updating section with error"""
        mock_todoist_api.update_section.side_effect = Exception("Update failed")

        result = todoist_service.update_section_for_mcp(section_id="1", name="Test")

        assert "error" in result

    def test_delete_section_for_mcp_error(self, todoist_service, mock_todoist_api):
        """Test MCP wrapper for deleting section with error"""
        mock_todoist_api.delete_section.side_effect = Exception("Delete failed")

        result = todoist_service.delete_section_for_mcp("1")

        assert "error" in result

    def test_update_label_for_mcp_error(self, todoist_service, mock_todoist_api):
        """Test MCP wrapper for updating label with error"""
        mock_todoist_api.update_label.side_effect = Exception("Update failed")

        result = todoist_service.update_label_for_mcp(label_id="1", name="test")

        assert "error" in result

    def test_delete_label_for_mcp_error(self, todoist_service, mock_todoist_api):
        """Test MCP wrapper for deleting label with error"""
        mock_todoist_api.delete_label.side_effect = Exception("Delete failed")

        result = todoist_service.delete_label_for_mcp("1")

        assert "error" in result

    def test_get_shared_labels_for_mcp_error(self, todoist_service, mock_todoist_api):
        """Test MCP wrapper for getting shared labels with error"""
        mock_todoist_api.get_shared_labels.side_effect = Exception("API Error")

        result = todoist_service.get_shared_labels_for_mcp()

        assert "error" in result

    def test_rename_shared_label_for_mcp_error(self, todoist_service, mock_todoist_api):
        """Test MCP wrapper for renaming shared label with error"""
        mock_todoist_api.rename_shared_label.side_effect = Exception("Rename failed")

        result = todoist_service.rename_shared_label_for_mcp(old_name="old", new_name="new")

        assert "error" in result

    def test_remove_shared_label_for_mcp_error(self, todoist_service, mock_todoist_api):
        """Test MCP wrapper for removing shared label with error"""
        mock_todoist_api.remove_shared_label.side_effect = Exception("Remove failed")

        result = todoist_service.remove_shared_label_for_mcp(name="test")

        assert "error" in result

    def test_get_comments_for_mcp_error(self, todoist_service, mock_todoist_api):
        """Test MCP wrapper for getting comments with error"""
        mock_todoist_api.get_comments.side_effect = Exception("API Error")

        result = todoist_service.get_comments_for_mcp(task_id="123")

        assert "error" in result

    def test_update_comment_for_mcp_error(self, todoist_service, mock_todoist_api):
        """Test MCP wrapper for updating comment with error"""
        mock_todoist_api.update_comment.side_effect = Exception("Update failed")

        result = todoist_service.update_comment_for_mcp(comment_id="1", content="Test")

        assert "error" in result

    def test_delete_comment_for_mcp_error(self, todoist_service, mock_todoist_api):
        """Test MCP wrapper for deleting comment with error"""
        mock_todoist_api.delete_comment.side_effect = Exception("Delete failed")

        result = todoist_service.delete_comment_for_mcp("1")

        assert "error" in result

    # ========== TASK TO DICT TESTS ==========

    def test_task_with_due_date(self, todoist_service, mock_todoist_api):
        """Test task with due date is properly converted"""
        task_with_due = MockTodoistTask(
            id="1",
            content="Task with due",
            due=MockTodoistDue(date="2024-12-31", string="Dec 31"),
        )
        mock_todoist_api.get_task.return_value = task_with_due

        task = todoist_service.get_task("1")

        assert task["due"] is not None
        assert task["due"]["date"] == "2024-12-31"

    def test_task_with_duration(self, todoist_service, mock_todoist_api):
        """Test task with duration is properly converted"""
        from tests.conftest import MockTodoistTask

        class MockDuration:
            def __init__(self):
                self.amount = 30
                self.unit = "minute"

        task_with_duration = MockTodoistTask(id="1", content="Task with duration")
        task_with_duration.duration = MockDuration()
        mock_todoist_api.get_task.return_value = task_with_duration

        task = todoist_service.get_task("1")

        assert task["duration"] is not None
        assert task["duration"]["amount"] == 30
        assert task["duration"]["unit"] == "minute"

    # ========== PROJECT/LABEL/SECTION TO DICT TESTS ==========

    def test_project_to_dict_with_parent(self, todoist_service, mock_todoist_api):
        """Test project with parent_id is properly converted"""
        mock_todoist_api.get_project.return_value = MockTodoistProject(
            id="sub1", name="Sub Project", parent_id="parent1"
        )

        project = todoist_service.get_project("sub1")

        assert project["parent_id"] == "parent1"

    def test_get_tasks_for_mcp(self, todoist_service, mock_todoist_api):
        """Test MCP wrapper for getting tasks"""
        # Reset the mock
        mock_todoist_api.get_tasks.return_value = iter(
            [[MockTodoistTask(id="1"), MockTodoistTask(id="2")]]
        )
        result = todoist_service.get_tasks_for_mcp()

        assert "tasks" in result
        assert result["count"] == 2

    def test_get_tasks_for_mcp_error(self, todoist_service, mock_todoist_api):
        """Test MCP wrapper for getting tasks with error"""
        mock_todoist_api.get_tasks.side_effect = Exception("API Error")

        result = todoist_service.get_tasks_for_mcp()

        assert "error" in result

    def test_close_task_for_mcp_error(self, todoist_service, mock_todoist_api):
        """Test MCP wrapper for closing task with error"""
        mock_todoist_api.complete_task.side_effect = Exception("Complete failed")

        result = todoist_service.close_task_for_mcp("123")

        assert "error" in result

    def test_reopen_task_for_mcp_error(self, todoist_service, mock_todoist_api):
        """Test MCP wrapper for reopening task with error"""
        mock_todoist_api.uncomplete_task.side_effect = Exception("Reopen failed")

        result = todoist_service.reopen_task_for_mcp("123")

        assert "error" in result

    def test_delete_task_for_mcp_error(self, todoist_service, mock_todoist_api):
        """Test MCP wrapper for deleting task with error"""
        mock_todoist_api.delete_task.side_effect = Exception("Delete failed")

        result = todoist_service.delete_task_for_mcp("123")

        assert "error" in result

    def test_get_projects_for_mcp_error(self, todoist_service, mock_todoist_api):
        """Test MCP wrapper for getting projects with error"""
        mock_todoist_api.get_projects.side_effect = Exception("API Error")

        result = todoist_service.get_projects_for_mcp()

        assert "error" in result

    def test_get_labels_for_mcp_error(self, todoist_service, mock_todoist_api):
        """Test MCP wrapper for getting labels with error"""
        mock_todoist_api.get_labels.side_effect = Exception("API Error")

        result = todoist_service.get_labels_for_mcp()

        assert "error" in result
