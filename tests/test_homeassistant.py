"""Unit tests for Home Assistant service"""

import pytest
from unittest.mock import MagicMock, patch, call, Mock
import json
import requests
from datetime import datetime, timezone
from services.homeassistant import (
    HomeAssistantService, 
    HomeAssistantClient, 
    ConnectionType, 
    Domain
)


class TestHomeAssistantService:
    """Test suite for HomeAssistantService (REST API)"""
    
    # ========== INITIALIZATION TESTS ==========
    
    def test_init_local_connection(self):
        """Test initialization with local connection"""
        service = HomeAssistantService(
            url='http://192.168.1.100:8123',
            access_token='test_token'
        )
        assert service.url == 'http://192.168.1.100:8123'
        assert service.access_token == 'test_token'
        assert service.connection_type == ConnectionType.LOCAL
    
    def test_init_nabu_casa_connection(self):
        """Test initialization with Nabu Casa connection"""
        service = HomeAssistantService(
            url='https://example.ui.nabu.casa',
            access_token='test_token'
        )
        assert service.connection_type == ConnectionType.NABU_CASA
    
    def test_init_strips_trailing_slash(self):
        """Test that trailing slash is removed from URL"""
        service = HomeAssistantService(
            url='http://localhost:8123/',
            access_token='test_token'
        )
        assert service.url == 'http://localhost:8123'
    
    # ========== VALIDATION TESTS ==========
    
    def test_validate_entity_id_valid(self):
        """Test entity ID validation with valid IDs"""
        service = HomeAssistantService('http://localhost', 'token')
        
        # Single entity
        service._validate_entity_id('light.living_room')  # Should not raise
        
        # Multiple entities
        service._validate_entity_id(['light.bedroom', 'switch.garage'])  # Should not raise
    
    def test_validate_entity_id_invalid_format(self):
        """Test entity ID validation with invalid format"""
        service = HomeAssistantService('http://localhost', 'token')
        
        with pytest.raises(ValueError, match="Invalid entity_id format"):
            service._validate_entity_id('invalid_entity')
    
    def test_validate_entity_id_invalid_domain(self):
        """Test entity ID validation with invalid domain"""
        service = HomeAssistantService('http://localhost', 'token')
        
        with pytest.raises(ValueError, match="Invalid domain"):
            service._validate_entity_id('invalid_domain.entity')
    
    def test_validate_domain_valid(self):
        """Test domain validation with valid domains"""
        service = HomeAssistantService('http://localhost', 'token')
        
        for domain in ['light', 'switch', 'sensor', 'climate']:
            service._validate_domain(domain)  # Should not raise
    
    def test_validate_domain_invalid(self):
        """Test domain validation with invalid domain"""
        service = HomeAssistantService('http://localhost', 'token')
        
        with pytest.raises(ValueError, match="Invalid domain"):
            service._validate_domain('invalid_domain')
    
    @pytest.mark.parametrize("brightness,expected", [
        (0, 0),
        (128, 128),
        (255, 255),
        ("100", 100),
        (None, None)
    ])
    def test_validate_brightness_valid(self, brightness, expected):
        """Test brightness validation with valid values"""
        service = HomeAssistantService('http://localhost', 'token')
        result = service._validate_brightness(brightness)
        assert result == expected
    
    @pytest.mark.parametrize("brightness", [-1, 256, 1000, "invalid"])
    def test_validate_brightness_invalid(self, brightness):
        """Test brightness validation with invalid values"""
        service = HomeAssistantService('http://localhost', 'token')
        
        with pytest.raises(ValueError, match="Invalid brightness"):
            service._validate_brightness(brightness)
    
    def test_validate_temperature_celsius_valid(self):
        """Test temperature validation in Celsius"""
        service = HomeAssistantService('http://localhost', 'token')
        service._validate_temperature(22.0, "C")  # Should not raise
        service._validate_temperature(-10.0, "C")  # Should not raise
    
    def test_validate_temperature_celsius_invalid(self):
        """Test temperature validation with invalid Celsius"""
        service = HomeAssistantService('http://localhost', 'token')
        
        with pytest.raises(ValueError, match="Invalid temperature"):
            service._validate_temperature(100.0, "C")
    
    # ========== STATE OPERATION TESTS ==========
    
    @patch('requests.get')
    def test_get_states(self, mock_get):
        """Test getting entity states"""
        service = HomeAssistantService('http://localhost', 'token')
        
        mock_response = Mock()
        mock_response.json.return_value = [
            {'entity_id': 'light.living_room', 'state': 'on'},
            {'entity_id': 'sensor.temperature', 'state': '22.5'}
        ]
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response
        
        states = service.get_states()
        
        assert len(states) == 2
        assert states[0]['entity_id'] == 'light.living_room'
        mock_get.assert_called_once_with(
            'http://localhost/api/states',
            headers=service.headers,
            timeout=service.timeout,
            verify=service.verify_ssl
        )
    
    @patch('requests.get')
    def test_get_states_with_filter(self, mock_get):
        """Test getting specific entity states"""
        service = HomeAssistantService('http://localhost', 'token')
        
        mock_response = Mock()
        mock_response.json.return_value = [
            {'entity_id': 'light.living_room', 'state': 'on', 'attributes': {'brightness': 255}},
            {'entity_id': 'light.bedroom', 'state': 'off', 'attributes': {}}
        ]
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response
        
        states = service.get_states(entity_ids=['light.living_room'])
        
        # Should filter to just the requested entity
        assert len(states) == 1
        assert states[0]['entity_id'] == 'light.living_room'
        mock_get.assert_called_once()
    
    @patch('requests.post')
    def test_set_state(self, mock_post):
        """Test setting entity state"""
        service = HomeAssistantService('http://localhost', 'token')
        
        mock_response = Mock()
        mock_response.json.return_value = {
            'entity_id': 'input_text.test',
            'state': 'new_value'
        }
        mock_response.raise_for_status = Mock()
        mock_post.return_value = mock_response
        
        result = service.set_state(
            'input_text.test',
            'new_value',
            {'friendly_name': 'Test Input'}
        )
        
        assert result['state'] == 'new_value'
        mock_post.assert_called_once()
    
    # ========== SERVICE CALL TESTS ==========
    
    @patch('requests.post')
    @patch.object(HomeAssistantService, '_validate_service')
    def test_call_service_basic(self, mock_validate, mock_post):
        """Test calling a basic service"""
        service = HomeAssistantService('http://localhost', 'token')
        
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = []
        mock_response.raise_for_status = Mock()
        mock_post.return_value = mock_response
        
        # Pass entity_id as a direct parameter, not in service_data
        result = service.call_service('light', 'turn_on', entity_id='light.living_room')
        
        assert result == {'status': 'success', 'domain': 'light', 'service': 'turn_on'}
        mock_post.assert_called_once_with(
            'http://localhost/api/services/light/turn_on',
            headers=service.headers,
            json={'entity_id': 'light.living_room'},
            timeout=service.timeout,
            verify=service.verify_ssl
        )
    
    @patch('requests.post')
    def test_turn_on_light(self, mock_post):
        """Test turning on a light with brightness"""
        service = HomeAssistantService('http://localhost', 'token')
        
        mock_response = Mock()
        mock_response.json.return_value = []
        mock_response.raise_for_status = Mock()
        mock_post.return_value = mock_response
        
        result = service.turn_on('light.living_room', brightness=200, color_temp=3000)
        
        mock_post.assert_called_once()
        call_args = mock_post.call_args
        assert call_args[1]['json']['entity_id'] == 'light.living_room'
        assert call_args[1]['json']['brightness'] == 200
        assert call_args[1]['json']['color_temp'] == 3000
    
    @patch('requests.post')
    def test_turn_off_entity(self, mock_post):
        """Test turning off an entity"""
        service = HomeAssistantService('http://localhost', 'token')
        
        mock_response = Mock()
        mock_response.json.return_value = []
        mock_response.raise_for_status = Mock()
        mock_post.return_value = mock_response
        
        result = service.turn_off('switch.garage')
        
        mock_post.assert_called_once()
        call_args = mock_post.call_args
        assert 'switch/turn_off' in call_args[0][0]
        assert call_args[1]['json']['entity_id'] == 'switch.garage'
    
    @patch('requests.post')
    def test_toggle_entity(self, mock_post):
        """Test toggling an entity"""
        service = HomeAssistantService('http://localhost', 'token')
        
        mock_response = Mock()
        mock_response.json.return_value = []
        mock_response.raise_for_status = Mock()
        mock_post.return_value = mock_response
        
        result = service.toggle('light.bedroom')
        
        mock_post.assert_called_once()
        call_args = mock_post.call_args
        assert 'light/toggle' in call_args[0][0]
    
    # ========== AREA AND DEVICE TESTS ==========
    
    @patch('services.homeassistant.HomeAssistantService._get_areas_via_websocket')
    @patch('requests.get')
    def test_get_areas(self, mock_get, mock_websocket):
        """Test getting areas"""
        service = HomeAssistantService('http://localhost', 'token')
        
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {'area_id': 'living_room', 'name': 'Living Room'},
            {'area_id': 'bedroom', 'name': 'Bedroom'}
        ]
        mock_get.return_value = mock_response
        
        areas = service.get_areas()
        
        assert len(areas) == 2
        # Default is minimal=True, so we get 'id' not 'area_id'
        assert areas[0]['id'] == 'living_room'
        assert areas[0]['name'] == 'Living Room'
        assert 'floor' in areas[0]  # Minimal format includes floor
        # Check caching - cache stores full data, not minimal
        assert service.areas_cache[0]['area_id'] == 'living_room'
        assert service.areas_cache[0]['name'] == 'Living Room'
    
    @patch('services.homeassistant.HomeAssistantService._get_areas_via_websocket')
    @patch('requests.get')
    def test_get_areas_non_minimal(self, mock_get, mock_websocket):
        """Test getting areas with minimal=False"""
        service = HomeAssistantService('http://localhost', 'token')
        
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {'area_id': 'living_room', 'name': 'Living Room', 'aliases': [], 'labels': []},
            {'area_id': 'bedroom', 'name': 'Bedroom', 'aliases': [], 'labels': []}
        ]
        mock_get.return_value = mock_response
        
        # Get areas with minimal=False
        areas = service.get_areas(minimal=False)
        
        assert len(areas) == 2
        # Non-minimal format should have original structure
        assert areas[0]['area_id'] == 'living_room'
        assert areas[0]['name'] == 'Living Room'
        assert 'aliases' in areas[0]
        assert 'labels' in areas[0]
        # Should be exactly what was returned
        assert areas == mock_response.json.return_value
    
    @patch('requests.get')
    def test_get_devices(self, mock_get):
        """Test getting devices"""
        service = HomeAssistantService('http://localhost', 'token')
        
        mock_response = Mock()
        mock_response.json.return_value = [
            {'id': 'device1', 'name': 'Smart Light', 'area_id': 'living_room'},
            {'id': 'device2', 'name': 'Thermostat', 'area_id': 'hallway'}
        ]
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response
        
        devices = service.get_devices()
        
        assert len(devices) == 2
        # Default is minimal=True, check for minimal fields
        assert devices[0]['id'] == 'device1'
        assert devices[0]['name'] == 'Smart Light'
        assert devices[0]['area_id'] == 'living_room'
        assert 'manufacturer' in devices[0]
        assert 'model' in devices[0]
        assert 'entities' in devices[0]
        # Check caching - cache stores full data, not minimal
        assert service.devices_cache[0]['id'] == 'device1'
        assert service.devices_cache[0]['name'] == 'Smart Light'
    
    @patch('requests.get')
    def test_get_devices_non_minimal(self, mock_get):
        """Test getting devices with minimal=False"""
        service = HomeAssistantService('http://localhost', 'token')
        
        mock_response = Mock()
        mock_response.json.return_value = [
            {'id': 'device1', 'name': 'Smart Light', 'area_id': 'living_room', 'sw_version': '1.0'},
            {'id': 'device2', 'name': 'Thermostat', 'area_id': 'hallway', 'hw_version': '2.0'}
        ]
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response
        
        # Get devices with minimal=False
        devices = service.get_devices(minimal=False)
        
        assert len(devices) == 2
        # Non-minimal format should have all original fields
        assert devices[0]['id'] == 'device1'
        assert devices[0]['name'] == 'Smart Light'
        assert devices[0]['area_id'] == 'living_room'
        assert devices[0]['sw_version'] == '1.0'
        # Should be exactly what was returned
        assert devices == mock_response.json.return_value
    
    @patch('requests.get')
    def test_get_devices_with_pagination(self, mock_get):
        """Test getting devices with pagination"""
        service = HomeAssistantService('http://localhost', 'token')
        
        mock_response = Mock()
        mock_response.json.return_value = [
            {'id': f'device{i}', 'name': f'Device {i}', 'area_id': 'room'}
            for i in range(10)
        ]
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response
        
        # Get first 3 devices
        devices = service.get_devices(limit=3, offset=0)
        assert len(devices) == 3
        assert devices[0]['id'] == 'device0'
        assert devices[2]['id'] == 'device2'
        
        # Get next 3 devices
        devices = service.get_devices(limit=3, offset=3)
        assert len(devices) == 3
        assert devices[0]['id'] == 'device3'
        assert devices[2]['id'] == 'device5'
        
        # Get devices with offset only
        devices = service.get_devices(offset=7)
        assert len(devices) == 3
        assert devices[0]['id'] == 'device7'
    
    @patch('services.homeassistant.HomeAssistantService.get_states')
    def test_get_entities(self, mock_get_states):
        """Test getting entities with default minimal=True"""
        service = HomeAssistantService('http://localhost', 'token')
        
        # Mock states that entities are derived from
        mock_get_states.return_value = [
            {
                'entity_id': 'light.living_room',
                'state': 'on',
                'attributes': {
                    'friendly_name': 'Living Room Light',
                    'device_class': 'light',
                    'area_id': 'living_room',
                    'icon': 'mdi:lightbulb'
                }
            }
        ]
        
        entities = service.get_entities()
        
        assert len(entities) == 1
        # Default minimal=True should only have essential fields
        assert entities[0]['entity_id'] == 'light.living_room'
        assert entities[0]['name'] == 'Living Room Light'
        assert entities[0]['domain'] == 'light'
        assert entities[0]['area_id'] == 'living_room'
        assert entities[0]['device_class'] == 'light'
        # Should NOT have non-essential fields in minimal mode
        assert 'icon' not in entities[0]
        assert 'unit_of_measurement' not in entities[0]
    
    @patch('services.homeassistant.HomeAssistantService.get_states')
    def test_get_entities_non_minimal(self, mock_get_states):
        """Test getting entities with minimal=False"""
        service = HomeAssistantService('http://localhost', 'token')
        
        # Mock states that entities are derived from
        mock_get_states.return_value = [
            {
                'entity_id': 'sensor.temperature',
                'state': '72',
                'attributes': {
                    'friendly_name': 'Temperature Sensor',
                    'device_class': 'temperature',
                    'unit_of_measurement': '°F',
                    'icon': 'mdi:thermometer',
                    'area_id': 'bedroom',
                    'device_id': 'temp_sensor_1'
                }
            }
        ]
        
        entities = service.get_entities(minimal=False)
        
        assert len(entities) == 1
        # Non-minimal should have all fields
        assert entities[0]['entity_id'] == 'sensor.temperature'
        assert entities[0]['name'] == 'Temperature Sensor'
        assert entities[0]['domain'] == 'sensor'
        assert entities[0]['device_class'] == 'temperature'
        assert entities[0]['unit_of_measurement'] == '°F'
        assert entities[0]['icon'] == 'mdi:thermometer'
        assert entities[0]['area_id'] == 'bedroom'
        assert entities[0]['device_id'] == 'temp_sensor_1'
        assert entities[0]['hidden'] == False
        assert entities[0]['disabled'] == False
    
    @patch('services.homeassistant.HomeAssistantService.get_states')
    def test_get_entities_with_pagination(self, mock_get_states):
        """Test getting entities with pagination"""
        service = HomeAssistantService('http://localhost', 'token')
        
        # Mock states for 10 entities
        mock_get_states.return_value = [
            {
                'entity_id': f'sensor.test_{i}',
                'state': 'on',
                'attributes': {
                    'friendly_name': f'Test Sensor {i}',
                    'device_class': 'sensor'
                }
            }
            for i in range(10)
        ]
        
        # Get first 4 entities
        entities = service.get_entities(limit=4, offset=0)
        assert len(entities) == 4
        assert entities[0]['entity_id'] == 'sensor.test_0'
        assert entities[3]['entity_id'] == 'sensor.test_3'
        
        # Get next 4 entities
        entities = service.get_entities(limit=4, offset=4)
        assert len(entities) == 4
        assert entities[0]['entity_id'] == 'sensor.test_4'
        assert entities[3]['entity_id'] == 'sensor.test_7'
        
        # Get entities with offset only
        entities = service.get_entities(offset=8)
        assert len(entities) == 2
        assert entities[0]['entity_id'] == 'sensor.test_8'
        assert entities[1]['entity_id'] == 'sensor.test_9'
    
    @patch('requests.get')
    def test_get_history_with_pagination(self, mock_get):
        """Test getting history with pagination"""
        service = HomeAssistantService('http://localhost', 'token')
        
        mock_response = Mock()
        # History API returns nested list
        mock_response.json.return_value = [[
            {'state': f'state_{i}', 'last_changed': f'2024-01-01T{i:02d}:00:00'}
            for i in range(10)
        ]]
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response
        
        # Get first 3 history entries
        history = service.get_history('sensor.test', limit=3, offset=0)
        assert len(history) == 3
        assert history[0]['state'] == 'state_0'
        assert history[2]['state'] == 'state_2'
        
        # Get next 3 history entries
        history = service.get_history('sensor.test', limit=3, offset=3)
        assert len(history) == 3
        assert history[0]['state'] == 'state_3'
        assert history[2]['state'] == 'state_5'
        
        # Get history with offset only
        history = service.get_history('sensor.test', offset=7)
        assert len(history) == 3
        assert history[0]['state'] == 'state_7'
        assert history[2]['state'] == 'state_9'
    
    # ========== ERROR HANDLING TESTS ==========
    
    @patch('requests.get')
    def test_api_error_handling(self, mock_get):
        """Test API error handling"""
        service = HomeAssistantService('http://localhost', 'token')
        
        mock_response = Mock()
        mock_response.raise_for_status.side_effect = requests.RequestException("Connection error")
        mock_get.return_value = mock_response
        
        # get_states raises ValueError on connection error
        with pytest.raises(ValueError, match="Failed to retrieve"):
            service.get_states()
    
    @patch('requests.get')
    def test_authentication_error(self, mock_get):
        """Test authentication error handling"""
        service = HomeAssistantService('http://localhost', 'token')
        
        mock_response = Mock()
        mock_response.status_code = 401
        mock_response.raise_for_status.side_effect = requests.HTTPError("401 Unauthorized")
        mock_get.return_value = mock_response
        
        # get_states raises ValueError on auth error
        with pytest.raises(ValueError, match="401 Unauthorized"):
            service.get_states()


