from flask import Flask, render_template, jsonify, request
from flask_cors import CORS
import os
from dotenv import load_dotenv
import logging
import uuid

load_dotenv()

app = Flask(__name__, template_folder='templates')
CORS(app)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

from database import init_db, db_session, League, Recap, Briefing, User, Roster
from sleeper_client import SleeperClient
from claude_helper import generate_recap

sleeper = SleeperClient()

@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "ok"})

@app.route('/api/test-db', methods=['GET'])
def test_db():
    try:
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

@app.route('/api/init-db', methods=['GET', 'POST'])
def init_database():
    try:
        init_db()
        return jsonify({"status": "database initialized"})
    except Exception as e:
        logger.error(f"DB init failed: {str(e)}")
        return jsonify({"status": "error", "error": str(e)}), 500

@app.route('/api/league/sync', methods=['POST', 'GET'])
def sync_league():
    try:
        league_id = request.args.get('league_id') or os.getenv('SLEEPER_LEAGUE_ID')
        logger.info(f"Syncing Sleeper league {league_id}")
        result = sleeper.sync_league(league_id)
        return jsonify({
            "status": "sync complete",
            "league_id": league_id,
            "platform": "sleeper",
            "teams": result.get("rosters", 0)
        })
    except Exception as e:
        logger.error(f"League sync failed: {str(e)}")
        return jsonify({"status": "error", "error": str(e)}), 500

@app.route('/api/recap/generate', methods=['POST', 'GET'])
def generate_recap_endpoint():
    try:
        league_id = request.args.get('league_id') or os.getenv('SLEEPER_LEAGUE_ID')
        week = request.args.get('week', '1')
        league = db_session.query(League).filter_by(league_id=league_id).first()
        if not league:
            return jsonify({"status": "league not found"}), 404
        recap_content = generate_recap(league_id, week)
        recap = Recap(
            id=str(uuid.uuid4()),
            league_id=league_id,
            week=str(week),
            content=recap_content,
            status='draft'
        )
        db_session.add(recap)
        db_session.commit()
        return jsonify({"status": "recap generated", "league_id": league_id, "week": week})
    except Exception as e:
        logger.error(f"Recap generation failed: {str(e)}")
        return jsonify({"status": "error", "error": str(e)}), 500

@app.route('/api/recap/publish', methods=['POST', 'GET'])
def publish_recap():
    try:
        league_id = request.args.get('league_id') or request.form.get('league_id')
        week = request.args.get('week') or request.form.get('week', '1')
        recap = db_session.query(Recap).filter_by(league_id=league_id, week=str(week)).first()
        if not recap:
            return jsonify({"status": "recap not found"}), 404
        recap.status = 'published'
        db_session.commit()
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

@app.route('/dashboard')
def dashboard():
    try:
        league_id = request.args.get('league_id') or os.getenv('SLEEPER_LEAGUE_ID')
        league = db_session.query(League).filter_by(league_id=league_id).first()
        if not league:
            return "League not found", 404
        latest_recap = db_session.query(Recap).filter_by(league_id=league_id).order_by(Recap.created_at.desc()).first()
        return render_template('dashboard.html', league=league, latest_recap=latest_recap)
    except Exception as e:
        logger.error(f"Dashboard error: {str(e)}")
        return f"Error: {str(e)}", 500

@app.route('/recap/<league_id>/<week>')
def view_recap(league_id, week):
    try:
        recap = db_session.query(Recap).filter_by(league_id=league_id, week=week, status='published').first()
        if not recap:
            return "Recap not found or not published", 404
        league = db_session.query(League).filter_by(league_id=league_id).first()
        return render_template('recap.html', recap=recap, league=league)
    except Exception as e:
        logger.error(f"Recap view error: {str(e)}")
        return f"Error: {str(e)}", 500

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
