#!/usr/bin/env python3
"""
Sensor Categorization Service for Home Assistant
Separates weather, pool, indoor air quality, and HVAC sensors
"""

import re
from typing import Dict, List, Any, Optional
from enum import Enum

class SensorCategory(Enum):
    """Sensor categories"""
    WEATHER = "weather"
    POOL = "pool"
    INDOOR_AIR_QUALITY = "indoor_air_quality"
    HVAC = "hvac"
    INDOOR_TEMPERATURE = "indoor_temperature"
    OUTDOOR = "outdoor"
    ENERGY = "energy"
    SECURITY = "security"
    OTHER = "other"

class SensorCategorizer:
    """Categorize Home Assistant sensors by type and location"""
    
    # Weather-related keywords and patterns
    WEATHER_PATTERNS = [
        r'weather[_.]',
        r'forecast',
        r'precipitation',
        r'rain',
        r'snow',
        r'wind[_.]?speed',
        r'wind[_.]?direction',
        r'humidity.*outdoor',
        r'outdoor.*humidity',
        r'barometer',
        r'barometric',
        r'pressure.*outdoor',
        r'outdoor.*pressure',
        r'uv[_.]?index',
        r'solar[_.]?radiation',
        r'visibility',
        r'cloud',
        r'storm',
        r'lightning',
        r'dew[_.]?point',
        r'feels[_.]?like',
        r'meteorolog',
        r'outside.*temp',
        r'outdoor.*temp',
        r'exterior.*temp',
    ]
    
    # Pool-related keywords and patterns
    POOL_PATTERNS = [
        r'pool',
        r'spa',
        r'hot[_.]?tub',
        r'jacuzzi',
        r'chlorine',
        r'ph[_.]?level',
        r'alkalinity',
        r'water[_.]?temp.*pool',
        r'pool.*temp',
        r'pump.*pool',
        r'pool.*pump',
        r'filter.*pool',
        r'pool.*filter',
        r'heater.*pool',
        r'pool.*heater',
    ]
    
    # Indoor air quality keywords and patterns
    AIR_QUALITY_PATTERNS = [
        r'air[_.]?quality',
        r'aqi',
        r'co2',
        r'carbon[_.]?dioxide',
        r'co[_.]?sensor',
        r'carbon[_.]?monoxide',
        r'voc',
        r'volatile[_.]?organic',
        r'pm[0-9.]+',
        r'particulate',
        r'particle',
        r'radon',
        r'formaldehyde',
        r'allergen',
        r'pollen.*indoor',
        r'indoor.*pollen',
        r'smoke[_.]?detector',
        r'air[_.]?purifier',
        r'ventilation',
        r'indoor.*humidity',
        r'humidity.*indoor',
    ]
    
    # HVAC-related keywords and patterns
    HVAC_PATTERNS = [
        r'thermostat',
        r'hvac',
        r'furnace',
        r'ac[_.]',
        r'air[_.]?condition',
        r'heating',
        r'cooling',
        r'heat[_.]?pump',
        r'boiler',
        r'radiator',
        r'zone[_.]?temp',
        r'setpoint',
        r'set[_.]?point',
        r'target[_.]?temp',
        r'climate',
        r'nest',
        r'ecobee',
        r'honeywell',
        r'duct',
        r'damper',
        r'fan[_.]?coil',
    ]
    
    # Indoor temperature patterns (non-HVAC)
    INDOOR_TEMP_PATTERNS = [
        r'bedroom.*temp',
        r'bathroom.*temp',
        r'kitchen.*temp',
        r'living[_.]?room.*temp',
        r'office.*temp',
        r'basement.*temp',
        r'attic.*temp',
        r'room.*temp',
        r'indoor.*temp',
        r'inside.*temp',
        r'temp.*bedroom',
        r'temp.*bathroom',
        r'temp.*kitchen',
        r'temp.*living',
        r'temp.*office',
        r'temp.*basement',
        r'temp.*attic',
        r'temp.*room',
        r'temp.*indoor',
        r'temp.*inside',
    ]
    
    def __init__(self):
        """Initialize the sensor categorizer"""
        self.compile_patterns()
    
    def compile_patterns(self):
        """Compile regex patterns for efficiency"""
        self.weather_regex = [re.compile(p, re.IGNORECASE) for p in self.WEATHER_PATTERNS]
        self.pool_regex = [re.compile(p, re.IGNORECASE) for p in self.POOL_PATTERNS]
        self.air_quality_regex = [re.compile(p, re.IGNORECASE) for p in self.AIR_QUALITY_PATTERNS]
        self.hvac_regex = [re.compile(p, re.IGNORECASE) for p in self.HVAC_PATTERNS]
        self.indoor_temp_regex = [re.compile(p, re.IGNORECASE) for p in self.INDOOR_TEMP_PATTERNS]
    
    def categorize_sensor(self, entity: Dict[str, Any]) -> SensorCategory:
        """
        Categorize a single sensor entity
        
        Args:
            entity: Entity dict with entity_id, attributes, etc.
            
        Returns:
            SensorCategory enum value
        """
        entity_id = entity.get('entity_id', '')
        attributes = entity.get('attributes', {})
        friendly_name = attributes.get('friendly_name', '')
        device_class = attributes.get('device_class', '')
        unit = attributes.get('unit_of_measurement', '')
        
        # Combine all text for matching
        search_text = f"{entity_id} {friendly_name} {device_class}".lower()
        
        # Check pool first (most specific)
        if self._matches_patterns(search_text, self.pool_regex):
            return SensorCategory.POOL
        
        # Check HVAC
        if self._matches_patterns(search_text, self.hvac_regex):
            return SensorCategory.HVAC
        
        # Check air quality
        if self._matches_patterns(search_text, self.air_quality_regex):
            return SensorCategory.INDOOR_AIR_QUALITY
        
        # Check weather
        if self._matches_patterns(search_text, self.weather_regex) or device_class == 'weather':
            return SensorCategory.WEATHER
        
        # Check indoor temperature (after HVAC to avoid overlap)
        if self._matches_patterns(search_text, self.indoor_temp_regex):
            return SensorCategory.INDOOR_TEMPERATURE
        
        # Check by device_class
        if device_class in ['temperature', 'humidity']:
            # Try to determine if indoor or outdoor
            if any(word in search_text for word in ['outdoor', 'outside', 'exterior', 'garden', 'yard']):
                return SensorCategory.OUTDOOR
            elif any(word in search_text for word in ['indoor', 'inside', 'room', 'bedroom', 'kitchen', 'bathroom']):
                return SensorCategory.INDOOR_TEMPERATURE
        
        # Energy sensors
        if device_class in ['power', 'energy', 'voltage', 'current'] or 'kwh' in search_text or 'watt' in search_text:
            return SensorCategory.ENERGY
        
        # Security sensors
        if device_class in ['motion', 'door', 'window', 'lock'] or any(word in search_text for word in ['motion', 'door', 'window', 'lock', 'camera']):
            return SensorCategory.SECURITY
        
        return SensorCategory.OTHER
    
    def _matches_patterns(self, text: str, patterns: List[re.Pattern]) -> bool:
        """Check if text matches any of the patterns"""
        return any(pattern.search(text) for pattern in patterns)
    
    def categorize_sensors(self, entities: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
        """
        Categorize all sensor entities
        
        Args:
            entities: List of entity dictionaries
            
        Returns:
            Dictionary with categories as keys and lists of entities as values
        """
        categorized = {category.value: [] for category in SensorCategory}
        
        for entity in entities:
            # Only process sensor entities
            entity_id = entity.get('entity_id', '')
            if not entity_id.startswith('sensor.') and not entity_id.startswith('weather.'):
                continue
            
            category = self.categorize_sensor(entity)
            categorized[category.value].append(entity)
        
        return categorized
    
    def get_category_summary(self, categorized: Dict[str, List[Dict[str, Any]]]) -> Dict[str, Any]:
        """
        Get summary statistics for categorized sensors
        
        Args:
            categorized: Dictionary of categorized sensors
            
        Returns:
            Summary statistics
        """
        summary = {
            "total_sensors": sum(len(entities) for entities in categorized.values()),
            "categories": {}
        }
        
        for category, entities in categorized.items():
            if entities:  # Only include non-empty categories
                summary["categories"][category] = {
                    "count": len(entities),
                    "percentage": round(len(entities) / summary["total_sensors"] * 100, 1),
                    "sample_entities": [e.get('entity_id') for e in entities[:3]]
                }
        
        return summary
    
    def get_sensor_details(self, entity: Dict[str, Any]) -> Dict[str, Any]:
        """
        Get detailed information about a sensor
        
        Args:
            entity: Entity dictionary
            
        Returns:
            Detailed sensor information
        """
        attributes = entity.get('attributes', {})
        
        return {
            "entity_id": entity.get('entity_id'),
            "category": self.categorize_sensor(entity).value,
            "friendly_name": attributes.get('friendly_name'),
            "device_class": attributes.get('device_class'),
            "state": entity.get('state'),
            "unit": attributes.get('unit_of_measurement'),
            "last_changed": entity.get('last_changed'),
            "area": attributes.get('area_name'),  # If available
            "device": attributes.get('device_name'),  # If available
        }
    
    def filter_by_categories(self, entities: List[Dict[str, Any]], 
                            categories: List[str]) -> List[Dict[str, Any]]:
        """
        Filter entities by specific categories
        
        Args:
            entities: List of all entities
            categories: List of category names to include
            
        Returns:
            Filtered list of entities
        """
        filtered = []
        category_enums = [SensorCategory[cat.upper()] for cat in categories]
        
        for entity in entities:
            entity_id = entity.get('entity_id', '')
            if not entity_id.startswith('sensor.') and not entity_id.startswith('weather.'):
                continue
            
            if self.categorize_sensor(entity) in category_enums:
                filtered.append(entity)
        
        return filtered
    
    def get_recommendations(self, categorized: Dict[str, List[Dict[str, Any]]]) -> List[str]:
        """
        Get recommendations based on sensor categorization
        
        Args:
            categorized: Dictionary of categorized sensors
            
        Returns:
            List of recommendations
        """
        recommendations = []
        
        # Check for missing categories
        if not categorized.get('weather'):
            recommendations.append("Consider adding weather sensors or integrating a weather service")
        
        if not categorized.get('indoor_air_quality'):
            recommendations.append("Consider adding indoor air quality sensors (CO2, VOC, PM2.5)")
        
        # Check for sensor balance
        total = sum(len(entities) for entities in categorized.values())
        if total > 0:
            hvac_percent = len(categorized.get('hvac', [])) / total * 100
            if hvac_percent > 40:
                recommendations.append("You have many HVAC sensors - consider grouping them by zone")
        
        # Pool safety
        if categorized.get('pool') and len(categorized['pool']) < 3:
            recommendations.append("Consider adding more pool sensors for safety (pH, chlorine, temperature)")
        
        return recommendations


def integrate_with_homeassistant(ha_service):
    """
    Integrate sensor categorization with HomeAssistantService
    
    Args:
        ha_service: Instance of HomeAssistantService
        
    Returns:
        Categorized sensor data
    """
    # Get all entities
    all_entities = ha_service.get_states()
    
    # Initialize categorizer
    categorizer = SensorCategorizer()
    
    # Categorize sensors
    categorized = categorizer.categorize_sensors(all_entities)
    
    # Get summary
    summary = categorizer.get_category_summary(categorized)
    
    # Get recommendations
    recommendations = categorizer.get_recommendations(categorized)
    
    return {
        "categorized": categorized,
        "summary": summary,
        "recommendations": recommendations
    }


if __name__ == "__main__":
    # Example usage
    print("Sensor Categorizer Module")
    print("Categories available:")
    for category in SensorCategory:
        print(f"  - {category.value}")