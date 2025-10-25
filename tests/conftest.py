"""Shared fixtures and configuration for tests"""

import os
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from datetime import datetime, date, timezone, timedelta
from typing import Dict, List, Any, Optional


# ============================================================================
# Mock Classes
# ============================================================================

class MockTodoistTask:
    """Mock Todoist Task object"""
    def __init__(self, **kwargs):
        self.id = kwargs.get('id', '123')
        self.content = kwargs.get('content', 'Test Task')
        self.description = kwargs.get('description', '')
        self.is_completed = kwargs.get('is_completed', False)
        self.labels = kwargs.get('labels', [])
        self.priority = kwargs.get('priority', 1)
        self.comment_count = kwargs.get('comment_count', 0)
        self.created_at = kwargs.get('created_at', datetime.now(timezone.utc).isoformat())
        self.creator_id = kwargs.get('creator_id', 'user123')
        self.assignee_id = kwargs.get('assignee_id', None)
        self.assigner_id = kwargs.get('assigner_id', None)
        self.project_id = kwargs.get('project_id', 'proj123')
        self.section_id = kwargs.get('section_id', None)
        self.parent_id = kwargs.get('parent_id', None)
        self.order = kwargs.get('order', 0)
        self.url = kwargs.get('url', f'https://todoist.com/tasks/{self.id}')
        self.due = kwargs.get('due', None)
        self.duration = kwargs.get('duration', None)


class MockTodoistDue:
    """Mock Todoist Due object"""
    def __init__(self, **kwargs):
        self.date = kwargs.get('date', date.today())
        self.string = kwargs.get('string', 'today')
        self.datetime = kwargs.get('datetime', None)
        self.timezone = kwargs.get('timezone', None)
        self.is_recurring = kwargs.get('is_recurring', False)


class MockTodoistProject:
    """Mock Todoist Project object"""
    def __init__(self, **kwargs):
        self.id = kwargs.get('id', 'proj123')
        self.name = kwargs.get('name', 'Test Project')
        self.color = kwargs.get('color', 'blue')
        self.parent_id = kwargs.get('parent_id', None)
        self.order = kwargs.get('order', 0)
        self.is_shared = kwargs.get('is_shared', False)
        self.is_favorite = kwargs.get('is_favorite', False)
        self.is_inbox_project = kwargs.get('is_inbox_project', False)
        self.is_archived = kwargs.get('is_archived', False)
        self.is_collapsed = kwargs.get('is_collapsed', False)
        self.view_style = kwargs.get('view_style', 'list')
        self.url = kwargs.get('url', f'https://todoist.com/projects/{self.id}')
        self.description = kwargs.get('description', '')
        self.workspace_id = kwargs.get('workspace_id', None)
        self.folder_id = kwargs.get('folder_id', None)


class MockTodoistLabel:
    """Mock Todoist Label object"""
    def __init__(self, **kwargs):
        self.id = kwargs.get('id', 'label123')
        self.name = kwargs.get('name', 'test-label')
        self.color = kwargs.get('color', 'red')
        self.order = kwargs.get('order', 0)
        self.is_favorite = kwargs.get('is_favorite', False)


class MockTodoistSection:
    """Mock Todoist Section object"""
    def __init__(self, **kwargs):
        self.id = kwargs.get('id', 'section123')
        self.name = kwargs.get('name', 'Test Section')
        self.project_id = kwargs.get('project_id', 'proj123')
        self.order = kwargs.get('order', 0)


class MockTodoistComment:
    """Mock Todoist Comment object"""
    def __init__(self, **kwargs):
        self.id = kwargs.get('id', 'comment123')
        self.content = kwargs.get('content', 'Test comment')
        self.posted_at = kwargs.get('posted_at', datetime.now(timezone.utc).isoformat())
        self.task_id = kwargs.get('task_id', None)
        self.project_id = kwargs.get('project_id', None)
        self.attachment = kwargs.get('attachment', None)


# ============================================================================
# Todoist Fixtures
# ============================================================================

