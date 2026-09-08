import anthropic
import os
import json
import logging
from database import db_session, League, Roster

logger = logging.getLogger(__name__)

RECAP_PROMPT = """You are a sports analyst creating an entertaining weekly fantasy football recap for a league called "{league_name}".

Here are the current standings and rosters:

{standings}

Create a fun, energetic recap that includes:
1. A power ranking of all teams (1 = best) based on wins/losses and points
2. A callout for the team with the most points (call them "on fire")
3. A callout for the team with the fewest points (a light, funny "punishment watch" tone, not mean)
4. One spicy AI "hot take" about the league this week

Keep it fun and conversational, like a sports radio host. Reference actual team names.

Respond in HTML format using <h2> for section headers and <p> for text. Do not include <html>, <head>, or <body> tags - just the inner content."""

DRAFT_PROMPT = """You are a sports analyst creating a fun, entertaining recap of a fantasy football draft for a league called "{league_name}".

Here are the draft picks in order:

{draft_picks}

Create an entertaining draft recap that includes:
1. Best value pick (a player picked later than expected, use your judgment on ADP if known, otherwise just pick a fun one)
2. Riskiest/boldest pick of the draft
3. A "best draft" call-out for one team, with a short reason
4. One spicy AI hot take about how the draft went overall

Keep it fun and conversational like a sports radio host. Reference actual team names and player names.

Respond in HTML format using <h2> for section headers and <p> for text. Do not include <html>, <head>, or <body> tags - just the inner content."""

BRIEFING_PROMPT = """You are a personal fantasy football coach giving a quick morning briefing to one manager in the league "{league_name}".

Manager's team: {team_name}
Manager's roster: {roster_players}

CONFIRMED BYE WEEK CONFLICTS (computed from real 2026 NFL schedule, not a guess):
{bye_conflicts}

CONFIRMED WEATHER FOR THIS WEEK'S GAMES (real data, only present when weather is actually a relevant factor - if empty, weather is not a concern for anyone on this roster and should not be mentioned at all):
{weather_notes}

RECENT NEWS RELEVANT TO THIS ROSTER (real headlines pulled live, only present when a player on this roster is actually mentioned - if empty, there is no relevant news right now):
{news_notes}

Give this manager 3 short, personalized insights about their team, prioritizing any real news above (injuries, roster moves, etc.) first if present, then roster construction, depth at each position, and confirmed weather where it applies. Keep it useful and specific-sounding, not generic filler. Only mention weather or news if they appear in the confirmed sections above - never guess or invent either.

For the lineup_warning field: if there are confirmed bye week conflicts listed above, state them directly and specifically (name the players and the week). If there are none, set lineup_warning to null. Do NOT guess at or invent bye week conflicts that are not in the confirmed list above.

Respond ONLY as a JSON object in this exact shape, no other text:
{{
  "insights": [
    {{"text": "short insight text", "source": "short source label like 'Roster Analysis' or 'Weather'"}},
    {{"text": "short insight text", "source": "short source label"}},
    {{"text": "short insight text", "source": "short source label"}}
  ],
  "lineup_warning": "specific sentence naming the players and bye week if a confirmed conflict exists, otherwise null"
}}"""

SEASON_PREVIEW_PROMPT = """You are a sports analyst creating a season preview for a fantasy football league called "{league_name}" before games have started.

Here are the teams and their rosters:

{teams}

Since no games have been played yet, create a season preview based on roster construction and projections instead of actual results. Include:
1. Projected strongest team ("Team to Beat") with a short reason
2. Projected weakest team ("Rebuild Watch") with a short reason, keep it light and funny not mean
3. A power ranking of all teams 1 to N based on roster strength (your best judgment)
4. One spicy AI "bold prediction" for the season

Respond ONLY as a JSON object in this exact shape, no other text:
{{
  "team_to_beat": "short text naming a team and why",
  "rebuild_watch": "short text naming a team and why, light and funny",
  "power_rankings": [
    {{"rank": 1, "team": "team name"}},
    {{"rank": 2, "team": "team name"}}
  ],
  "bold_prediction": "one spicy prediction for the season"
}}"""

def _extract_text(message):
    text = None
    for block in message.content:
        if hasattr(block, "text"):
            text = block.text
            break
    if not text:
        text = "<h2>No text content returned</h2>"
    return text

def _parse_json_safely(raw_text, fallback):
    """Strip markdown code fences if present, then parse JSON.
    Returns fallback (a callable taking raw_text, or a dict) on failure."""
    cleaned = raw_text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("```")[1] if "```" in cleaned[3:] else cleaned[3:]
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:]
        cleaned = cleaned.rsplit("```", 1)[0] if "```" in cleaned else cleaned
    cleaned = cleaned.strip()
    try:
        return json.loads(cleaned)
    except Exception:
        if callable(fallback):
            return fallback(raw_text)
        return fallback

