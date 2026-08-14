import requests
import logging
from datetime import datetime
from database import db_session, League, Roster, Matchup, Score
import uuid

logger = logging.getLogger(__name__)

BASE_URL = "https://api.sleeper.app/v1"

class SleeperClient:
    def __init__(self):
        self.session = requests.Session()
    
    def get_league(self, league_id):
        """Get league info"""
        try:
            url = f"{BASE_URL}/league/{league_id}"
            response = self.session.get(url)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Error fetching league: {str(e)}")
            raise
    
    def get_rosters(self, league_id):
        """Get all rosters in league"""
        try:
            url = f"{BASE_URL}/league/{league_id}/rosters"
            response = self.session.get(url)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Error fetching rosters: {str(e)}")
            raise
    
    def get_matchups(self, league_id, week):
        """Get matchups for a week"""
        try:
            url = f"{BASE_URL}/league/{league_id}/matchups/{week}"
            response = self.session.get(url)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Error fetching matchups: {str(e)}")
            raise
    
    def get_players(self):
        """Get all NFL players"""
        try:
            url = f"{BASE_URL}/players/nfl"
            response = self.session.get(url)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Error fetching players: {str(e)}")
            raise
    
    def sync_league(self, league_id):
        """Sync entire league data to database"""
        try:
            # Get league info
            league_data = self.get_league(league_id)
            
            # Create or update league in DB
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
            
            # Get rosters
            rosters = self.get_rosters(league_id)
            for roster in rosters:
                roster_id = str(uuid.uuid4())
                existing = db_session.query(Roster).filter_by(
                    league_id=league_id,
                    team_id=str(roster['roster_id'])
                ).first()
                
                if not existing:
                    new_roster = Roster(
                        id=roster_id,
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
                else:
                    existing.team_name = roster.get('display_name', existing.team_name)
                    existing.players = roster.get('players', [])
                    existing.wins = roster.get('wins', 0)
                    existing.losses = roster.get('losses', 0)
                    existing.points_for = roster.get('points_for', 0)
                    existing.points_against = roster.get('points_against', 0)
            
            db_session.commit()
            
            # Get current week matchups (assuming week 1-18)
            try:
                current_week = league_data.get('settings', {}).get('leg', 1)
                matchups = self.get_matchups(league_id, current_week)
                
                for matchup in matchups:
                    matchup_id = str(uuid.uuid4())
                    existing_matchup = db_session.query(Matchup).filter_by(
                        league_id=league_id,
                        week=current_week,
                        matchup_id=str(matchup.get('matchup_id'))
                    ).first()
                    
                    if not existing_matchup:
                        new_matchup = Matchup(
                            id=matchup_id,
                            league_id=league_id,
                            week=current_week,
                            matchup_id=str(matchup.get('matchup_id')),
                            team_1_id=str(matchup.get('roster_id')),
                            team_1_score=matchup.get('points', 0),
                            team_2_id=str(matchup.get('matchup_id')),  # Placeholder
                            created_at=datetime.utcnow()
                        )
                        db_session.add(new_matchup)
                
                db_session.commit()
            except Exception as e:
                logger.warning(f"Could not sync matchups: {str(e)}")
            
            logger.info(f"Successfully synced Sleeper league {league_id}")
            
            return {
                "status": "synced",
                "league_id": league_id,
                "rosters": len(rosters),
                "matchups": "synced"
            }
        
        except Exception as e:
            logger.error(f"Error syncing league: {str(e)}")
            raise
