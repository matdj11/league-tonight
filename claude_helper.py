import os
import json
import logging

logger = logging.getLogger(__name__)

# Import inside function to avoid initialization errors
def get_client():
    import anthropic
    return anthropic.Anthropic(api_key=os.getenv('CLAUDE_API_KEY'))

RECAP_PROMPT = """You are a sports analyst creating an entertaining weekly fantasy football recap for a league.

Here's the league data from this week:

MATCHUPS:
{matchups}

STANDINGS:
{standings}

Your job is to create an entertaining recap that includes:

1. **Biggest Upset**: The most surprising result
2. **Closest Game**: The matchup with the smallest margin
3. **Blowout of the Week**: The biggest margin of victory
4. **Power Rankings**: Rank all teams 1-{num_teams}
5. **Punishment Watch**: Which team is in last place and their odds of staying there
6. **AI Hot Take**: One spicy opinion about the week

Keep the tone energetic and fun. Reference team names and actual scores. Use emojis sparingly but effectively.

Format your response as a JSON object with these keys:
- biggest_upset (string with team names and score)
- closest_game (string with team names and score)
- blowout (string with team names and score)
- power_rankings (list of {"rank": 1, "team": "name", "trend": "up/down/flat"})
- punishment_watch (string with team name and odds)
- hot_take (string with opinion)

Respond ONLY with valid JSON, no additional text."""

BRIEFING_PROMPT = """You are a personal fantasy football coach. Create a brief morning briefing for this manager.

MANAGER'S ROSTER:
{roster}

LEAGUE DATA:
{league_data}

INJURIES & WEATHER:
{injuries_and_weather}

Create 3-5 key insights that affect this manager's team this week. Each insight should:
- Be specific to their roster
- Include actionable advice
- Have a source (injury report, weather data, waiver analysis, etc.)

Format as JSON:
{{
  "insights": [
    {{
      "text": "Brief insight about their team",
      "action": "What they should do about it",
      "source": "Where this comes from (FantasyPros, NOAA, Sleeper, etc.)",
      "source_url": "Link to source if available"
    }}
  ],
  "lineup_warning": "Any major warning about current lineup, or null"
}}

Respond ONLY with valid JSON."""

def generate_recap(league, week):
    """Generate weekly recap with Claude"""
    try:
        # Fetch matchup data
        matchups = db_session.query(Matchup).filter_by(
            league_id=league.league_id,
            week=week
        ).all()
        
        # Format matchups for prompt
        matchup_text = ""
        standings_data = {}
        for matchup in matchups:
            matchup_text += f"\n{matchup.team_1_name} ({matchup.team_1_score}) vs {matchup.team_2_name} ({matchup.team_2_score})"
            if matchup.winner:
                matchup_text += f" - Winner: {matchup.winner}"
            
            # Build standings
            if matchup.team_1_name not in standings_data:
                standings_data[matchup.team_1_name] = {"wins": 0, "losses": 0, "points": 0}
            if matchup.team_2_name not in standings_data:
                standings_data[matchup.team_2_name] = {"wins": 0, "losses": 0, "points": 0}
            
            standings_data[matchup.team_1_name]["points"] = matchup.team_1_score
            standings_data[matchup.team_2_name]["points"] = matchup.team_2_score
        
        standings_text = "\n".join([
            f"{name}: {data['wins']}-{data['losses']} ({data['points']} pts)"
            for name, data in standings_data.items()
        ])
        
        # Call Claude
        prompt = RECAP_PROMPT.format(
            matchups=matchup_text,
            standings=standings_text,
            num_teams=len(standings_data)
        )
        
        message = client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=1024,
            messages=[
                {"role": "user", "content": prompt}
            ]
        )
        
        # Parse response
        response_text = message.content[0].text
        recap_data = json.loads(response_text)
        
        # Format as HTML
        recap_html = format_recap_html(recap_data, league.name)
        
        logger.info(f"Generated recap for league {league.league_id}")
        return recap_html
    
    except Exception as e:
        logger.error(f"Error generating recap: {str(e)}")
        raise

def generate_briefing(roster, league_id):
    """Generate personalized briefing with Claude"""
    try:
        # Get league and injury/weather data
        league = db_session.query(League).filter_by(league_id=league_id).first()
        
        injuries = db_session.query(PlayerInjury).all()
        weather = db_session.query(GameWeather).all()
        
        injuries_text = "\n".join([
            f"{i.player_name} ({i.team}): {i.status} - {i.injury_description}"
            for i in injuries[:10]  # Top 10 injuries
        ])
        
        # Format roster
        roster_text = f"Team: {roster.team_name}\nPlayers: {', '.join(roster.players[:5])}..."
        
        # Call Claude
        prompt = BRIEFING_PROMPT.format(
            roster=roster_text,
            league_data=f"League: {league.name}",
            injuries_and_weather=injuries_text or "No major injuries"
        )
        
        message = client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=512,
            messages=[
                {"role": "user", "content": prompt}
            ]
        )
        
        # Parse response
        response_text = message.content[0].text
        briefing_data = json.loads(response_text)
        
        logger.info(f"Generated briefing for {roster.team_name}")
        return briefing_data
    
    except Exception as e:
        logger.error(f"Error generating briefing: {str(e)}")
        raise

def format_recap_html(recap_data, league_name):
    """Format recap data as HTML"""
    html = f"""
    <div class="recap-container">
        <h1>{league_name} — League Tonight</h1>
        
        <div class="recap-section">
            <h2>🚨 Biggest Upset</h2>
            <p>{recap_data.get('biggest_upset', 'N/A')}</p>
        </div>
        
        <div class="recap-section">
            <h2>📌 Closest Game</h2>
            <p>{recap_data.get('closest_game', 'N/A')}</p>
        </div>
        
        <div class="recap-section">
            <h2>💥 Blowout of the Week</h2>
            <p>{recap_data.get('blowout', 'N/A')}</p>
        </div>
        
        <div class="recap-section">
            <h2>🏆 Power Rankings</h2>
            <ol>
    """
    
    for ranking in recap_data.get('power_rankings', []):
        trend_emoji = "📈" if ranking.get('trend') == 'up' else "📉" if ranking.get('trend') == 'down' else "➡️"
        html += f"<li>{ranking.get('team', 'N/A')} {trend_emoji}</li>"
    
    html += f"""
            </ol>
        </div>
        
        <div class="recap-section">
            <h2>⚠️ Punishment Watch</h2>
            <p>{recap_data.get('punishment_watch', 'N/A')}</p>
        </div>
        
        <div class="recap-section">
            <h2>🔥 Hot Take</h2>
            <p>{recap_data.get('hot_take', 'N/A')}</p>
        </div>
    </div>
    """
    
    return html