@pytest.fixture
def mock_todoist_api():
    """Mock TodoistAPI client"""
    with patch('services.todoist.TodoistAPI') as mock_api_class:
        mock_api = MagicMock()
        mock_api_class.return_value = mock_api
        
        # Setup default responses for common operations
        mock_api.get_projects.return_value = iter([[
            MockTodoistProject(id='1', name='Work'),
            MockTodoistProject(id='2', name='Personal', is_inbox_project=True)
        ]])
        
        mock_api.get_labels.return_value = iter([[
            MockTodoistLabel(id='1', name='urgent'),
            MockTodoistLabel(id='2', name='work')
        ]])
        
        mock_api.get_tasks.return_value = iter([[
            MockTodoistTask(id='1', content='Task 1'),
            MockTodoistTask(id='2', content='Task 2', priority=4)
        ]])
        
        mock_api.add_task.return_value = MockTodoistTask(
            id='new123',
            content='New Task'
        )
        
        mock_api.update_task.return_value = MockTodoistTask(
            id='123',
            content='Updated Task'
        )
        
        mock_api.complete_task.return_value = True
        mock_api.uncomplete_task.return_value = True
        mock_api.delete_task.return_value = True
        
        mock_api.get_project.return_value = MockTodoistProject(id='1', name='Work')
        mock_api.get_section.return_value = MockTodoistSection(id='1', name='In Progress')
        mock_api.get_label.return_value = MockTodoistLabel(id='1', name='urgent')
        
        yield mock_api


@pytest.fixture
def todoist_service(mock_todoist_api):
    """Create TodoistService with mocked API"""
    with patch.dict(os.environ, {'TODOIST_API_TOKEN': 'test_token', 'TIMEZONE': 'UTC'}):
        from services.todoist import TodoistService
        service = TodoistService('test_token')
        return service


# ============================================================================
# Home Assistant Fixtures
# ============================================================================

@pytest.fixture
def mock_websocket():
    """Mock WebSocket for Home Assistant"""
    with patch('websocket.WebSocketApp') as mock_ws_class:
        mock_ws = MagicMock()
        mock_ws_class.return_value = mock_ws
        
        # Setup WebSocket behavior
        mock_ws.send = MagicMock()
        mock_ws.close = MagicMock()
        mock_ws.run_forever = MagicMock()
        
        yield mock_ws


@pytest.fixture
def mock_ha_responses():
    """Mock Home Assistant API responses"""
    return {
        'states': [
            {
                'entity_id': 'sensor.temperature',
                'state': '22.5',
                'attributes': {
                    'unit_of_measurement': '°C',
                    'friendly_name': 'Temperature'
                }
            },
            {
                'entity_id': 'light.living_room',
                'state': 'on',
                'attributes': {
                    'brightness': 255,
                    'friendly_name': 'Living Room Light'
                }
            }
        ],
        'areas': [
            {
                'area_id': 'living_room',
                'name': 'Living Room',
                'aliases': []
            },
            {
                'area_id': 'bedroom',
                'name': 'Bedroom',
                'aliases': []
            }
        ],
        'devices': [
            {
                'id': 'device123',
                'name': 'Smart Light',
                'area_id': 'living_room'
            }
        ]
    }


@pytest.fixture
def homeassistant_client(mock_websocket, mock_ha_responses):
    """Create HomeAssistantClient with mocked WebSocket"""
    with patch.dict(os.environ, {
        'HA_URL': 'http://localhost:8123',
        'HA_TOKEN': 'test_token'
    }):
        with patch('requests.get') as mock_get:
            mock_get.return_value.json.return_value = mock_ha_responses['states']
            mock_get.return_value.status_code = 200
            
            from services.homeassistant import HomeAssistantClient
            client = HomeAssistantClient(
                url='http://localhost:8123',
                access_token='test_token'
            )
            return client


# ============================================================================
# iCalendar Fixtures
# ============================================================================

@pytest.fixture
def sample_ical_data():
    """Sample iCalendar data for testing"""
    return """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//Test Calendar//EN
BEGIN:VEVENT
UID:test-event-1@example.com
DTSTART:20240101T100000Z
DTEND:20240101T110000Z
SUMMARY:Test Event 1
DESCRIPTION:This is a test event
LOCATION:Conference Room
END:VEVENT
BEGIN:VEVENT
UID:test-event-2@example.com
DTSTART:20240102T140000Z
DTEND:20240102T150000Z
SUMMARY:Test Event 2
RRULE:FREQ=WEEKLY;COUNT=4
END:VEVENT
END:VCALENDAR"""


