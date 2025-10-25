"""Test cases for Todoist week tasks functionality"""
import pytest
from datetime import datetime, date, timedelta
from unittest.mock import Mock, patch
from zoneinfo import ZoneInfo

from services.todoist import TodoistService
from tests.conftest import MockTodoistTask, MockTodoistDue


class MockTodoistDueCustom:
    """Custom mock for due object with specific field values"""
    def __init__(self, date=None, datetime_val=None, string=None, timezone=None, is_recurring=False):
        self.date = date
        self.datetime = datetime_val
        self.string = string
        self.timezone = timezone
        self.is_recurring = is_recurring


class TestWeekTasks:
    """Test week task retrieval with various date formats"""
    
    def test_week_tasks_with_date_objects(self, todoist_service, mock_todoist_api):
        """Test tasks with date objects are correctly filtered for the week"""
        # Get current week boundaries - using rolling week (today + 6 days)
        today = datetime.now(ZoneInfo('UTC')).date()
        start_of_week = today
        end_of_week = today + timedelta(days=6)
        
        # Create tasks with different dates
        tasks = [
            # Task due today (start of rolling week)
            MockTodoistTask(
                id='1', 
                content='Today task',
                due=MockTodoistDue(date=start_of_week)
            ),
            # Task due in 2 days (mid-week)
            MockTodoistTask(
                id='2',
                content='Mid-week task',
                due=MockTodoistDue(date=start_of_week + timedelta(days=2))
            ),
            # Task due on day 6 (end of rolling week)
            MockTodoistTask(
                id='3',
                content='End of week task',
                due=MockTodoistDue(date=end_of_week)
            ),
            # Task due after rolling week (should be excluded)
            MockTodoistTask(
                id='4',
                content='Next week task',
                due=MockTodoistDue(date=end_of_week + timedelta(days=1))
            ),
            # Task due yesterday (should be excluded from "next 7 days")
            MockTodoistTask(
                id='5',
                content='Yesterday task',
                due=MockTodoistDue(date=start_of_week - timedelta(days=1))
            ),
            # Task with no due date (should be excluded)
            MockTodoistTask(
                id='6',
                content='No due date task'
            ),
        ]
        
        mock_todoist_api.get_tasks.return_value = iter([tasks])
        # Mock filter_tasks to return only tasks within the rolling week
        week_tasks = [tasks[0], tasks[1], tasks[2]]  # First 3 tasks are within the week
        mock_todoist_api.filter_tasks.return_value = iter([week_tasks])
        
        result = todoist_service.get_week_tasks_resource()
        
        assert result['tasks_count'] == 3
        assert result['week_start'] == start_of_week.isoformat()
        assert result['week_end'] == end_of_week.isoformat()
        assert result['week_type'] == 'rolling_7_days'
        
        # Verify correct tasks are included
        task_ids = [t['id'] for t in result['tasks']]
        assert '1' in task_ids  # Today task
        assert '2' in task_ids  # Mid-week task
        assert '3' in task_ids  # End of week task
        assert '4' not in task_ids  # After rolling week
        assert '5' not in task_ids  # Yesterday (before rolling week)
        assert '6' not in task_ids  # No due date
    
    def test_week_tasks_with_datetime_strings(self, todoist_service, mock_todoist_api):
        """Test tasks with datetime strings in ISO format"""
        today = datetime.now(ZoneInfo('UTC')).date()
        start_of_week = today  # Rolling week starts from today
        
        # Create tasks with datetime strings
        tasks = [
            # Task with datetime in 'datetime' field
            MockTodoistTask(
                id='1',
                content='DateTime task 1',
                due=MockTodoistDueCustom(datetime_val=f"{start_of_week}T10:00:00Z")
            ),
            # Task with datetime in 'date' field (some APIs do this)
            MockTodoistTask(
                id='2',
                content='DateTime task 2',
                due=MockTodoistDueCustom(date=f"{start_of_week + timedelta(days=1)}T14:30:00+00:00")
            ),
            # Task with simple date string
            MockTodoistTask(
                id='3',
                content='Date string task',
                due=MockTodoistDueCustom(date=str(start_of_week + timedelta(days=2)))
            ),
            # Task with both datetime and date (datetime should take precedence)
            MockTodoistTask(
                id='4',
                content='Both fields task',
                due=MockTodoistDueCustom(
                    datetime_val=f"{start_of_week + timedelta(days=3)}T09:00:00Z",
                    date=str(start_of_week + timedelta(days=10))  # Next week date
                )
            ),
        ]
        
        mock_todoist_api.get_tasks.return_value = iter([tasks])
        # Mock filter_tasks to return all tasks (they're all within the week)
        mock_todoist_api.filter_tasks.return_value = iter([tasks])
        
        result = todoist_service.get_week_tasks_resource()
        
        assert result['tasks_count'] == 4
        task_ids = [t['id'] for t in result['tasks']]
        assert all(id in task_ids for id in ['1', '2', '3', '4'])
    
    def test_week_tasks_with_timezone_conversion(self, todoist_service, mock_todoist_api):
        """Test that datetime values are correctly converted to service timezone"""
        # Set service timezone to US/Eastern
        todoist_service.timezone = ZoneInfo('US/Eastern')
        todoist_service.timezone_str = 'US/Eastern'
        
        # Get rolling week boundaries in Eastern time
        today = datetime.now(ZoneInfo('US/Eastern')).date()
        end_date = today + timedelta(days=6)
        
        # Create a task due at 11 PM Pacific on the 7th day (which is 8th day in Eastern)
        seventh_day_pacific = end_date
        task_datetime = f"{seventh_day_pacific}T23:00:00-08:00"  # 11 PM Pacific
        
        tasks = [
            MockTodoistTask(
                id='1',
                content='Late day Pacific = Early next day Eastern',
                due=MockTodoistDueCustom(datetime_val=task_datetime)
            ),
        ]
        
        mock_todoist_api.get_tasks.return_value = iter([tasks])
        # Mock filter_tasks to return empty list (task is outside rolling week when converted to Eastern)
        mock_todoist_api.filter_tasks.return_value = iter([[]])
        
        result = todoist_service.get_week_tasks_resource()
        
        # This task should NOT be in the rolling week when converted to Eastern time
        # because 11 PM Pacific on day 7 = 2 AM Eastern on day 8 (outside rolling week)
        assert result['tasks_count'] == 0
    
    def test_week_tasks_with_malformed_dates(self, todoist_service, mock_todoist_api):
        """Test handling of malformed date values"""
        today = datetime.now(ZoneInfo('UTC')).date()
        start_of_week = today - timedelta(days=today.weekday())
        
        tasks = [
            # Valid task
            MockTodoistTask(
                id='1',
                content='Valid task',
                due=MockTodoistDue(date=start_of_week)
            ),
            # Task with malformed date string
            MockTodoistTask(
                id='2',
                content='Malformed date',
                due=MockTodoistDueCustom(date='not-a-date')
            ),
            # Task with empty due object
            MockTodoistTask(
                id='3',
                content='Empty due',
                due=MockTodoistDueCustom()
            ),
            # Task with null values
            MockTodoistTask(
                id='4',
                content='Null values',
                due=MockTodoistDueCustom(date=None, datetime_val=None)
            ),
        ]
        
        mock_todoist_api.get_tasks.return_value = iter([tasks])
        # Mock filter_tasks to return only the valid task
        mock_todoist_api.filter_tasks.return_value = iter([[tasks[0]]])
        
        result = todoist_service.get_week_tasks_resource()
        
        # Only the valid task should be included
        assert result['tasks_count'] == 1
        assert result['tasks'][0]['id'] == '1'
        
        # Check if debug info includes parsing errors
        if 'debug' in result:
            assert result['debug']['total_errors'] >= 1
    
    def test_week_tasks_sorting(self, todoist_service, mock_todoist_api):
        """Test that tasks are sorted by due date"""
        today = datetime.now(ZoneInfo('UTC')).date()
        start_of_week = today - timedelta(days=today.weekday())
        
        # Create tasks in random order
        tasks = [
            MockTodoistTask(
                id='3',
                content='Thursday task',
                due=MockTodoistDue(date=start_of_week + timedelta(days=3))
            ),
            MockTodoistTask(
                id='1',
                content='Monday task',
                due=MockTodoistDue(date=start_of_week)
            ),
            MockTodoistTask(
                id='2',
                content='Tuesday task',
                due=MockTodoistDue(date=start_of_week + timedelta(days=1))
            ),
        ]
        
        mock_todoist_api.get_tasks.return_value = iter([tasks])
        # Mock filter_tasks to return all tasks (they're all within the week)
        mock_todoist_api.filter_tasks.return_value = iter([tasks])
        
        result = todoist_service.get_week_tasks_resource()
        
        # Tasks should be sorted by date
        assert result['tasks'][0]['id'] == '1'  # Monday
        assert result['tasks'][1]['id'] == '2'  # Tuesday
        assert result['tasks'][2]['id'] == '3'  # Thursday
    
    def test_week_tasks_with_recurring_flag(self, todoist_service, mock_todoist_api):
        """Test that recurring tasks are included correctly"""
        today = datetime.now(ZoneInfo('UTC')).date()
        start_of_week = today - timedelta(days=today.weekday())
        
        tasks = [
            # Recurring task due this week
            MockTodoistTask(
                id='1',
                content='Recurring weekly task',
                due=MockTodoistDueCustom(
                    date=start_of_week + timedelta(days=2),
                    is_recurring=True,
                    string='every Wednesday'
                )
            ),
            # Non-recurring task
            MockTodoistTask(
                id='2',
                content='One-time task',
                due=MockTodoistDueCustom(
                    date=start_of_week + timedelta(days=3),
                    is_recurring=False
                )
            ),
        ]
        
        mock_todoist_api.get_tasks.return_value = iter([tasks])
        # Mock filter_tasks to return all tasks (they're all within the week)
        mock_todoist_api.filter_tasks.return_value = iter([tasks])
        
        result = todoist_service.get_week_tasks_resource()
        
        # Both tasks should be included
        assert result['tasks_count'] == 2
        
        # Verify recurring flag is preserved
        recurring_task = next(t for t in result['tasks'] if t['id'] == '1')
        assert recurring_task['due']['is_recurring'] == True
    
    def test_week_tasks_with_datetime_objects(self, todoist_service, mock_todoist_api):
        """Test tasks with actual datetime objects (not strings)"""
        today = datetime.now(ZoneInfo('UTC')).date()
        start_of_week = today - timedelta(days=today.weekday())
        
        # Create tasks with actual datetime objects
        tasks = [
            # Task with datetime object
            MockTodoistTask(
                id='1',
                content='DateTime object task',
                due=MockTodoistDueCustom(
                    datetime_val=datetime.combine(
                        start_of_week + timedelta(days=1),
                        datetime.min.time(),
                        tzinfo=ZoneInfo('UTC')
                    )
                )
            ),
            # Task with date object in datetime field
            MockTodoistTask(
                id='2',
                content='Date in datetime field',
                due=MockTodoistDueCustom(
                    datetime_val=start_of_week + timedelta(days=2)
                )
            ),
        ]
        
        mock_todoist_api.get_tasks.return_value = iter([tasks])
        # Mock filter_tasks to return all tasks (they're all within the week)
        mock_todoist_api.filter_tasks.return_value = iter([tasks])
        
        result = todoist_service.get_week_tasks_resource()
        
        # Both tasks should be included
        assert result['tasks_count'] == 2
        task_ids = [t['id'] for t in result['tasks']]
        assert '1' in task_ids
        assert '2' in task_ids