import requests
import logging
from datetime import datetime
from database import db_session, League, Roster
import uuid

logger = logging.getLogger(__name__)

BASE_URL = "https://api.sleeper.app/v1"

class SleeperClient:
    def __init__(self):
        self.session = requests.Session()
    
    def get_league(self, league_id):
        try:
            url = f"{BASE_URL}/league/{league_id}"
            response = self.session.get(url)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Error fetching league: {str(e)}")
            raise
    
    def get_rosters(self, league_id):
        try:
            url = f"{BASE_URL}/league/{league_id}/rosters"
            response = self.session.get(url)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Error fetching rosters: {str(e)}")
            raise
    
    def get_draft_id(self, league_id):
        try:
            url = f"{BASE_URL}/league/{league_id}/drafts"
            response = self.session.get(url)
            response.raise_for_status()
            drafts = response.json()
            if drafts:
                return drafts[0]['draft_id']
            return None
        except Exception as e:
            logger.error(f"Error fetching draft id: {str(e)}")
            raise
    
    def get_draft_picks(self, draft_id):
        try:
            url = f"{BASE_URL}/draft/{draft_id}/picks"
            response = self.session.get(url)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Error fetching draft picks: {str(e)}")
            raise
    
    def get_players_map(self):
        try:
            url = f"{BASE_URL}/players/nfl"
            response = self.session.get(url)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Error fetching players: {str(e)}")
            raise
    
    def sync_league(self, league_id):
        try:
            league_data = self.get_league(league_id)
            
            league = db_session.query(League).filter_by(league_id=league_id).first()
            if not league:
                league = League(
                    id=str(uuid.uuid4()),
                    league_id=league_id,
                    name=league_data.get('name', 'Unknown'),
                    platform='sleeper',
                    settings=league_data
                )
                db_session.add(league)
            else:
                league.name = league_data.get('name', league.name)
                league.settings = league_data
            db_session.commit()
            
            rosters = self.get_rosters(league_id)
            roster_count = 0
            for roster in rosters:
                existing = db_session.query(Roster).filter_by(
                    league_id=league_id,
                    team_id=str(roster['roster_id'])
                ).first()
                
                if not existing:
                    new_roster = Roster(
                        id=str(uuid.uuid4()),
                        league_id=league_id,
                        team_id=str(roster['roster_id']),
                        team_name=roster.get('display_name', f"Team {roster['roster_id']}"),
                        owner_name=roster.get('owner_id'),
                        players=roster.get('players', []),
                        wins=roster.get('wins', 0),
                        losses=roster.get('losses', 0),
                        points_for=roster.get('points_for', 0),
                        points_against=roster.get('points_against', 0)
                    )
                    db_session.add(new_roster)
                    roster_count += 1
                else:
                    existing.team_name = roster.get('display_name', existing.team_name)
                    existing.players = roster.get('players', [])
                    existing.wins = roster.get('wins', 0)
                    existing.losses = roster.get('losses', 0)
                    existing.points_for = roster.get('points_for', 0)
                    existing.points_against = roster.get('points_against', 0)
            
            db_session.commit()
            logger.info(f"Successfully synced Sleeper league {league_id}")
            
            return {
                "status": "synced",
                "league_id": league_id,
                "rosters": roster_count
            }
        
        except Exception as e:
            logger.error(f"Error syncing league: {str(e)}")
            raise
