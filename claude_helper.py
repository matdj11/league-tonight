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

def generate_recap(league_id, week):
    try:
        client = anthropic.Anthropic(api_key=os.getenv('CLAUDE_API_KEY'))
        
        league = db_session.query(League).filter_by(league_id=league_id).first()
        rosters = db_session.query(Roster).filter_by(league_id=league_id).all()
        
        if not rosters:
            return "<h2>No roster data yet</h2><p>Sync your league first to generate a real recap.</p>"
        
        standings_text = "\n".join([
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
        
        recap_html = None
        for block in message.content:
            if hasattr(block, "text"):
                recap_html = block.text
                break
        if not recap_html:
            recap_html = "<h2>No text content returned</h2>"
        logger.info(f"Generated Claude recap for league {league_id}")
        return recap_html
    
    except Exception as e:
        logger.error(f"Error generating recap with Claude: {str(e)}")
        return f"<h2>Recap generation failed</h2><p>Error: {str(e)}</p>"