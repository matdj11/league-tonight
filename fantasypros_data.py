import requests
import logging
import os

logger = logging.getLogger(__name__)

BASE_URL = "https://api.fantasypros.com/public/v2/json"

def get_weekly_projections(season=2026, week=None, position=None):
    api_key = os.getenv("FANTASYPROS_API_KEY")
    if not api_key:
        logger.warning("FANTASYPROS_API_KEY not set, skipping projections")
        return {}
    try:
        url = f"{BASE_URL}/nfl/{season}/projections"
        params = {}
        if week:
            params["week"] = week
        if position:
            params["position"] = position
        headers = {"x-api-key": api_key}
        response = requests.get(url, headers=headers, params=params, timeout=10)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logger.warning(f"Could not fetch FantasyPros projections: {str(e)}")
        return {}

def _build_projection_map(data):
    """Build a dict of normalized player name -> projected points."""
    projections = {}
    players = data.get("players", []) if isinstance(data, dict) else []
    for p in players:
        name = p.get("player_name")
        if not name:
            continue
        pts = None
        for key in ("fpts", "points", "projected_points", "proj_pts"):
            if key in p and p[key] is not None:
                pts = p[key]
                break
        if pts is not None:
            projections[name.lower().strip()] = pts
    return projections

def get_projected_points_for_names(player_names, season=2026, week=None):
    """Return dict of player_name (as given) -> projected points (float) or None."""
    if not player_names:
        return {}
    data = get_weekly_projections(season=season, week=week)
    proj_map = _build_projection_map(data)
    results = {}
    for name in player_names:
        key = name.lower().strip()
        results[name] = proj_map.get(key)
    return results

def build_projection_notes(projections):
    """Format {name: points} into short text notes for the AI prompt.
    Only includes players that actually have a real projection."""
    notes = []
    for name, points in projections.items():
        if points is not None:
            notes.append(f"{name}: {points} projected points")
    return notes
