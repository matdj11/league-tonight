import requests
import logging

logger = logging.getLogger(__name__)

SCOREBOARD_URL = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard"

ESPN_ABBR_FIX = {
    "WSH": "WAS",
    "JAC": "JAX",
    "LA": "LAR",
}

def get_weather_by_team():
    """Fetch this week's NFL scoreboard from ESPN and return a dict of
    team_abbr -> weather summary string. ESPN only attaches weather data
    to games where it's actually relevant (outdoor stadiums with real
    conditions) - domes and non-issues are simply absent, so no game
    appearing here means weather isn't a factor for that team this week."""
    try:
        response = requests.get(SCOREBOARD_URL, timeout=10)
        response.raise_for_status()
        data = response.json()

        weather_by_team = {}
        for event in data.get("events", []):
            weather = event.get("weather")
            if not weather:
                continue

            temp = weather.get("temperature")
            condition = weather.get("displayValue", "")
            summary_parts = []
            if temp is not None:
                summary_parts.append(f"{temp}\u00b0F")
            if condition:
                summary_parts.append(condition)
            if not summary_parts:
                continue
            summary = ", ".join(summary_parts)

            for comp in event.get("competitions", []):
                for competitor in comp.get("competitors", []):
                    team_info = competitor.get("team", {})
                    abbr = team_info.get("abbreviation", "").upper()
                    abbr = ESPN_ABBR_FIX.get(abbr, abbr)
                    if abbr:
                        weather_by_team[abbr] = summary

        return weather_by_team
    except Exception as e:
        logger.warning(f"Could not fetch weather data: {str(e)}")
        return {}


def build_weather_notes(name_to_team, weather_by_team):
    """Given resolved player_name -> team_abbr and team_abbr -> weather
    summary, return a list of human-readable weather notes only for
    players whose team actually has relevant weather this week."""
    notes = []
    for name, team in name_to_team.items():
        team_upper = (team or "").upper()
        if team_upper in weather_by_team:
            notes.append(f"{name} ({team_upper}): {weather_by_team[team_upper]}")
    return notes

NEWS_URL = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/news?limit=50"

def get_relevant_news(player_names):
    """Fetch recent NFL news headlines from ESPN's public feed and return
    only the ones that mention a player from the given roster. This is a
    real, live check - no manual uploading, no guessing."""
    if not player_names:
        return []
    try:
        response = requests.get(NEWS_URL, timeout=10)
        response.raise_for_status()
        data = response.json()

        articles = data.get("articles", [])
        relevant = []

        for name in player_names:
            name_lower = name.lower()
            for article in articles:
                headline = article.get("headline", "")
                description = article.get("description", "")
                combined = f"{headline} {description}".lower()
                if name_lower in combined:
                    link = ""
                    links = article.get("links", {})
                    if isinstance(links, dict):
                        web = links.get("web", {})
                        if isinstance(web, dict):
                            link = web.get("href", "")
                    relevant.append({
                        "player": name,
                        "headline": headline,
                        "description": description,
                        "link": link
                    })
                    break

        return relevant
    except Exception as e:
        logger.warning(f"Could not fetch news data: {str(e)}")
        return []


def build_news_notes(news_items):
    """Format news items into short text notes for the AI prompt."""
    notes = []
    for item in news_items:
        text = f"{item['player']}: {item['headline']}"
        if item.get("description"):
            text += f" - {item['description']}"
        notes.append(text)
    return notes
