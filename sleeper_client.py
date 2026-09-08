import requests
import logging
import re
from datetime import datetime
from database import db_session, League, Roster
import uuid

logger = logging.getLogger(__name__)

BASE_URL = "https://api.sleeper.app/v1"

NFL_TEAM_BYE_WEEKS = {
    "ARI": 14, "ATL": 11, "BAL": 13, "BUF": 7, "CAR": 5, "CHI": 10,
    "CIN": 6, "CLE": 11, "DAL": 14, "DEN": 10, "DET": 6, "GB": 11,
    "HOU": 8, "IND": 13, "JAX": 7, "KC": 5, "LV": 13, "LAC": 7,
    "LAR": 11, "MIA": 6, "MIN": 6, "NE": 11, "NO": 8, "NYG": 8,
    "NYJ": 13, "PHI": 10, "PIT": 9, "SF": 8, "SEA": 11, "TB": 10,
    "TEN": 9, "WAS": 7
}

def _normalize_name(name):
    name = name.lower().strip()
    name = re.sub(r"[.\']", "", name)
    name = re.sub(r"\s+(jr|sr|ii|iii|iv)$", "", name)
    name = re.sub(r"\s+", " ", name)
    return name

class SleeperClient:
    def __init__(self):
        self.session = requests.Session()
        self._players_cache = None
        self._name_to_team_cache = None
    
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
        if self._players_cache is not None:
            return self._players_cache
        try:
            url = f"{BASE_URL}/players/nfl"
            response = self.session.get(url)
            response.raise_for_status()
            self._players_cache = response.json()
            return self._players_cache
        except Exception as e:
            logger.error(f"Error fetching players: {str(e)}")
            raise

    def _build_name_to_team_index(self):
        if self._name_to_team_cache is not None:
            return self._name_to_team_cache

        players = self.get_players_map()
        index = {}
        for player_id, info in players.items():
            full_name = info.get("full_name")
            team = info.get("team")
            if full_name and team:
                key = _normalize_name(full_name)
                index[key] = team

        self._name_to_team_cache = index
        return index

    def resolve_team_for_name(self, name):
        try:
            index = self._build_name_to_team_index()
            key = _normalize_name(name)
            return index.get(key)
        except Exception as e:
            logger.warning(f"Could not resolve team for '{name}': {str(e)}")
            return None

    def resolve_teams_for_names(self, player_names):
        """Resolve each name to (team_abbr or None) via Sleeper's database.
        Returns (resolved: dict name->team, unresolved: list of names)."""
        resolved = {}
        unresolved = []
        for name in player_names:
            team = self.resolve_team_for_name(name)
            if team:
                resolved[name] = team
            else:
                unresolved.append(name)
        return resolved, unresolved

    
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


def build_bye_conflicts_from_team_map(name_to_team):
    """Given a dict of player_name -> NFL team abbreviation, return a list
    of human-readable conflict strings for players sharing a bye week."""
    team_groups = {}
    for name, team in name_to_team.items():
        if team and team.upper() in NFL_TEAM_BYE_WEEKS:
            team_groups.setdefault(team.upper(), []).append(name)

    conflicts = []
    for team, names in team_groups.items():
        if len(names) >= 2:
            week = NFL_TEAM_BYE_WEEKS[team]
            conflicts.append(f"{', '.join(names)} are all on {team} and share a Week {week} bye")

    return conflicts
