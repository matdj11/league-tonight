import requests
import logging
import os
from datetime import datetime
from database import db_session, League, Roster, Matchup
import uuid

logger = logging.getLogger(__name__)

BASE_URL = "https://fantasy.espn.com/apis/v3/games/ffl"

class ESPNClient:
    def __init__(self):
        self.session = requests.Session()
        self.s2 = os.getenv('ESPN_S2')
        self.swid = os.getenv('ESPN_SWID')
        
        # Set cookies for authenticated requests
        if self.s2 and self.swid:
            self.session.cookies.set('espn_s2', self.s2)
            self.session.cookies.set('SWID', self.swid)
    
    def get_league(self, league_id, season=2024):
        """Get league info"""
        try:
            url = f"{BASE_URL}/seasons/{season}/segments/0/leagues/{league_id}"
            params = {
                'view': ['mTeam', 'mRoster', 'mSettings']
            }
            response = self.session.get(url, params=params)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Error fetching ESPN league: {str(e)}")
            raise
    
    def get_teams(self, league_id, season=2024):
        """Get all teams in league"""
        try:
            league = self.get_league(league_id, season)
            return league.get('teams', [])
        except Exception as e:
            logger.error(f"Error fetching ESPN teams: {str(e)}")
            raise
    
    def sync_league(self, league_id, season=2024):
        """Sync ESPN league data to database"""
        try:
            # Get league info
            league_data = self.get_league(league_id, season)
            
            # Create or update league
            league = db_session.query(League).filter_by(league_id=league_id).first()
            if not league:
                league = League(
                    id=str(uuid.uuid4()),
                    league_id=league_id,
                    name=league_data.get('name', 'Unknown'),
                    platform='espn',
                    settings=league_data.get('settings', {})
                )
                db_session.add(league)
            else:
                league.name = league_data.get('name', league.name)
                league.settings = league_data.get('settings', {})
            
            db_session.commit()
            
            # Get and store teams/rosters
            teams = league_data.get('teams', [])
            for team in teams:
                team_id = str(team.get('id'))
                existing = db_session.query(Roster).filter_by(
                    league_id=league_id,
                    team_id=team_id
                ).first()
                
                roster_data = team.get('roster', {})
                entries = roster_data.get('entries', [])
                players = [str(entry.get('playerId')) for entry in entries]
                
                if not existing:
                    new_roster = Roster(
                        id=str(uuid.uuid4()),
                        league_id=league_id,
                        team_id=team_id,
                        team_name=team.get('location', 'Unknown') + ' ' + team.get('nickname', ''),
                        owner_name=team.get('owner'),
                        players=players,
                        wins=team.get('wins', 0),
                        losses=team.get('losses', 0),
                        points_for=team.get('points_for', 0),
                        points_against=team.get('points_against', 0)
                    )
                    db_session.add(new_roster)
                else:
                    existing.team_name = team.get('location', '') + ' ' + team.get('nickname', '')
                    existing.players = players
                    existing.wins = team.get('wins', 0)
                    existing.losses = team.get('losses', 0)
                    existing.points_for = team.get('points_for', 0)
                    existing.points_against = team.get('points_against', 0)
            
            db_session.commit()
            
            logger.info(f"Successfully synced ESPN league {league_id}")
            
            return {
                "status": "synced",
                "league_id": league_id,
                "rosters": len(teams)
            }
        
        except Exception as e:
            logger.error(f"Error syncing ESPN league: {str(e)}")
            raise
