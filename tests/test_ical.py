"""Unit tests for iCalendar service"""

import pytest
from unittest.mock import MagicMock, patch, Mock
from datetime import datetime, date, timedelta, timezone
from services.ical import MultiCalendarService, CalendarFeed
from icalendar import Calendar, Event
import requests


class TestCalendarFeed:
    """Test suite for CalendarFeed class"""
    
    def test_init_with_name(self):
        """Test feed initialization with explicit name"""
        feed = CalendarFeed(url='https://example.com/calendar.ics', name='Work Calendar')
        assert feed.url == 'https://example.com/calendar.ics'
        assert feed.name == 'Work Calendar'
        assert feed.calendar is None
        assert feed.last_fetch is None
        assert feed.error is None
    
    def test_init_without_name(self):
        """Test feed initialization without name (auto-generated)"""
        feed = CalendarFeed(url='https://calendar.google.com/calendar.ics')
        # The auto-generated name comes from the domain
        assert 'calendar' in feed.name
        
        feed2 = CalendarFeed(url='https://outlook.com/work/calendar.ics')
        assert 'outlook' in feed2.name
    
    def test_id_generation(self):
        """Test that feed ID is generated from URL hash"""
        feed = CalendarFeed(url='https://example.com/calendar.ics')
        assert len(feed.id) == 8
        # Same URL should generate same ID
        feed2 = CalendarFeed(url='https://example.com/calendar.ics')
        assert feed.id == feed2.id