class TestHomeAssistantClient:
    """Test suite for HomeAssistantClient (WebSocket)"""
    
    # ========== INITIALIZATION TESTS ==========
    
    def test_init_client(self, mock_websocket):
        """Test client initialization"""
        client = HomeAssistantClient(
            url='http://localhost:8123',
            access_token='test_token'
        )
        assert client.url == 'http://localhost:8123'
        assert client.access_token == 'test_token'
    
    def test_init_with_ssl(self, mock_websocket):
        """Test client initialization with SSL"""
        client = HomeAssistantClient(
            url='https://localhost:8123',
            access_token='test_token',
            verify_ssl=False
        )
        # HomeAssistantClient doesn't have verify_ssl, it uses the parent class
        assert client.url == 'https://localhost:8123'
    
    # ========== WEBSOCKET CONNECTION TESTS ==========
    
    def test_service_wrapper_methods(self, mock_websocket):
        """Test that HomeAssistantClient properly wraps HomeAssistantService"""
        client = HomeAssistantClient(
            url='http://localhost:8123',
            access_token='test_token'
        )
        
        # Check that service is initialized
        assert client.service is not None
        assert isinstance(client.service, HomeAssistantService)
        
        # Check that the URL and token are passed correctly
        assert client.service.url == 'http://localhost:8123'
        assert client.service.access_token == 'test_token'
    
    # ========== WRAPPER METHOD TESTS ==========
    
    @patch.object(HomeAssistantService, 'get_areas')
    def test_get_areas_wrapper(self, mock_get_areas, mock_websocket):
        """Test that get_areas is properly wrapped"""
        client = HomeAssistantClient(
            url='http://localhost:8123',
            access_token='test_token'
        )
        
        mock_get_areas.return_value = [
            {'area_id': 'living_room', 'name': 'Living Room'},
            {'area_id': 'bedroom', 'name': 'Bedroom'}
        ]
        
        areas = client.get_areas()
        
        assert len(areas) == 2
        assert areas[0]['name'] == 'Living Room'
        mock_get_areas.assert_called_once()
    
    @patch.object(HomeAssistantService, 'call_service')
    def test_call_service_wrapper(self, mock_call_service, mock_websocket):
        """Test that call_service is properly wrapped"""
        client = HomeAssistantClient(
            url='http://localhost:8123',
            access_token='test_token'
        )
        
        mock_call_service.return_value = {'status': 'success'}
        
        result = client.call_service(
            domain='light',
            service='turn_on',
            entity_id='light.living_room'
        )
        
        assert result == {'status': 'success'}
        mock_call_service.assert_called_once_with(
            'light',
            'turn_on',
            'light.living_room'  # entity_id is passed as positional arg
        )