def generate_recap(league_id, week):
    try:
        client = anthropic.Anthropic(api_key=os.getenv("CLAUDE_API_KEY"))

        league = db_session.query(League).filter_by(league_id=league_id).first()
        rosters = db_session.query(Roster).filter_by(league_id=league_id).all()

        if not rosters:
            return "<h2>No roster data yet</h2><p>Sync your league first to generate a real recap.</p>"

        standings_text = chr(10).join([
            f"{r.team_name}: {r.wins}-{r.losses}, {r.points_for} points for"
            for r in rosters
        ])

        prompt = RECAP_PROMPT.format(
            league_name=league.name,
            standings=standings_text
        )

        message = client.messages.create(
            model="claude-sonnet-5",
            max_tokens=1024,
            messages=[
                {"role": "user", "content": prompt}
            ]
        )

        recap_html = _extract_text(message)
        logger.info(f"Generated Claude recap for league {league_id}")
        return recap_html

    except Exception as e:
        logger.error(f"Error generating recap with Claude: {str(e)}")
        return f"<h2>Recap generation failed</h2><p>Error: {str(e)}</p>"

def generate_draft_recap(league_id, draft_picks_text, league_name):
    try:
        client = anthropic.Anthropic(api_key=os.getenv("CLAUDE_API_KEY"))

        prompt = DRAFT_PROMPT.format(
            league_name=league_name,
            draft_picks=draft_picks_text
        )

        message = client.messages.create(
            model="claude-sonnet-5",
            max_tokens=1024,
            messages=[
                {"role": "user", "content": prompt}
            ]
        )

        recap_html = _extract_text(message)
        logger.info(f"Generated Claude draft recap for league {league_id}")
        return recap_html

    except Exception as e:
        logger.error(f"Error generating draft recap with Claude: {str(e)}")
        return f"<h2>Draft recap generation failed</h2><p>Error: {str(e)}</p>"

def generate_briefing(league_id, team_id, bye_conflicts=None, weather_notes=None, news_notes=None):
    try:
        client = anthropic.Anthropic(api_key=os.getenv("CLAUDE_API_KEY"))

        league = db_session.query(League).filter_by(league_id=league_id).first()
        roster = db_session.query(Roster).filter_by(league_id=league_id, team_id=team_id).first()

        if not roster:
            return {"insights": [], "lineup_warning": "No roster found for this team."}

        roster_list = roster.players if roster.players else []
        roster_players = ", ".join(roster_list[:15]) if roster_list else "No players on roster yet"

        bye_conflicts_text = chr(10).join(bye_conflicts) if bye_conflicts else "None found."
        weather_notes_text = chr(10).join(weather_notes) if weather_notes else "None found."
        news_notes_text = chr(10).join(news_notes) if news_notes else "None found."

        prompt = BRIEFING_PROMPT.format(
            league_name=league.name if league else "your league",
            team_name=roster.team_name,
            roster_players=roster_players,
            bye_conflicts=bye_conflicts_text,
            weather_notes=weather_notes_text,
            news_notes=news_notes_text
        )

        message = client.messages.create(
            model="claude-sonnet-5",
            max_tokens=1024,
            messages=[
                {"role": "user", "content": prompt}
            ]
        )

        raw_text = _extract_text(message)

        def _briefing_fallback(text):
            return {
                "insights": [{"text": "Briefing couldn't be parsed this time. Try generating again.", "source": "System"}],
                "lineup_warning": None
            }

        briefing_data = _parse_json_safely(raw_text, _briefing_fallback)

        logger.info(f"Generated Claude briefing for team {team_id} in league {league_id}")
        return briefing_data

    except Exception as e:
        logger.error(f"Error generating briefing with Claude: {str(e)}")
        return {"insights": [{"text": f"Briefing generation failed: {str(e)}", "source": "Error"}], "lineup_warning": None}

TEAM_LOOKUP_PROMPT = """You are an NFL roster expert. For each player name listed below, identify their current 2026 NFL team using the standard 2-3 letter abbreviation (e.g. SF, KC, NYJ, GB).

Player names:
{names}

Respond ONLY as a JSON object mapping each exact player name (as given) to their team abbreviation. If you are not confident about a player, map them to null. No other text.

Example format:
{{
  "Christian McCaffrey": "SF",
  "Some Unknown Player": null
}}"""

