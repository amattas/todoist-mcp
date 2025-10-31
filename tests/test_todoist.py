"""Unit tests for Todoist service"""

import pytest
from unittest.mock import MagicMock, patch, call
from datetime import datetime, date, timezone, timedelta
from src.services.todoist import TodoistService
from tests.conftest import MockTodoistTask, MockTodoistProject, MockTodoistLabel, MockTodoistDue


class TestTodoistService:
    """Test suite for TodoistService"""
    
    # ========== INITIALIZATION TESTS ==========
    
    def test_init_with_token(self):
        """Test service initialization with API token"""
        with patch('src.services.todoist.TodoistAPI') as mock_api:
            service = TodoistService(api_token='test_token')
            assert service.api_token == 'test_token'
            mock_api.assert_called_once_with('test_token')
    
    def test_init_with_env_token(self):
        """Test service initialization with environment variable"""
        with patch.dict('os.environ', {'TODOIST_API_TOKEN': 'env_token'}):
            with patch('src.services.todoist.TodoistAPI') as mock_api:
                service = TodoistService()
                assert service.api_token == 'env_token'
                mock_api.assert_called_once_with('env_token')
    
    def test_init_without_token_raises_error(self):
        """Test that initialization without token raises ValueError"""
        with patch.dict('os.environ', {}, clear=True):
            with pytest.raises(ValueError, match="Todoist API token is required"):
                TodoistService()
    
    # ========== VALIDATION TESTS ==========
    
    @pytest.mark.parametrize("priority,expected", [
        ("1", 1),
        ("2", 2),
        ("3", 3),
        ("4", 4),
        (1, 1),
        (4, 4),
        (None, None)
    ])
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
        mock_todoist_api.get_project.return_value = MockTodoistProject(id='proj123')
        todoist_service._validate_project_id('proj123')  # Should not raise
        mock_todoist_api.get_project.assert_called_once_with('proj123')
    
    def test_validate_project_id_invalid(self, todoist_service, mock_todoist_api):
        """Test project ID validation with non-existent project"""
        mock_todoist_api.get_project.side_effect = Exception("Project not found")
        with pytest.raises(ValueError, match="Invalid project_id"):
            todoist_service._validate_project_id('invalid_id')
    
    def test_validate_section_id_valid(self, todoist_service, mock_todoist_api):
        """Test section ID validation with existing section"""
        from tests.conftest import MockTodoistSection
        mock_todoist_api.get_section.return_value = MockTodoistSection(id='sec123')
        todoist_service._validate_section_id('sec123')  # Should not raise
        mock_todoist_api.get_section.assert_called_once_with('sec123')
    
    def test_validate_label_names_valid(self, todoist_service):
        """Test label validation with existing labels"""
        todoist_service._validate_label_names(['urgent', 'work'])  # Should not raise
    
    def test_validate_label_names_invalid(self, todoist_service):
        """Test label validation with non-existent labels"""
        with pytest.raises(ValueError, match="Invalid label"):
            todoist_service._validate_label_names(['nonexistent'])
    
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
            todoist_service._validate_color('invalid_color')
    
    @pytest.mark.parametrize("view_style", ["list", "board", None])
    def test_validate_view_style_valid(self, todoist_service, view_style):
        """Test view style validation with valid values"""
        todoist_service._validate_view_style(view_style)  # Should not raise
    
    def test_validate_view_style_invalid(self, todoist_service):
        """Test view style validation with invalid value"""
        with pytest.raises(ValueError, match="Invalid view_style"):
            todoist_service._validate_view_style('kanban')
    
    # ========== TASK OPERATION TESTS ==========
    
    def test_get_tasks(self, todoist_service, mock_todoist_api):
        """Test getting tasks"""
        tasks = todoist_service.get_tasks()
        assert len(tasks) == 2
        assert tasks[0]['content'] == 'Task 1'
        assert tasks[1]['priority'] == 4
    
    def test_get_tasks_with_filters(self, todoist_service, mock_todoist_api):
        """Test getting tasks with filters"""
        tasks = todoist_service.get_tasks(
            project_id='proj123',
            label='urgent'
        )
        mock_todoist_api.get_tasks.assert_called_once_with(
            project_id='proj123',
            section_id=None,
            label='urgent',
            ids=None
        )
    
    def test_get_tasks_with_pagination(self, todoist_service, mock_todoist_api):
        """Test getting tasks with pagination"""
        # Mock API returning 10 tasks
        mock_tasks = [
            MockTodoistTask(id=str(i), content=f'Task {i}', priority=1)
            for i in range(10)
        ]
        mock_todoist_api.get_tasks.return_value = iter([mock_tasks])
        
        # Get first 3 tasks
        tasks = todoist_service.get_tasks(limit=3, offset=0)
        assert len(tasks) == 3
        assert tasks[0]['id'] == '0'
        assert tasks[0]['content'] == 'Task 0'
        assert tasks[2]['id'] == '2'
        
        # Get next 3 tasks
        mock_todoist_api.get_tasks.return_value = iter([mock_tasks])
        tasks = todoist_service.get_tasks(limit=3, offset=3)
        assert len(tasks) == 3
        assert tasks[0]['id'] == '3'
        assert tasks[0]['content'] == 'Task 3'
        assert tasks[2]['id'] == '5'
        
        # Get tasks with offset only
        mock_todoist_api.get_tasks.return_value = iter([mock_tasks])
        tasks = todoist_service.get_tasks(offset=7)
        assert len(tasks) == 3
        assert tasks[0]['id'] == '7'
        assert tasks[2]['id'] == '9'
    
    def test_get_task(self, todoist_service, mock_todoist_api):
        """Test getting a specific task"""
        mock_todoist_api.get_task.return_value = MockTodoistTask(
            id='123',
            content='Specific Task'
        )
        task = todoist_service.get_task('123')
        assert task['id'] == '123'
        assert task['content'] == 'Specific Task'
        mock_todoist_api.get_task.assert_called_once_with('123')
    
    def test_create_task_basic(self, todoist_service, mock_todoist_api):
        """Test creating a basic task"""
        task = todoist_service.create_task(content='New Task')
        assert task['content'] == 'New Task'
        mock_todoist_api.add_task.assert_called_once()
    
    def test_create_task_with_validation(self, todoist_service, mock_todoist_api):
        """Test creating a task with all validations"""
        mock_todoist_api.get_project.return_value = MockTodoistProject()
        
        task = todoist_service.create_task(
            content='Complex Task',
            priority=3,
            project_id='proj123',
            labels=['urgent'],
            due_date='2024-12-31',
            duration=30,
            duration_unit='minute'
        )
        
        assert task['content'] == 'New Task'
        call_args = mock_todoist_api.add_task.call_args
        assert call_args.kwargs['priority'] == 3
        # due_date is now converted to a date object
        from datetime import date
        assert call_args.kwargs['due_date'] == date(2024, 12, 31)
    
    def test_create_task_for_mcp_type_conversion(self, todoist_service, mock_todoist_api):
        """Test MCP wrapper handles string type conversion"""
        task = todoist_service.create_task_for_mcp(
            content='MCP Task',
            priority='4',  # String instead of int
            duration='60',  # String instead of int
            order='5'  # String instead of int
        )
        
        call_args = mock_todoist_api.add_task.call_args
        assert call_args.kwargs['priority'] == 4  # Converted to int
        assert call_args.kwargs['duration'] == 60  # Converted to int
        assert call_args.kwargs['order'] == 5  # Converted to int
    
    def test_update_task(self, todoist_service, mock_todoist_api):
        """Test updating a task"""
        task = todoist_service.update_task(
            task_id='123',
            content='Updated Content',
            priority=2
        )
        
        assert task['content'] == 'Updated Task'
        mock_todoist_api.update_task.assert_called_once()
        call_args = mock_todoist_api.update_task.call_args
        assert call_args.kwargs['task_id'] == '123'
        assert call_args.kwargs['priority'] == 2
    
    def test_close_task(self, todoist_service, mock_todoist_api):
        """Test completing a task"""
        result = todoist_service.close_task('123')
        assert result is True
        mock_todoist_api.complete_task.assert_called_once_with(task_id='123')
    
    def test_reopen_task(self, todoist_service, mock_todoist_api):
        """Test reopening a task"""
        result = todoist_service.reopen_task('123')
        assert result is True
        mock_todoist_api.uncomplete_task.assert_called_once_with(task_id='123')
    
    def test_delete_task(self, todoist_service, mock_todoist_api):
        """Test deleting a task"""
        result = todoist_service.delete_task('123')
        assert result is True
        mock_todoist_api.delete_task.assert_called_once_with('123')
    
    # ========== PROJECT OPERATION TESTS ==========
    
    def test_get_projects(self, todoist_service, mock_todoist_api):
        """Test getting all projects"""
        projects = todoist_service.get_projects()
        assert len(projects) == 2
        assert projects[0]['name'] == 'Work'
        assert projects[1]['is_inbox_project'] is True
    
    def test_get_project(self, todoist_service, mock_todoist_api):
        """Test getting a specific project"""
        project = todoist_service.get_project('1')
        assert project['name'] == 'Work'
        mock_todoist_api.get_project.assert_called_once_with('1')
    
    def test_create_project(self, todoist_service, mock_todoist_api):
        """Test creating a project"""
        mock_todoist_api.add_project.return_value = MockTodoistProject(
            id='new_proj',
            name='New Project'
        )
        
        project = todoist_service.create_project(
            name='New Project',
            color='blue',
            is_favorite=True
        )
        
        assert project['name'] == 'New Project'
        mock_todoist_api.add_project.assert_called_once()
    
    def test_update_project(self, todoist_service, mock_todoist_api):
        """Test updating a project"""
        mock_todoist_api.update_project.return_value = MockTodoistProject(
            id='1',
            name='Updated Project'
        )
        
        project = todoist_service.update_project(
            project_id='1',
            name='Updated Project'
        )
        
        assert project['name'] == 'Updated Project'
        mock_todoist_api.update_project.assert_called_once()
    
    def test_delete_project(self, todoist_service, mock_todoist_api):
        """Test deleting a project"""
        # The Todoist API returns True for successful deletion
        mock_todoist_api.delete_project.return_value = True
        result = todoist_service.delete_project('1')
        assert result is True
        mock_todoist_api.delete_project.assert_called_once_with('1')
    
    # ========== LABEL OPERATION TESTS ==========
    
    def test_get_labels(self, todoist_service, mock_todoist_api):
        """Test getting all labels"""
        labels = todoist_service.get_labels()
        assert len(labels) == 2
        assert labels[0]['name'] == 'urgent'
        assert labels[1]['name'] == 'work'
    
    def test_create_label(self, todoist_service, mock_todoist_api):
        """Test creating a label"""
        mock_todoist_api.add_label.return_value = MockTodoistLabel(
            id='new_label',
            name='important'
        )
        
        label = todoist_service.create_label(
            name='important',
            color='red'
        )
        
        assert label['name'] == 'important'
        mock_todoist_api.add_label.assert_called_once()
    
    # ========== RESOURCE METHOD TESTS ==========
    
    def test_get_today_tasks_resource(self, todoist_service, mock_todoist_api, test_dates):
        """Test getting today's tasks"""
        today_task = MockTodoistTask(
            id='1',
            content='Today Task',
            due=MockTodoistDue(date=test_dates['today'])
        )
        mock_todoist_api.get_tasks.return_value = iter([[
            today_task,
            MockTodoistTask(
                id='2',
                content='Tomorrow Task',
                due=MockTodoistDue(date=test_dates['tomorrow'])
            ),
            MockTodoistTask(
                id='3',
                content='No Due Date'
            )
        ]])
        # Mock filter_tasks to return only today's task
        mock_todoist_api.filter_tasks.return_value = iter([[today_task]])
        
        result = todoist_service.get_today_tasks_resource()
        assert result['tasks_count'] == 1
        assert result['tasks'][0]['content'] == 'Today Task'
        assert 'timezone' in result
        assert 'date' in result
    
    def test_get_overdue_tasks_resource(self, todoist_service, mock_todoist_api, test_dates):
        """Test getting overdue tasks"""
        overdue_task = MockTodoistTask(
            id='1',
            content='Overdue Task',
            due=MockTodoistDue(date=test_dates['yesterday'])
        )
        mock_todoist_api.get_tasks.return_value = iter([[
            overdue_task,
            MockTodoistTask(
                id='2',
                content='Today Task',
                due=MockTodoistDue(date=test_dates['today'])
            )
        ]])
        # Mock filter_tasks to return only overdue task
        mock_todoist_api.filter_tasks.return_value = iter([[overdue_task]])
        
        result = todoist_service.get_overdue_tasks_resource()
        assert result['tasks_count'] == 1
        assert result['tasks'][0]['content'] == 'Overdue Task'
        assert 'timezone' in result
        assert 'date' in result
    
    def test_get_priorities_resource(self, todoist_service):
        """Test getting priority information"""
        priorities = todoist_service.get_priorities_resource()
        assert 'priorities' in priorities
        assert len(priorities['priorities']) == 4
        assert priorities['default'] == 1
    
    def test_get_colors_resource(self, todoist_service):
        """Test getting color information"""
        colors = todoist_service.get_colors_resource()
        assert 'colors' in colors
        assert len(colors['colors']) == 20
        assert colors['colors'][0]['name'] == 'berry_red'
    
    def test_get_common_filters_resource(self, todoist_service):
        """Test getting common filter strings"""
        filters = todoist_service.get_common_filters_resource()
        assert 'filters' in filters
        assert len(filters['filters']) > 0
        assert any(f['filter'] == 'today' for f in filters['filters'])
    
    def test_get_task_stats_resource(self, todoist_service, mock_todoist_api, test_dates):
        """Test getting task statistics"""
        mock_todoist_api.get_tasks.return_value = iter([[
            MockTodoistTask(id='1', priority=4),
            MockTodoistTask(id='2', priority=3),
            MockTodoistTask(id='3', priority=1),
            MockTodoistTask(
                id='4',
                due=MockTodoistDue(date=test_dates['yesterday'])
            ),
            MockTodoistTask(
                id='5',
                due=MockTodoistDue(date=test_dates['today'])
            )
        ]])
        
        stats = todoist_service.get_task_stats_resource()
        assert stats['total_active'] == 5
        assert stats['by_priority']['urgent'] == 1
        assert stats['by_priority']['high'] == 1
        assert stats['by_due']['overdue'] == 1
        assert stats['by_due']['today'] == 1
    
    # ========== ERROR HANDLING TESTS ==========
    
    def test_create_task_auth_error(self, todoist_service, mock_todoist_api):
        """Test authentication error handling"""
        mock_todoist_api.add_task.side_effect = Exception("401 Unauthorized")
        
        with pytest.raises(ValueError, match="Authentication failed"):
            todoist_service.create_task(content='Test')
    
    def test_create_task_not_found_error(self, todoist_service, mock_todoist_api):
        """Test resource not found error handling"""
        mock_todoist_api.add_task.side_effect = Exception("404 Not Found")
        
        with pytest.raises(ValueError, match="Resource not found"):
            todoist_service.create_task(content='Test')
    
    def test_update_task_not_found(self, todoist_service, mock_todoist_api):
        """Test updating non-existent task"""
        mock_todoist_api.update_task.side_effect = Exception("404 Not Found")
        
        with pytest.raises(ValueError, match="Task with ID .* not found"):
            todoist_service.update_task(task_id='nonexistent', content='Test')
    
    # ========== MCP WRAPPER TESTS ==========
    
    def test_close_task_for_mcp(self, todoist_service, mock_todoist_api):
        """Test MCP wrapper for closing task"""
        result = todoist_service.close_task_for_mcp('123')
        assert result['success'] is True
        assert 'completed' in result['message']
        mock_todoist_api.complete_task.assert_called_once_with(task_id='123')
    
    def test_reopen_task_for_mcp(self, todoist_service, mock_todoist_api):
        """Test MCP wrapper for reopening task"""
        result = todoist_service.reopen_task_for_mcp('123')
        assert result['success'] is True
        assert 'reopened' in result['message']
        mock_todoist_api.uncomplete_task.assert_called_once_with(task_id='123')
    
    def test_delete_task_for_mcp(self, todoist_service, mock_todoist_api):
        """Test MCP wrapper for deleting task"""
        result = todoist_service.delete_task_for_mcp('123')
        assert result['success'] is True
        assert 'deleted' in result['message']
        mock_todoist_api.delete_task.assert_called_once_with('123')
    
    def test_get_projects_for_mcp(self, todoist_service):
        """Test MCP wrapper for getting projects"""
        result = todoist_service.get_projects_for_mcp()
        assert 'projects' in result
        assert result['count'] == 2
    
    def test_get_labels_for_mcp(self, todoist_service):
        """Test MCP wrapper for getting labels"""
        result = todoist_service.get_labels_for_mcp()
        assert 'labels' in result
        assert result['count'] == 2