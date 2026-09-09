import requests
import logging
import os
import time
from datetime import date

logger = logging.getLogger(__name__)

BASE_URL = "https://api.fantasypros.com/public/v2/json"
POSITIONS = ["QB", "RB", "WR", "TE", "DST", "K"]

SEASON_START = date(2026, 9, 9)

_cache = None
_cache_time = 0
CACHE_TTL = 6 * 3600  # 6 hours - projections don't need to refresh more often than this

_last_attempt_time = 0
RETRY_COOLDOWN = 15 * 60  # don't hammer the API again for 15 min after a failed attempt

REQUEST_DELAY = 1.5  # seconds between each position's request, to avoid tripping their rate limit


def get_current_nfl_week():
    today = date.today()
    if today < SEASON_START:
        return 1
    delta_days = (today - SEASON_START).days
    week = (delta_days // 7) + 1
    return max(1, min(week, 18))


def _fetch_position_projections(position, season=2026, week=None):
    api_key = os.getenv("FANTASYPROS_API_KEY")
    if not api_key:
        logger.warning("FANTASYPROS_API_KEY not set, skipping projections")
        return []
    try:
        url = f"{BASE_URL}/nfl/{season}/projections"
        params = {"position": position}
        if week:
            params["week"] = week
        headers = {"x-api-key": api_key}
        response = requests.get(url, headers=headers, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        return data.get("players", [])
    except Exception as e:
        logger.warning(f"Could not fetch FantasyPros {position} projections: {str(e)}")
        return []


def _build_projection_map(season=2026, week=None):
    global _cache, _cache_time, _last_attempt_time
    now = time.time()

    if _cache is not None and (now - _cache_time) < CACHE_TTL:
        return _cache

    if (now - _last_attempt_time) < RETRY_COOLDOWN:
        logger.info("Skipping FantasyPros fetch, still in cooldown after a recent failure/rate limit")
        return _cache if _cache is not None else {}

    _last_attempt_time = now

    if week is None:
        week = get_current_nfl_week()

    projections = {}
    hit_rate_limit = False

    for i, position in enumerate(POSITIONS):
        if i > 0:
            time.sleep(REQUEST_DELAY)

        players = _fetch_position_projections(position, season=season, week=week)
        if not players:
            hit_rate_limit = True

        for p in players:
            name = p.get("name")
            stats = p.get("stats", {})
            pts = stats.get("points_ppr")
            if pts is None:
                pts = stats.get("points")
            if name and pts is not None:
                projections[name.lower().strip()] = round(pts, 1)

    if projections:
        _cache = projections
        _cache_time = now
    elif hit_rate_limit and _cache is not None:
        # Keep serving the stale cache rather than nothing, since a fresh
        # fetch failed entirely (likely rate limited)
        logger.info("Fresh fetch failed, continuing to serve stale cached projections")

    return _cache if _cache is not None else {}


def get_projected_points_for_names(player_names, season=2026, week=None):
    """Return dict of player_name (as given) -> projected points (float) or None.
    Note: FantasyPros' free tier only exposes roughly the top 10 players per
    position, so bench-level or lesser-known players often won't have a value -
    that's a real limitation of the free tier, not a bug."""
    if not player_names:
        return {}
    proj_map = _build_projection_map(season=season, week=week)
    results = {}
    for name in player_names:
        key = name.lower().strip()
        results[name] = proj_map.get(key)
    return results


def build_projection_notes(projections):
    notes = []
    for name, points in projections.items():
        if points is not None:
            notes.append(f"{name}: {points} projected points")
    return notes


def get_weekly_projections(season=2026, week=None, position=None):
    """Raw single-position fetch, used by the debug endpoint."""
    api_key = os.getenv("FANTASYPROS_API_KEY")
    if not api_key:
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