LINEUP_PROMPT = """You are a fantasy football coach setting an optimal starting lineup for this week.

Team: {team_name}
Full roster: {roster_players}

CONFIRMED WEATHER FOR THIS WEEK'S GAMES (real data, only present when weather is actually a relevant factor - if empty, weather is not a concern and should not affect your reasoning):
{weather_notes}

RECENT NEWS RELEVANT TO THIS ROSTER (real headlines pulled live, only present when a player on this roster is actually mentioned - if empty, there is no relevant news right now):
{news_notes}

Assume a standard lineup: 1 QB, 2 RB, 2 WR, 1 TE, 1 FLEX (RB/WR/TE), 1 DST, 1 K. If the roster doesn't clearly contain enough players for a slot, leave that slot's player as null.

Pick the strongest starters from the roster for each slot based on your knowledge of these players. Factor in confirmed weather and news above where relevant (e.g. if news says a player is out or a backup is now starting, that should change your pick; bad weather can hurt passing games and favor run-heavy game plans). Never invent weather or news that isn't in the confirmed lists.

For each slot, write a short one-sentence "reason" explaining the pick. If there's another player on the roster at the same position who could have started instead (a bench option at that position), explicitly compare the two and explain why you chose the starter over them, referencing any confirmed news/weather/matchup reasoning. If there's no real alternative at that position, just explain why the starter is a solid play.

Respond ONLY as a JSON object in this exact shape, no other text:
{{
  "lineup": [
    {{"slot": "QB", "player": "player name or null", "reason": "short sentence, compares to bench option if one exists at this position"}},
    {{"slot": "RB", "player": "player name or null", "reason": "short sentence"}},
    {{"slot": "RB", "player": "player name or null", "reason": "short sentence"}},
    {{"slot": "WR", "player": "player name or null", "reason": "short sentence"}},
    {{"slot": "WR", "player": "player name or null", "reason": "short sentence"}},
    {{"slot": "TE", "player": "player name or null", "reason": "short sentence"}},
    {{"slot": "FLEX", "player": "player name or null", "reason": "short sentence"}},
    {{"slot": "DST", "player": "player name or null", "reason": "short sentence"}},
    {{"slot": "K", "player": "player name or null", "reason": "short sentence"}}
  ],
  "flex_reasoning": "one short sentence on why that FLEX pick over other flex-eligible bench players"
}}"""

def ai_resolve_team_for_names(names):
    """Ask Claude to identify NFL teams for player names Sleeper's database
    couldn't match (nicknames, typos, etc). Returns dict name->team or {}."""
    if not names:
        return {}
    try:
        client = anthropic.Anthropic(api_key=os.getenv("CLAUDE_API_KEY"))

        prompt = TEAM_LOOKUP_PROMPT.format(names=", ".join(names))

        message = client.messages.create(
            model="claude-sonnet-5",
            max_tokens=512,
            messages=[
                {"role": "user", "content": prompt}
            ]
        )

        raw_text = _extract_text(message)
        result = _parse_json_safely(raw_text, {})
        return {k: v for k, v in result.items() if v}

    except Exception as e:
        logger.warning(f"AI team resolution failed: {str(e)}")
        return {}

def generate_lineup_suggestion(league_id, team_id, weather_notes=None, news_notes=None):
    try:
        client = anthropic.Anthropic(api_key=os.getenv("CLAUDE_API_KEY"))

        roster = db_session.query(Roster).filter_by(league_id=league_id, team_id=team_id).first()
        if not roster or not roster.players:
            return {"error": "No roster data yet"}

        roster_players = ", ".join(roster.players)
        weather_notes_text = chr(10).join(weather_notes) if weather_notes else "None found."
        news_notes_text = chr(10).join(news_notes) if news_notes else "None found."

        prompt = LINEUP_PROMPT.format(
            team_name=roster.team_name,
            roster_players=roster_players,
            weather_notes=weather_notes_text,
            news_notes=news_notes_text
        )

        message = client.messages.create(
            model="claude-sonnet-5",
            max_tokens=2048,
            messages=[
                {"role": "user", "content": prompt}
            ]
        )

        raw_text = _extract_text(message)

        def _lineup_fallback(text):
            return {"lineup": [], "flex_reasoning": "Lineup couldn't be parsed this time. Try generating again."}

        lineup_data = _parse_json_safely(raw_text, _lineup_fallback)

        logger.info(f"Generated Claude lineup suggestion for team {team_id} in league {league_id}")
        return lineup_data

    except Exception as e:
        logger.error(f"Error generating lineup suggestion with Claude: {str(e)}")
        return {"error": str(e)}

def generate_season_preview(league_id):
    try:
        client = anthropic.Anthropic(api_key=os.getenv("CLAUDE_API_KEY"))

        league = db_session.query(League).filter_by(league_id=league_id).first()
        rosters = db_session.query(Roster).filter_by(league_id=league_id).all()

        if not rosters:
            return {"error": "No roster data yet"}

        teams_text = chr(10).join([
            f"{r.team_name}: {', '.join(r.players[:10]) if r.players else 'No players listed'}"
            for r in rosters
        ])

        prompt = SEASON_PREVIEW_PROMPT.format(
            league_name=league.name if league else "the league",
            teams=teams_text
        )

        message = client.messages.create(
            model="claude-sonnet-5",
            max_tokens=1536,
            messages=[
                {"role": "user", "content": prompt}
            ]
        )

        raw_text = _extract_text(message)

        def _preview_fallback(text):
            return {
                "team_to_beat": "",
                "rebuild_watch": "",
                "power_rankings": [],
                "bold_prediction": "Preview couldn't be parsed this time. Try generating again."
            }

        preview_data = _parse_json_safely(raw_text, _preview_fallback)

        logger.info(f"Generated Claude season preview for league {league_id}")
        return preview_data

    except Exception as e:
        logger.error(f"Error generating season preview with Claude: {str(e)}")
        return {"error": str(e)}
