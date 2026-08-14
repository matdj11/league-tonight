from flask import Flask, render_template, jsonify, request
from flask_cors import CORS
import os
from dotenv import load_dotenv
import logging

# Load environment variables
load_dotenv()

# Initialize Flask app
app = Flask(__name__)
CORS(app)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Import modules
from database import init_db, db_session, League, Recap, Briefing, User, Roster
from sleeper_client import SleeperClient
from espn_client import ESPNClient
from claude_helper import generate_recap, generate_briefing
from external_data import sync_injuries_and_weather

# Initialize clients
sleeper = SleeperClient()
espn = ESPNClient()

# ============ HEALTH & TEST ENDPOINTS ============

@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "ok"})

@app.route('/api/test-db', methods=['GET'])
def test_db():
    try:
        # Try to query the database
        leagues = db_session.query(League).first()
        return jsonify({"database": "connected", "test": "ok"})
    except Exception as e:
        logger.error(f"DB test failed: {str(e)}")
        return jsonify({"database": "error", "error": str(e)}), 500

@app.route('/api/test-sleeper', methods=['GET'])
def test_sleeper():
    try:
        league_id = os.getenv('SLEEPER_LEAGUE_ID')
        if not league_id:
            return jsonify({"sleeper": "not configured"}), 400
        
        result = sleeper.get_league(league_id)
        return jsonify({"sleeper": "connected", "league": result.get("name")})
    except Exception as e:
        logger.error(f"Sleeper test failed: {str(e)}")
        return jsonify({"sleeper": "error", "error": str(e)}), 500

@app.route('/api/test-espn', methods=['GET'])
def test_espn():
    try:
        league_id = os.getenv('ESPN_LEAGUE_ID')
        if not league_id:
            return jsonify({"espn": "not configured"}), 400
        
        result = espn.get_league(league_id)
        return jsonify({"espn": "connected", "league": result.get("name")})
    except Exception as e:
        logger.error(f"ESPN test failed: {str(e)}")
        return jsonify({"espn": "error", "error": str(e)}), 500

# ============ DATABASE INITIALIZATION ============

@app.route('/api/init-db', methods=['GET', 'POST'])
def init_database():
    try:
        init_db()
        return jsonify({"status": "database initialized"})
    except Exception as e:
        logger.error(f"DB init failed: {str(e)}")
        return jsonify({"status": "error", "error": str(e)}), 500

# ============ LEAGUE SYNC ============

@app.route('/api/league/sync', methods=['POST', 'GET'])
def sync_league():
    try:
        league_id = request.args.get('league_id') or os.getenv('SLEEPER_LEAGUE_ID')
        platform = request.args.get('platform', 'sleeper')
        
        if platform == 'sleeper':
            data = sleeper.sync_league(league_id)
        else:
            data = espn.sync_league(league_id)
        
        return jsonify({
            "status": "sync complete",
            "league_id": league_id,
            "platform": platform,
            "teams": len(data.get("rosters", [])),
            "matchups": len(data.get("matchups", []))
        })
    except Exception as e:
        logger.error(f"League sync failed: {str(e)}")
        return jsonify({"status": "error", "error": str(e)}), 500

# ============ RECAP GENERATION ============

@app.route('/api/recap/generate', methods=['POST', 'GET'])
def generate_recap_endpoint():
    try:
        league_id = request.args.get('league_id') or os.getenv('SLEEPER_LEAGUE_ID')
        week = request.args.get('week', 'current')
        
        # Get league and matchup data from DB
        league = db_session.query(League).filter_by(league_id=league_id).first()
        if not league:
            return jsonify({"status": "league not found"}), 404
        
        # Generate recap with Claude
        recap_content = generate_recap(league, week)
        
        # Store in database
        recap = Recap(
            league_id=league_id,
            week=week,
            content=recap_content,
            status='draft'
        )
        db_session.add(recap)
        db_session.commit()
        
        return jsonify({
            "status": "recap generated",
            "league_id": league_id,
            "week": week,
            "content_preview": recap_content[:200] + "..."
        })
    except Exception as e:
        logger.error(f"Recap generation failed: {str(e)}")
        return jsonify({"status": "error", "error": str(e)}), 500

# ============ RECAP PUBLISHING ============

@app.route('/api/recap/publish', methods=['POST'])
def publish_recap():
    try:
        league_id = request.json.get('league_id')
        week = request.json.get('week', 'current')
        
        recap = db_session.query(Recap).filter_by(
            league_id=league_id,
            week=week
        ).first()
        
        if not recap:
            return jsonify({"status": "recap not found"}), 404
        
        recap.status = 'published'
        db_session.commit()
        
        # Generate shareable link
        shareable_link = f"{request.host_url}recap/{league_id}/{week}"
        
        return jsonify({
            "status": "published",
            "league_id": league_id,
            "week": week,
            "shareable_link": shareable_link
        })
    except Exception as e:
        logger.error(f"Recap publish failed: {str(e)}")
        return jsonify({"status": "error", "error": str(e)}), 500

# ============ BRIEFING ============