class TestMultiCalendarService:
    """Test suite for MultiCalendarService"""
    
    # ========== INITIALIZATION TESTS ==========
    
    @patch('services.ical.MultiCalendarService.refresh_all_calendars')
    @patch('services.ical.MultiCalendarService._schedule_refresh')
    def test_init_with_feeds(self, mock_schedule, mock_refresh):
        """Test service initialization with feed configurations"""
        feed_configs = [
            {'url': 'https://example.com/personal.ics', 'name': 'Personal'},
            {'url': 'https://example.com/work.ics', 'name': 'Work'}
        ]
        
        service = MultiCalendarService(feed_configs, refresh_interval_minutes=30)
        
        assert len(service.feeds) == 2
        assert service.refresh_interval == 1800  # 30 * 60
        mock_refresh.assert_called_once()
        mock_schedule.assert_called_once()
    
    @patch('services.ical.MultiCalendarService.refresh_all_calendars')
    @patch('services.ical.MultiCalendarService._schedule_refresh')
    def test_init_empty_feeds(self, mock_schedule, mock_refresh):
        """Test service initialization with no feeds"""
        service = MultiCalendarService([], refresh_interval_minutes=60)
        assert len(service.feeds) == 0
    
    # ========== VALIDATION TESTS ==========
    
    def test_validate_url_valid(self):
        """Test URL validation with valid URLs"""
        service = MultiCalendarService([])
        
        service._validate_url('https://example.com/calendar.ics')  # Should not raise
        service._validate_url('http://example.com/calendar.ics')  # Should not raise
        service._validate_url('webcal://example.com/calendar.ics')  # Should not raise
    
    def test_validate_url_empty(self):
        """Test URL validation with empty URL"""
        service = MultiCalendarService([])
        
        with pytest.raises(ValueError, match="Calendar URL is required"):
            service._validate_url('')
    
    def test_validate_url_invalid_format(self):
        """Test URL validation with invalid format"""
        service = MultiCalendarService([])
        
        with pytest.raises(ValueError, match="Invalid URL format"):
            service._validate_url('not-a-url')
    
    @pytest.mark.parametrize("date_str", ["2024-12-31", "2024-01-01", "2025-06-15"])
    def test_validate_date_format_valid(self, date_str):
        """Test date format validation with valid dates"""
        service = MultiCalendarService([])
        service._validate_date_format(date_str, 'start_date')  # Should not raise
    
    @pytest.mark.parametrize("date_str", ["12/31/2024", "2024-13-01", "invalid", "31-12-2024"])
    def test_validate_date_format_invalid(self, date_str):
        """Test date format validation with invalid dates"""
        service = MultiCalendarService([])
        
        with pytest.raises(ValueError, match="Invalid .* format"):
            service._validate_date_format(date_str, 'test_date')
    
    def test_validate_feed_exists_valid(self):
        """Test feed validation with existing feed"""
        service = MultiCalendarService([])
        feed = CalendarFeed('https://example.com/test.ics', 'Test')
        service.feeds[feed.id] = feed
        
        result = service._validate_feed_exists(feed.id)
        assert result == feed
        
        # Test by name
        result = service._validate_feed_exists('Test')
        assert result == feed
    
    def test_validate_feed_exists_invalid(self):
        """Test feed validation with non-existent feed"""
        service = MultiCalendarService([])
        
        with pytest.raises(ValueError, match="Calendar feed .* not found"):
            service._validate_feed_exists('nonexistent')
    
    # ========== FEED MANAGEMENT TESTS ==========
    
    def test_add_feed(self):
        """Test adding a new calendar feed"""
        service = MultiCalendarService([])
        
        with patch.object(service, '_refresh_single_calendar') as mock_refresh:
            mock_refresh.return_value = {
                'status': 'success',
                'name': 'New Calendar',
                'url': 'https://example.com/new.ics'
            }
            
            result = service.add_feed(
                url='https://example.com/new.ics',
                name='New Calendar'
            )
            
            assert result['status'] == 'success'
            assert len(service.feeds) == 1
            mock_refresh.assert_called_once()
    
    def test_remove_feed(self):
        """Test removing a calendar feed"""
        service = MultiCalendarService([])
        feed = CalendarFeed('https://example.com/test.ics', 'Test')
        service.feeds[feed.id] = feed
        
        result = service.remove_feed('Test')
        
        assert result['status'] == 'removed'
        assert len(service.feeds) == 0
    
    def test_list_feeds(self):
        """Test listing all calendar feeds"""
        service = MultiCalendarService([])
        
        # Add some feeds
        feed1 = CalendarFeed('https://example.com/feed1.ics', 'Feed 1')
        feed2 = CalendarFeed('https://example.com/feed2.ics', 'Feed 2')
        service.feeds[feed1.id] = feed1
        service.feeds[feed2.id] = feed2
        
        result = service.list_feeds()
        
        assert len(result) == 2
        assert any(f['name'] == 'Feed 1' for f in result)
        assert any(f['name'] == 'Feed 2' for f in result)
    
    # ========== CALENDAR FETCHING TESTS ==========
    
    @patch('icalendar.Calendar.from_ical')
    @patch('requests.get')
    def test_refresh_single_calendar_success(self, mock_get, mock_from_ical):
        """Test successful calendar refresh"""
        service = MultiCalendarService([])
        feed = CalendarFeed('https://example.com/test.ics', 'Test')
        service.feeds[feed.id] = feed
        
        # Mock response
        mock_response = Mock()
        mock_response.text = "mock calendar data"
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response
        
        # Mock calendar parsing
        mock_calendar = MagicMock()
        mock_from_ical.return_value = mock_calendar
        
        result = service._refresh_single_calendar(feed)
        
        assert result['status'] == 'success'
        assert feed.calendar is not None
        assert feed.last_fetch is not None
        assert feed.error is None
    
    @patch('requests.get')
    def test_refresh_single_calendar_error(self, mock_get):
        """Test calendar refresh with error"""
        service = MultiCalendarService([])
        feed = CalendarFeed('https://example.com/test.ics', 'Test')
        
        mock_get.side_effect = requests.RequestException("Connection error")
        
        result = service._refresh_single_calendar(feed)
        
        assert result['status'] == 'error'
        assert 'Connection error' in result['error']
    
    @patch('icalendar.Calendar.from_ical')
    @patch('requests.get')
    def test_refresh_all_calendars(self, mock_get, mock_from_ical):
        """Test refreshing all calendars"""
        service = MultiCalendarService([])
        
        # Add feeds
        feed1 = CalendarFeed('https://example.com/feed1.ics', 'Feed 1')
        feed2 = CalendarFeed('https://example.com/feed2.ics', 'Feed 2')
        service.feeds[feed1.id] = feed1
        service.feeds[feed2.id] = feed2
        
        # Mock responses
        mock_response = Mock()
        mock_response.text = "mock calendar data"
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response
        
        # Mock calendar parsing
        mock_calendar = MagicMock()
        mock_from_ical.return_value = mock_calendar
        
        result = service.refresh_all_calendars()
        
        assert mock_get.call_count == 2
        assert result['feeds_refreshed'] == 2
    
    # ========== EVENT RETRIEVAL TESTS ==========
    
    @patch('recurring_ical_events.of')
    def test_get_events_single_feed(self, mock_recurring):
        """Test getting events from a single feed"""
        service = MultiCalendarService([])
        
        # Create mock feed with calendar
        feed = CalendarFeed('https://example.com/test.ics', 'Test')
        cal = Calendar()
        cal.add('prodid', '-//Test//Test//EN')
        cal.add('version', '2.0')
        
        event = Event()
        event.add('summary', 'Test Event')
        event.add('dtstart', datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc))
        event.add('dtend', datetime(2024, 1, 1, 11, 0, 0, tzinfo=timezone.utc))
        event.add('uid', 'test-event@example.com')
        cal.add_component(event)
        
        feed.calendar = cal
        service.feeds[feed.id] = feed
        
        # Mock the recurring_ical_events.of().between() chain
        mock_between = MagicMock(return_value=[event])
        mock_recurring.return_value.between = mock_between
        
        events = service.get_events(
            start_date='2024-01-01',
            end_date='2024-01-31'
        )
        
        assert len(events) == 1
        assert events[0]['summary'] == 'Test Event'
        assert events[0]['source_feed_name'] == 'Test'
    
    def test_get_events_multiple_feeds(self):
        """Test getting events from multiple feeds"""
        service = MultiCalendarService([])
        
        # Create two feeds with calendars
        for i, name in enumerate(['Personal', 'Work']):
            feed = CalendarFeed(f'https://example.com/{name.lower()}.ics', name)
            cal = Calendar()
            cal.add('prodid', f'-//{name}//EN')
            cal.add('version', '2.0')
            
            event = Event()
            event.add('summary', f'{name} Event')
            event.add('dtstart', datetime(2024, 1, i+1, 10, 0, 0, tzinfo=timezone.utc))
            event.add('dtend', datetime(2024, 1, i+1, 11, 0, 0, tzinfo=timezone.utc))
            event.add('uid', f'{name.lower()}-event@example.com')
            cal.add_component(event)
            
            feed.calendar = cal
            service.feeds[feed.id] = feed
        
        with patch('recurring_ical_events.of') as mock_recurring:
            # Return the event for each call
            mock_recurring.side_effect = [
                [list(cal.walk('VEVENT'))[0]] for cal in 
                [f.calendar for f in service.feeds.values()]
            ]
            
            events = service.get_events(
                start_date='2024-01-01',
                end_date='2024-01-31'
            )
            
            assert len(events) == 2
            summaries = [e['summary'] for e in events]
            assert 'Personal Event' in summaries
            assert 'Work Event' in summaries
            # Check that events have the correct feed names
            feed_names = [e['source_feed_name'] for e in events]
            assert 'Personal' in feed_names
            assert 'Work' in feed_names
    
    def test_search_events(self):
        """Test searching events"""
        service = MultiCalendarService([])
        
        # Create feed with multiple events
        feed = CalendarFeed('https://example.com/test.ics', 'Test')
        cal = Calendar()
        cal.add('prodid', '-//Test//EN')
        cal.add('version', '2.0')
        
        for title in ['Meeting with John', 'Lunch break', 'Meeting with Jane']:
            event = Event()
            event.add('summary', title)
            event.add('dtstart', datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc))
            event.add('dtend', datetime(2024, 1, 1, 11, 0, 0, tzinfo=timezone.utc))
            event.add('uid', f'{title.replace(" ", "-")}@example.com')
            cal.add_component(event)
        
        feed.calendar = cal
        service.feeds[feed.id] = feed
        
        events = service.search_events('Meeting')
        
        assert len(events) == 2
        for event in events:
            assert 'Meeting' in event['summary']
    
    @patch('recurring_ical_events.of')
    def test_get_events_with_pagination(self, mock_recurring):
        """Test getting events with pagination"""
        service = MultiCalendarService([])
        
        # Create mock feed with calendar
        feed = CalendarFeed('https://example.com/test.ics', 'Test')
        cal = Calendar()
        cal.add('prodid', '-//Test//Test//EN')
        cal.add('version', '2.0')
        
        # Create 10 mock events
        mock_events = []
        for i in range(10):
            event = Event()
            event.add('summary', f'Event {i}')
            event.add('dtstart', datetime(2024, 1, i+1, 10, 0, 0, tzinfo=timezone.utc))
            event.add('dtend', datetime(2024, 1, i+1, 11, 0, 0, tzinfo=timezone.utc))
            event.add('uid', f'event-{i}@example.com')
            cal.add_component(event)
            mock_events.append(event)
        
        feed.calendar = cal
        service.feeds[feed.id] = feed
        
        # Mock the recurring_ical_events.of().between() chain
        mock_between = MagicMock(return_value=mock_events)
        mock_recurring.return_value.between = mock_between
        
        # Get first 3 events
        events = service.get_events(
            start_date='2024-01-01',
            end_date='2024-01-31',
            limit=3,
            offset=0
        )
        assert len(events) == 3
        assert events[0]['summary'] == 'Event 0'
        assert events[2]['summary'] == 'Event 2'
        
        # Get next 3 events
        events = service.get_events(
            start_date='2024-01-01',
            end_date='2024-01-31',
            limit=3,
            offset=3
        )
        assert len(events) == 3
        assert events[0]['summary'] == 'Event 3'
        assert events[2]['summary'] == 'Event 5'
        
        # Get events with offset only
        events = service.get_events(
            start_date='2024-01-01',
            end_date='2024-01-31',
            offset=7
        )
        assert len(events) == 3
        assert events[0]['summary'] == 'Event 7'
        assert events[2]['summary'] == 'Event 9'
    
    # ========== CALENDAR INFO TESTS ==========
    
    def test_get_calendar_info(self):
        """Test getting calendar information"""
        service = MultiCalendarService([])
        
        # Add some feeds
        feed1 = CalendarFeed('https://example.com/feed1.ics', 'Feed 1')
        feed2 = CalendarFeed('https://example.com/feed2.ics', 'Feed 2')
        feed1.last_fetch = datetime.now(timezone.utc)
        feed2.error = "Test error"
        service.feeds[feed1.id] = feed1
        service.feeds[feed2.id] = feed2
        
        info = service.get_calendar_info()
        
        assert info['total_feeds'] == 2
        assert info['refresh_interval_minutes'] == 60
        assert len(info['feeds']) == 2
    
    # ========== TIMER/SCHEDULING TESTS ==========
    
    def test_schedule_refresh(self):
        """Test that refresh scheduling works"""
        service = MultiCalendarService([], refresh_interval_minutes=60)
        
        assert service._refresh_timer is not None
        assert service._refresh_timer.interval == 3600
        
        # Cancel timer for cleanup
        service._refresh_timer.cancel()
    
    @patch('services.ical.MultiCalendarService.refresh_all_calendars')
    def test_auto_refresh(self, mock_refresh):
        """Test automatic refresh functionality"""
        service = MultiCalendarService([], refresh_interval_minutes=60)
        
        # Reset the mock since refresh_all_calendars is called in __init__
        mock_refresh.reset_mock()
        
        # Manually trigger auto refresh
        service._auto_refresh()
        
        mock_refresh.assert_called_once()
        
        # Cleanup
        if service._refresh_timer:
            service._refresh_timer.cancel()