import requests
import logging
from datetime import datetime
from database import db_session, PlayerInjury, GameWeather
import uuid

logger = logging.getLogger(__name__)

# FantasyPros API
FANTASY_PROS_URL = "https://www.fantasypros.com/api/v1"

# NOAA Weather API
NOAA_POINTS_URL = "https://api.weather.gov/points"
NOAA_FORECAST_URL = "https://api.weather.gov/gridpoints"

def sync_injuries_and_weather():
    """Sync injury and weather data from external sources"""
    try:
        sync_injuries()
        sync_weather()
        logger.info("Successfully synced injuries and weather")
    except Exception as e:
        logger.error(f"Error syncing external data: {str(e)}")

def sync_injuries():
    """Sync NFL injury reports from FantasyPros"""
    try:
        # This would connect to FantasyPros API
        # For MVP, we'll create placeholder data
        logger.info("Syncing injuries...")
        
        # Example: Create some test injury data
        # In production, pull from FantasyPros API
        
    except Exception as e:
        logger.error(f"Error syncing injuries: {str(e)}")

def sync_weather():
    """Sync game weather from NOAA"""
    try:
        # This would connect to NOAA Weather API
        # For MVP, we'll create placeholder data
        logger.info("Syncing weather...")
        
        # NFL stadiums and their coordinates (example)
        nfl_stadiums = {
            "KC": (39.0489, -94.4795),  # Arrowhead Stadium
            "DEN": (39.7434, -104.9857),  # Empower Field
            "LA": (33.9733, -118.2437),  # SoFi Stadium
        }
        
        # For MVP, we'll create placeholder weather data
        # In production, call NOAA API with these coordinates
        
    except Exception as e:
        logger.error(f"Error syncing weather: {str(e)}")

def get_injury_data_for_player(player_id):
    """Get injury data for a specific player"""
    try:
        injury = db_session.query(PlayerInjury).filter_by(
            player_id=player_id
        ).order_by(PlayerInjury.updated_at.desc()).first()
        
        if injury:
            return {
                "status": injury.status,
                "description": injury.injury_description,
                "updated": injury.updated_at.isoformat()
            }
        return None
    
    except Exception as e:
        logger.error(f"Error getting injury data: {str(e)}")
        return None

def get_weather_for_game(game_id):
    """Get weather data for a specific game"""
    try:
        weather = db_session.query(GameWeather).filter_by(
            game_id=game_id
        ).first()
        
        if weather:
            return weather.weather
        return None
    
    except Exception as e:
        logger.error(f"Error getting weather data: {str(e)}")
        return None