@pytest.fixture
def sample_ical_with_timezone():
    """Sample iCalendar data with timezone information"""
    return """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//Test Calendar//EN
BEGIN:VTIMEZONE
TZID:America/New_York
BEGIN:STANDARD
DTSTART:20231105T020000
TZOFFSETFROM:-0400
TZOFFSETTO:-0500
RRULE:FREQ=YEARLY;BYMONTH=11;BYDAY=1SU
END:STANDARD
BEGIN:DAYLIGHT
DTSTART:20240310T020000
TZOFFSETFROM:-0500
TZOFFSETTO:-0400
RRULE:FREQ=YEARLY;BYMONTH=3;BYDAY=2SU
END:DAYLIGHT
END:VTIMEZONE
BEGIN:VEVENT
UID:tz-event-1@example.com
DTSTART;TZID=America/New_York:20240101T100000
DTEND;TZID=America/New_York:20240101T110000
SUMMARY:Event with Timezone
END:VEVENT
END:VCALENDAR"""


@pytest.fixture
def mock_ical_feeds():
    """Mock iCalendar feed URLs and responses"""
    with patch('requests.get') as mock_get:
        def side_effect(url, *args, **kwargs):
            response = MagicMock()
            response.status_code = 200
            
            if 'personal' in url:
                response.text = """BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:personal-1@example.com
DTSTART:20240101T090000Z
DTEND:20240101T100000Z
SUMMARY:Personal Event
END:VEVENT
END:VCALENDAR"""
            elif 'work' in url:
                response.text = """BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:work-1@example.com
DTSTART:20240101T090000Z
DTEND:20240101T100000Z
SUMMARY:Work Meeting
END:VEVENT
END:VCALENDAR"""
            else:
                response.text = """BEGIN:VCALENDAR
VERSION:2.0
END:VCALENDAR"""
            
            return response
        
        mock_get.side_effect = side_effect
        yield mock_get


# ============================================================================
# Helper Fixtures
# ============================================================================

@pytest.fixture
def sample_ha_entities():
    """Sample Home Assistant entities for categorization testing"""
    return [
        {'entity_id': 'sensor.temperature_living_room', 'domain': 'sensor'},
        {'entity_id': 'sensor.humidity_bedroom', 'domain': 'sensor'},
        {'entity_id': 'light.kitchen', 'domain': 'light'},
        {'entity_id': 'switch.garage_door', 'domain': 'switch'},
        {'entity_id': 'binary_sensor.motion_hallway', 'domain': 'binary_sensor'},
        {'entity_id': 'climate.thermostat', 'domain': 'climate'},
        {'entity_id': 'media_player.living_room_tv', 'domain': 'media_player'},
        {'entity_id': 'lock.front_door', 'domain': 'lock'},
        {'entity_id': 'cover.garage_door', 'domain': 'cover'},
        {'entity_id': 'camera.driveway', 'domain': 'camera'}
    ]


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
        'TODOIST_API_TOKEN': 'test_todoist_token',
        'HA_URL': 'http://localhost:8123',
        'HA_TOKEN': 'test_ha_token',
        'ICAL_PERSONAL_URL': 'http://example.com/personal.ics',
        'ICAL_WORK_URL': 'http://example.com/work.ics',
        'MCP_API_KEY': 'test_mcp_key'
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
        'today': now.date(),
        'tomorrow': (now + timedelta(days=1)).date(),
        'yesterday': (now - timedelta(days=1)).date(),
        'next_week': (now + timedelta(days=7)).date(),
        'last_week': (now - timedelta(days=7)).date(),
        'now': now,
        'one_hour_ago': now - timedelta(hours=1),
        'one_hour_later': now + timedelta(hours=1)
    }


@pytest.fixture
def test_priorities():
    """Todoist priority mappings"""
    return {
        'urgent': 4,
        'high': 3,
        'medium': 2,
        'low': 1,
        'default': 1
    }


@pytest.fixture
def test_colors():
    """Todoist color options"""
    return [
        'berry_red', 'red', 'orange', 'yellow', 'olive_green', 
        'lime_green', 'green', 'mint_green', 'teal', 'sky_blue',
        'light_blue', 'blue', 'grape', 'violet', 'lavender',
        'magenta', 'salmon', 'charcoal', 'grey', 'taupe'
    ]