@app.route('/api/briefing/generate', methods=['POST', 'GET'])
def generate_briefing_endpoint():
    try:
        league_id = request.args.get('league_id') or os.getenv('SLEEPER_LEAGUE_ID')
        team_id = request.args.get('team_id')
        
        if not team_id:
            return jsonify({"status": "team_id required"}), 400
        
        # Sync injuries/weather
        sync_injuries_and_weather()
        
        # Get roster and generate briefing
        roster = db_session.query(Roster).filter_by(
            league_id=league_id,
            team_id=team_id
        ).first()
        
        if not roster:
            return jsonify({"status": "roster not found"}), 404
        
        briefing_content = generate_briefing(roster, league_id)
        
        # Store briefing
        briefing = Briefing(
            league_id=league_id,
            team_id=team_id,
            content=briefing_content
        )
        db_session.add(briefing)
        db_session.commit()
        
        return jsonify({
            "status": "briefing generated",
            "league_id": league_id,
            "team_id": team_id,
            "briefing": briefing_content
        })
    except Exception as e:
        logger.error(f"Briefing generation failed: {str(e)}")
        return jsonify({"status": "error", "error": str(e)}), 500

# ============ CLAIM TEAM ============

@app.route('/api/claim-team', methods=['POST', 'GET'])
def claim_team():
    try:
        league_id = request.args.get('league_id')
        team_id = request.args.get('team_id')
        user_email = request.args.get('email', 'default@example.com')
        
        if not league_id or not team_id:
            return jsonify({"status": "league_id and team_id required"}), 400
        
        # Create or get user
        user = db_session.query(User).filter_by(email=user_email).first()
        if not user:
            user = User(email=user_email)
            db_session.add(user)
        
        # Link team to user
        user.claimed_teams = f"{league_id}:{team_id}"
        db_session.commit()
        
        return jsonify({
            "status": "team claimed",
            "user": user_email,
            "team_id": team_id,
            "league_id": league_id
        })
    except Exception as e:
        logger.error(f"Claim team failed: {str(e)}")
        return jsonify({"status": "error", "error": str(e)}), 500

# ============ WEB VIEWS ============

@app.route('/dashboard')
def dashboard():
    """Commissioner dashboard"""
    try:
        league_id = request.args.get('league_id') or os.getenv('SLEEPER_LEAGUE_ID')
        league = db_session.query(League).filter_by(league_id=league_id).first()
        
        if not league:
            return "League not found", 404
        
        latest_recap = db_session.query(Recap).filter_by(
            league_id=league_id
        ).order_by(Recap.created_at.desc()).first()
        
        return render_template('dashboard.html', 
                             league=league,
                             latest_recap=latest_recap)
    except Exception as e:
        logger.error(f"Dashboard error: {str(e)}")
        return f"Error: {str(e)}", 500

@app.route('/recap/<league_id>/<week>')
def view_recap(league_id, week):
    """Public recap view"""
    try:
        recap = db_session.query(Recap).filter_by(
            league_id=league_id,
            week=week,
            status='published'
        ).first()
        
        if not recap:
            return "Recap not found or not published", 404
        
        league = db_session.query(League).filter_by(league_id=league_id).first()
        
        return render_template('recap.html',
                             recap=recap,
                             league=league)
    except Exception as e:
        logger.error(f"Recap view error: {str(e)}")
        return f"Error: {str(e)}", 500

@app.route('/briefing')
def view_briefing():
    """Personal briefing view"""
    try:
        league_id = request.args.get('league_id')
        team_id = request.args.get('team_id')
        
        if not league_id or not team_id:
            return "league_id and team_id required", 400
        
        briefing = db_session.query(Briefing).filter_by(
            league_id=league_id,
            team_id=team_id
        ).order_by(Briefing.created_at.desc()).first()
        
        if not briefing:
            return "Briefing not found", 404
        
        league = db_session.query(League).filter_by(league_id=league_id).first()
        
        return render_template('briefing.html',
                             briefing=briefing,
                             league=league,
                             team_id=team_id)
    except Exception as e:
        logger.error(f"Briefing view error: {str(e)}")
        return f"Error: {str(e)}", 500

# ============ SCHEDULED JOBS ============

@app.route('/api/recap/scheduled', methods=['POST', 'GET'])
def scheduled_recap_job():
    """Runs every Tuesday at 8 AM"""
    try:
        league_id = os.getenv('SLEEPER_LEAGUE_ID')
        
        # Sync league data
        sleeper.sync_league(league_id)
        
        # Generate recap
        generate_recap_endpoint()
        
        return jsonify({"status": "scheduled job executed", "league_id": league_id})
    except Exception as e:
        logger.error(f"Scheduled job failed: {str(e)}")
        return jsonify({"status": "error", "error": str(e)}), 500

# ============ ERROR HANDLERS ============

@app.errorhandler(404)
def not_found(error):
    return jsonify({"error": "not found"}), 404

@app.errorhandler(500)
def server_error(error):
    logger.error(f"Server error: {str(error)}")
    return jsonify({"error": "server error"}), 500

if __name__ == '__main__':
     port = int(os.getenv('PORT', 5000))
     app.run(host='0.0.0.0', port=port, debug=False)
