from flask import Flask, render_template, jsonify, request
from flask_cors import CORS
import os
from dotenv import load_dotenv
import logging
import uuid
import random

load_dotenv()

app = Flask(__name__, template_folder='templates')
CORS(app)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

from database import init_db, db_session, League, Recap, Briefing, User, Roster, Matchup
from sleeper_client import SleeperClient, build_bye_conflicts_from_team_map, _normalize_name
from espn_data import get_weather_by_team, build_weather_notes, get_relevant_news, build_news_notes
from fantasypros_data import get_projected_points_for_names, build_projection_notes, get_current_nfl_week
from claude_helper import generate_recap, generate_draft_recap, generate_briefing, generate_season_preview, ai_resolve_team_for_names, generate_lineup_suggestion, generate_matchup_preview, ai_resolve_player_info_for_names

sleeper = SleeperClient()

@app.teardown_appcontext
def shutdown_session(exception=None):
    db_session.remove()

def generate_pin(length):
    return ''.join([str(random.randint(0, 9)) for _ in range(length)])

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/manual-setup')
def manual_setup_page():
    return render_template('manual_setup.html')

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

@app.route('/api/migrate-db', methods=['GET', 'POST'])
def migrate_database():
    try:
        from sqlalchemy import text
        from database import engine

        migrations = [
            "ALTER TABLE leagues ADD COLUMN IF NOT EXISTS league_pin VARCHAR(6)",
            "ALTER TABLE leagues ADD COLUMN IF NOT EXISTS prize_pool FLOAT DEFAULT 0.0",
            "ALTER TABLE leagues ADD COLUMN IF NOT EXISTS first_place_amount FLOAT DEFAULT 0.0",
            "ALTER TABLE leagues ADD COLUMN IF NOT EXISTS second_place_amount FLOAT DEFAULT 0.0",
            "ALTER TABLE leagues ADD COLUMN IF NOT EXISTS third_place_amount FLOAT DEFAULT 0.0",
            "ALTER TABLE leagues ADD COLUMN IF NOT EXISTS weather_api_key VARCHAR",
            "ALTER TABLE rosters ADD COLUMN IF NOT EXISTS team_pin VARCHAR(4)",
            "ALTER TABLE rosters ADD COLUMN IF NOT EXISTS claimed BOOLEAN DEFAULT FALSE",
        ]

        results = []
        with engine.connect() as conn:
            for stmt in migrations:
                conn.execute(text(stmt))
                conn.commit()
                results.append(stmt)

        return jsonify({"status": "migrated", "statements_run": len(results)})
    except Exception as e:
        logger.error(f"Migration failed: {str(e)}")
        return jsonify({"status": "error", "error": str(e)}), 500

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

@app.route('/api/league/manual-setup', methods=['POST'])
def manual_league_setup():
    try:
        data = request.get_json()
        league_id = data.get('league_id')
        league_name = data.get('league_name')
        teams = data.get('teams', [])
        prize_pool = data.get('prize_pool', 0)
        first_place_amount = data.get('first_place_amount', 0)
        second_place_amount = data.get('second_place_amount', 0)
        third_place_amount = data.get('third_place_amount', 0)

        if not league_id or not league_name:
            return jsonify({"status": "error", "error": "league_id and league_name required"}), 400

        if not teams:
            return jsonify({"status": "error", "error": "at least one team required"}), 400

        league = db_session.query(League).filter_by(league_id=league_id).first()
        is_new = False
        if not league:
            is_new = True
            league = League(
                id=str(uuid.uuid4()),
                league_id=league_id,
                name=league_name,
                platform='espn_manual',
                settings={},
                league_pin=generate_pin(6),
                prize_pool=prize_pool,
                first_place_amount=first_place_amount,
                second_place_amount=second_place_amount,
                third_place_amount=third_place_amount
            )
            db_session.add(league)
        else:
            league.name = league_name
            league.prize_pool = prize_pool
            league.first_place_amount = first_place_amount
            league.second_place_amount = second_place_amount
            league.third_place_amount = third_place_amount
            if not league.league_pin:
                league.league_pin = generate_pin(6)
        db_session.commit()

        for idx, team in enumerate(teams):
            team_id = str(idx + 1)
            existing = db_session.query(Roster).filter_by(league_id=league_id, team_id=team_id).first()
            players_raw = team.get('players', '')
            players_list = [p.strip() for p in players_raw.split(',') if p.strip()] if isinstance(players_raw, str) else (players_raw or [])

            if not existing:
                new_roster = Roster(
                    id=str(uuid.uuid4()),
                    league_id=league_id,
                    team_id=team_id,
                    team_name=team.get('team_name'),
                    owner_name=None,
                    players=players_list,
                    wins=team.get('wins', 0),
                    losses=team.get('losses', 0),
                    points_for=team.get('points_for', 0),
                    points_against=team.get('points_against', 0)
                )
                db_session.add(new_roster)
            else:
                existing.team_name = team.get('team_name')
                existing.players = players_list
                existing.wins = team.get('wins', 0)
                existing.losses = team.get('losses', 0)
                existing.points_for = team.get('points_for', 0)
                existing.points_against = team.get('points_against', 0)

        db_session.commit()

        return jsonify({
            "status": "saved",
            "league_id": league_id,
            "teams": len(teams),
            "league_pin": league.league_pin
        })
    except Exception as e:
        logger.error(f"Manual league setup failed: {str(e)}")
        return jsonify({"status": "error", "error": str(e)}), 500

@app.route('/join')
def join_page():
    return render_template('join.html')

@app.route('/login')
def login_page():
    return render_template('login.html')

@app.route('/api/league/find-by-pin', methods=['POST'])
def find_league_by_pin():
    try:
        data = request.get_json()
        league_pin = data.get('league_pin', '').strip()

        if not league_pin:
            return jsonify({"status": "error", "error": "league_pin required"}), 400

        league = db_session.query(League).filter_by(league_pin=league_pin).first()
        if not league:
            return jsonify({"status": "error", "error": "No league found with that PIN"}), 404

        rosters = db_session.query(Roster).filter_by(league_id=league.league_id).all()
        teams = [
            {"team_id": r.team_id, "team_name": r.team_name, "claimed": bool(r.claimed)}
            for r in rosters
        ]

        return jsonify({
            "status": "found",
            "league_id": league.league_id,
            "league_name": league.name,
            "teams": teams
        })
    except Exception as e:
        logger.error(f"Find league by pin failed: {str(e)}")
        return jsonify({"status": "error", "error": str(e)}), 500

@app.route('/api/team/claim-with-pin', methods=['POST'])
def claim_team_with_pin():
    try:
        data = request.get_json()
        league_id = data.get('league_id')
        team_id = data.get('team_id')
        team_pin = data.get('team_pin', '').strip()

        if not league_id or not team_id or not team_pin:
            return jsonify({"status": "error", "error": "league_id, team_id, and team_pin required"}), 400

        if len(team_pin) != 4 or not team_pin.isdigit():
            return jsonify({"status": "error", "error": "team_pin must be exactly 4 digits"}), 400

        roster = db_session.query(Roster).filter_by(league_id=league_id, team_id=team_id).first()
        if not roster:
            return jsonify({"status": "error", "error": "Team not found"}), 404

        if roster.claimed:
            return jsonify({"status": "error", "error": "This team has already been claimed"}), 400

        roster.team_pin = team_pin
        roster.claimed = True
        db_session.commit()

        return jsonify({
            "status": "claimed",
            "league_id": league_id,
            "team_id": team_id,
            "team_name": roster.team_name
        })
    except Exception as e:
        logger.error(f"Claim team with pin failed: {str(e)}")
        return jsonify({"status": "error", "error": str(e)}), 500

@app.route('/api/team/login-with-pin', methods=['POST'])
def login_team_with_pin():
    try:
        data = request.get_json()
        league_pin = data.get('league_pin', '').strip()
        team_pin = data.get('team_pin', '').strip()

        if not league_pin or not team_pin:
            return jsonify({"status": "error", "error": "league_pin and team_pin required"}), 400

        league = db_session.query(League).filter_by(league_pin=league_pin).first()
        if not league:
            return jsonify({"status": "error", "error": "No league found with that PIN"}), 404

        roster = db_session.query(Roster).filter_by(
            league_id=league.league_id, team_pin=team_pin, claimed=True
        ).first()
        if not roster:
            return jsonify({"status": "error", "error": "Incorrect team PIN"}), 404

        return jsonify({
            "status": "logged in",
            "league_id": league.league_id,
            "league_name": league.name,
            "team_id": roster.team_id,
            "team_name": roster.team_name
        })
    except Exception as e:
        logger.error(f"Login with pin failed: {str(e)}")
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

@app.route('/api/recap/draft', methods=['POST', 'GET'])
def generate_draft_recap_endpoint():
    try:
        league_id = request.args.get('league_id') or os.getenv('SLEEPER_LEAGUE_ID')

        league = db_session.query(League).filter_by(league_id=league_id).first()
        if not league:
            return jsonify({"status": "league not found"}), 404

        rosters = db_session.query(Roster).filter_by(league_id=league_id).all()
        roster_map = {r.team_id: r.team_name for r in rosters}

        draft_id = sleeper.get_draft_id(league_id)
        if not draft_id:
            return jsonify({"status": "no draft found for this league"}), 404

        picks = sleeper.get_draft_picks(draft_id)
        players = sleeper.get_players_map()

        picks_lines = []
        for pick in picks:
            player_id = pick.get('player_id')
            player_info = players.get(player_id, {})
            player_name = player_info.get('full_name', f"Player {player_id}")
            position = player_info.get('position', '')
            roster_id = str(pick.get('roster_id'))
            team_name = roster_map.get(roster_id, f"Team {roster_id}")
            pick_no = pick.get('pick_no')
            picks_lines.append(f"Pick {pick_no}: {team_name} selected {player_name} ({position})")

        draft_picks_text = chr(10).join(picks_lines)

        recap_content = generate_draft_recap(league_id, draft_picks_text, league.name)

        recap = Recap(
            id=str(uuid.uuid4()),
            league_id=league_id,
            week="draft",
            content=recap_content,
            status='draft'
        )
        db_session.add(recap)
        db_session.commit()

        return jsonify({"status": "draft recap generated", "league_id": league_id})
    except Exception as e:
        logger.error(f"Draft recap generation failed: {str(e)}")
        return jsonify({"status": "error", "error": str(e)}), 500

@app.route('/api/recap/draft-manual', methods=['POST'])
def generate_manual_draft_recap_endpoint():
    try:
        data = request.get_json()
        league_id = data.get('league_id')
        draft_text = data.get('draft_text', '').strip()

        if not league_id or not draft_text:
            return jsonify({"status": "error", "error": "league_id and draft_text required"}), 400

        league = db_session.query(League).filter_by(league_id=league_id).first()
        if not league:
            return jsonify({"status": "error", "error": "league not found"}), 404

        recap_content = generate_draft_recap(league_id, draft_text, league.name)

        recap = Recap(
            id=str(uuid.uuid4()),
            league_id=league_id,
            week="draft",
            content=recap_content,
            status='draft'
        )
        db_session.add(recap)
        db_session.commit()

        return jsonify({"status": "draft recap generated", "league_id": league_id})
    except Exception as e:
        logger.error(f"Manual draft recap generation failed: {str(e)}")
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

@app.route('/api/claim-team', methods=['POST', 'GET'])
def claim_team():
    try:
        league_id = request.args.get('league_id') or os.getenv('SLEEPER_LEAGUE_ID')
        team_id = request.args.get('team_id')
        email = request.args.get('email', 'default@example.com')

        if not team_id:
            return jsonify({"status": "team_id required"}), 400

        roster = db_session.query(Roster).filter_by(league_id=league_id, team_id=team_id).first()
        if not roster:
            return jsonify({"status": "roster not found"}), 404

        user = db_session.query(User).filter_by(email=email).first()
        if not user:
            user = User(id=str(uuid.uuid4()), email=email, claimed_teams=f"{league_id}:{team_id}")
            db_session.add(user)
        else:
            user.claimed_teams = f"{league_id}:{team_id}"
        db_session.commit()

        return jsonify({
            "status": "team claimed",
            "league_id": league_id,
            "team_id": team_id,
            "team_name": roster.team_name
        })
    except Exception as e:
        logger.error(f"Claim team failed: {str(e)}")
        return jsonify({"status": "error", "error": str(e)}), 500

@app.route('/api/briefing/generate', methods=['POST', 'GET'])
def generate_briefing_endpoint():
    try:
        league_id = request.args.get('league_id') or os.getenv('SLEEPER_LEAGUE_ID')
        team_id = request.args.get('team_id')

        if not team_id:
            return jsonify({"status": "team_id required"}), 400

        roster = db_session.query(Roster).filter_by(league_id=league_id, team_id=team_id).first()
        if not roster:
            return jsonify({"status": "roster not found"}), 404

        bye_conflicts = []
        weather_notes = []
        news_notes = []
        projection_notes = []
        try:
            if roster.players:
                resolved, unresolved = sleeper.resolve_teams_for_names(roster.players)
                if unresolved:
                    ai_resolved = ai_resolve_team_for_names(unresolved)
                    resolved.update(ai_resolved)
                bye_conflicts = build_bye_conflicts_from_team_map(resolved)

                weather_by_team = get_weather_by_team()
                weather_notes = build_weather_notes(resolved, weather_by_team)

                news_items = get_relevant_news(roster.players)
                news_notes = build_news_notes(news_items)

                projections = get_projected_points_for_names(roster.players)
                projection_notes = build_projection_notes(projections)
        except Exception as e:
            logger.warning(f"Bye conflict / weather / news / projections lookup failed: {str(e)}")

        briefing_data = generate_briefing(league_id, team_id, bye_conflicts=bye_conflicts, weather_notes=weather_notes, news_notes=news_notes, projection_notes=projection_notes)

        briefing = Briefing(
            id=str(uuid.uuid4()),
            league_id=league_id,
            team_id=team_id,
            team_name=roster.team_name,
            content=briefing_data
        )
        db_session.add(briefing)
        db_session.commit()

        return jsonify({
            "status": "briefing generated",
            "league_id": league_id,
            "team_id": team_id,
            "briefing": briefing_data
        })
    except Exception as e:
        logger.error(f"Briefing generation failed: {str(e)}")
        return jsonify({"status": "error", "error": str(e)}), 500

@app.route('/api/season-preview/generate', methods=['POST', 'GET'])
def generate_season_preview_endpoint():
    try:
        league_id = request.args.get('league_id')
        if not league_id:
            return jsonify({"status": "error", "error": "league_id required"}), 400

        preview_data = generate_season_preview(league_id)

        return jsonify({
            "status": "generated",
            "league_id": league_id,
            "preview": preview_data
        })
    except Exception as e:
        logger.error(f"Season preview generation failed: {str(e)}")
        return jsonify({"status": "error", "error": str(e)}), 500

@app.route('/api/lineup/generate', methods=['POST', 'GET'])
def generate_lineup_endpoint():
    try:
        league_id = request.args.get('league_id')
        team_id = request.args.get('team_id')

        if not league_id or not team_id:
            return jsonify({"status": "error", "error": "league_id and team_id required"}), 400

        weather_notes = []
        news_notes = []
        projection_notes = []
        try:
            roster = db_session.query(Roster).filter_by(league_id=league_id, team_id=team_id).first()
            if roster and roster.players:
                resolved, unresolved = sleeper.resolve_teams_for_names(roster.players)
                if unresolved:
                    ai_resolved = ai_resolve_team_for_names(unresolved)
                    resolved.update(ai_resolved)
                weather_by_team = get_weather_by_team()
                weather_notes = build_weather_notes(resolved, weather_by_team)

                news_items = get_relevant_news(roster.players)
                news_notes = build_news_notes(news_items)

                projections = get_projected_points_for_names(roster.players)
                projection_notes = build_projection_notes(projections)
        except Exception as e:
            logger.warning(f"Weather / news / projections lookup failed for lineup: {str(e)}")

        lineup_data = generate_lineup_suggestion(league_id, team_id, weather_notes=weather_notes, news_notes=news_notes, projection_notes=projection_notes)

        return jsonify({
            "status": "generated",
            "league_id": league_id,
            "team_id": team_id,
            "lineup": lineup_data
        })
    except Exception as e:
        logger.error(f"Lineup generation failed: {str(e)}")
        return jsonify({"status": "error", "error": str(e)}), 500

@app.route('/api/league/teams', methods=['GET'])
def get_league_teams():
    try:
        league_id = request.args.get('league_id')
        exclude_team_id = request.args.get('exclude_team_id')
        if not league_id:
            return jsonify({"status": "error", "error": "league_id required"}), 400
        rosters = db_session.query(Roster).filter_by(league_id=league_id).all()
        teams = [
            {"team_id": r.team_id, "team_name": r.team_name}
            for r in rosters if r.team_id != exclude_team_id
        ]
        return jsonify({"status": "ok", "teams": teams})
    except Exception as e:
        logger.error(f"Get league teams failed: {str(e)}")
        return jsonify({"status": "error", "error": str(e)}), 500

@app.route('/api/matchup/set-opponent', methods=['POST'])
def set_matchup_opponent():
    try:
        data = request.get_json()
        league_id = data.get('league_id')
        team_id = data.get('team_id')
        opponent_team_id = data.get('opponent_team_id')
        week = data.get('week') or get_current_nfl_week()

        if not league_id or not team_id or not opponent_team_id:
            return jsonify({"status": "error", "error": "league_id, team_id, opponent_team_id required"}), 400

        my_roster = db_session.query(Roster).filter_by(league_id=league_id, team_id=team_id).first()
        opp_roster = db_session.query(Roster).filter_by(league_id=league_id, team_id=opponent_team_id).first()
        if not my_roster or not opp_roster:
            return jsonify({"status": "error", "error": "team not found"}), 404

        week = int(week)

        existing = db_session.query(Matchup).filter_by(league_id=league_id, week=week).filter(
            ((Matchup.team_1_id == team_id) & (Matchup.team_2_id == opponent_team_id)) |
            ((Matchup.team_1_id == opponent_team_id) & (Matchup.team_2_id == team_id))
        ).first()

        if existing:
            existing.team_1_id = team_id
            existing.team_1_name = my_roster.team_name
            existing.team_2_id = opponent_team_id
            existing.team_2_name = opp_roster.team_name
        else:
            new_matchup = Matchup(
                id=str(uuid.uuid4()),
                league_id=league_id,
                week=week,
                team_1_id=team_id,
                team_1_name=my_roster.team_name,
                team_2_id=opponent_team_id,
                team_2_name=opp_roster.team_name
            )
            db_session.add(new_matchup)

        db_session.commit()
        return jsonify({"status": "saved", "week": week})
    except Exception as e:
        logger.error(f"Set matchup opponent failed: {str(e)}")
        return jsonify({"status": "error", "error": str(e)}), 500

@app.route('/api/matchup/current', methods=['GET'])
def get_current_matchup():
    try:
        league_id = request.args.get('league_id')
        team_id = request.args.get('team_id')
        week_param = request.args.get('week')

        if not league_id or not team_id:
            return jsonify({"status": "error", "error": "league_id and team_id required"}), 400

        week = int(week_param) if week_param else get_current_nfl_week()

        matchup = db_session.query(Matchup).filter_by(league_id=league_id, week=week).filter(
            (Matchup.team_1_id == team_id) | (Matchup.team_2_id == team_id)
        ).first()

        if not matchup:
            return jsonify({"status": "not_set", "week": week})

        if matchup.team_1_id == team_id:
            opponent_id = matchup.team_2_id
            opponent_name = matchup.team_2_name
        else:
            opponent_id = matchup.team_1_id
            opponent_name = matchup.team_1_name

        my_roster = db_session.query(Roster).filter_by(league_id=league_id, team_id=team_id).first()
        opp_roster = db_session.query(Roster).filter_by(league_id=league_id, team_id=opponent_id).first()

        preview = generate_matchup_preview(
            my_roster.team_name if my_roster else "Your team",
            (my_roster.players or []) if my_roster else [],
            opponent_name,
            (opp_roster.players or []) if opp_roster else []
        )

        return jsonify({
            "status": "ok",
            "week": week,
            "opponent_name": opponent_name,
            "opponent_team_id": opponent_id,
            "preview": preview
        })
    except Exception as e:
        logger.error(f"Get current matchup failed: {str(e)}")
        return jsonify({"status": "error", "error": str(e)}), 500

@app.route('/api/roster/update-players', methods=['POST'])
def update_roster_players():
    try:
        data = request.get_json()
        league_id = data.get('league_id')
        team_id = data.get('team_id')
        players_raw = data.get('players', '')

        if not league_id or not team_id:
            return jsonify({"status": "error", "error": "league_id and team_id required"}), 400

        roster = db_session.query(Roster).filter_by(league_id=league_id, team_id=team_id).first()
        if not roster:
            return jsonify({"status": "error", "error": "roster not found"}), 404

        players_list = [p.strip() for p in players_raw.split(',') if p.strip()]
        roster.players = players_list
        db_session.commit()

        return jsonify({"status": "updated", "players": players_list})
    except Exception as e:
        logger.error(f"Update roster players failed: {str(e)}")
        return jsonify({"status": "error", "error": str(e)}), 500

@app.route('/api/roster/full', methods=['GET'])
def get_full_roster():
    try:
        league_id = request.args.get('league_id')
        team_id = request.args.get('team_id')

        if not league_id or not team_id:
            return jsonify({"status": "error", "error": "league_id and team_id required"}), 400

        roster = db_session.query(Roster).filter_by(league_id=league_id, team_id=team_id).first()
        if not roster:
            return jsonify({"status": "error", "error": "roster not found"}), 404

        player_names = roster.players or []

        weather_by_team = get_weather_by_team()
        news_items = get_relevant_news(player_names)
        news_by_player = {item['player']: item for item in news_items}
        projections = get_projected_points_for_names(player_names)

        bye_conflicts = []
        players_out = []
        try:
            resolved, unresolved = sleeper.resolve_teams_for_names(player_names)
            if unresolved:
                ai_resolved = ai_resolve_team_for_names(unresolved)
                resolved.update(ai_resolved)
            bye_conflicts = build_bye_conflicts_from_team_map(resolved)
        except Exception as e:
            logger.warning(f"Bye lookup failed for roster view: {str(e)}")

        sleeper_info_by_name = {}
        unresolved_for_ai = []
        for name in player_names:
            info = sleeper.resolve_player_info_for_name(name)
            sleeper_info_by_name[name] = info
            if not info or not info.get('team') or not info.get('position'):
                unresolved_for_ai.append(name)

        ai_info_by_name = {}
        if unresolved_for_ai:
            raw_ai_info = ai_resolve_player_info_for_names(unresolved_for_ai)
            for k, v in raw_ai_info.items():
                ai_info_by_name[_normalize_name(k)] = v

        results = []
        for name in player_names:
            info = sleeper_info_by_name.get(name)
            team = info.get('team') if info else None
            position = info.get('position') if info else None
            injury_status = info.get('injury_status') if info else None

            if not team or not position:
                ai_info = ai_info_by_name.get(_normalize_name(name))
                if ai_info:
                    team = team or ai_info.get('team')
                    position = position or ai_info.get('position')

            projected_points = projections.get(name)

            notes = []
            if name in news_by_player:
                item = news_by_player[name]
                notes.append(f"{item['headline']}")
            if team and team.upper() in weather_by_team:
                notes.append(f"Weather: {weather_by_team[team.upper()]}")
            for conflict in bye_conflicts:
                if name in conflict:
                    notes.append(conflict)

            results.append({
                "name": name,
                "team": team,
                "position": position,
                "injury_status": injury_status,
                "projected_points": projected_points,
                "notes": notes
            })

        return jsonify({
            "status": "ok",
            "league_id": league_id,
            "team_id": team_id,
            "players": results
        })
    except Exception as e:
        logger.error(f"Get full roster failed: {str(e)}")
        return jsonify({"status": "error", "error": str(e)}), 500

@app.route('/api/debug/fantasypros', methods=['GET'])
def debug_fantasypros():
    try:
        from fantasypros_data import get_weekly_projections
        data = get_weekly_projections()
        return jsonify({"status": "ok", "raw_response": data})
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500

@app.route('/api/debug/roster-resolve', methods=['GET'])
def debug_roster_resolve():
    try:
        league_id = request.args.get('league_id')
        team_id = request.args.get('team_id')
        roster = db_session.query(Roster).filter_by(league_id=league_id, team_id=team_id).first()
        if not roster:
            return jsonify({"status": "error", "error": "roster not found"}), 404

        player_names = roster.players or []
        sleeper_results = {}
        unresolved = []
        for name in player_names:
            info = sleeper.resolve_player_info_for_name(name)
            sleeper_results[name] = info
            if not info or not info.get('team') or not info.get('position'):
                unresolved.append(name)

        ai_raw = ai_resolve_player_info_for_names(unresolved) if unresolved else {}

        return jsonify({
            "status": "ok",
            "player_names": player_names,
            "sleeper_results": sleeper_results,
            "unresolved_sent_to_ai": unresolved,
            "ai_raw_response": ai_raw
        })
    except Exception as e:
        logger.error(f"Debug roster resolve failed: {str(e)}")
        return jsonify({"status": "error", "error": str(e)}), 500

@app.route('/api/stakes', methods=['GET'])
def get_stakes():
    try:
        league_id = request.args.get('league_id')
        if not league_id:
            return jsonify({"status": "error", "error": "league_id required"}), 400

        league = db_session.query(League).filter_by(league_id=league_id).first()
        if not league:
            return jsonify({"status": "error", "error": "league not found"}), 404

        rosters = db_session.query(Roster).filter_by(league_id=league_id).all()

        standings = sorted(
            rosters,
            key=lambda r: (-(r.wins or 0), (r.losses or 0), -(r.points_for or 0))
        )

        num_teams = len(standings)
        results = []
        for idx, r in enumerate(standings):
            place = idx + 1
            payout = 0.0
            if place == 1:
                payout = league.first_place_amount or 0
            elif place == 2:
                payout = league.second_place_amount or 0
            elif place == 3:
                payout = league.third_place_amount or 0

            punishment_watch = place > num_teams - 2 if num_teams > 2 else False

            results.append({
                "place": place,
                "team_name": r.team_name,
                "wins": r.wins or 0,
                "losses": r.losses or 0,
                "points_for": r.points_for or 0,
                "payout": payout,
                "punishment_watch": punishment_watch
            })

        return jsonify({
            "status": "ok",
            "league_id": league_id,
            "prize_pool": league.prize_pool or 0,
            "first_place_amount": league.first_place_amount or 0,
            "second_place_amount": league.second_place_amount or 0,
            "third_place_amount": league.third_place_amount or 0,
            "standings": results
        })
    except Exception as e:
        logger.error(f"Get stakes failed: {str(e)}")
        return jsonify({"status": "error", "error": str(e)}), 500

@app.route('/api/recaps/list', methods=['GET'])
def list_recaps():
    try:
        league_id = request.args.get('league_id')
        if not league_id:
            return jsonify({"status": "error", "error": "league_id required"}), 400

        recaps = db_session.query(Recap).filter_by(
            league_id=league_id, status='published'
        ).order_by(Recap.created_at.desc()).all()

        results = [
            {"week": r.week, "created_at": r.created_at.isoformat() if r.created_at else None}
            for r in recaps
        ]

        return jsonify({"status": "ok", "league_id": league_id, "recaps": results})
    except Exception as e:
        logger.error(f"List recaps failed: {str(e)}")
        return jsonify({"status": "error", "error": str(e)}), 500

@app.route('/team-home')
def team_home():
    try:
        league_id = request.args.get('league_id')
        team_id = request.args.get('team_id')

        if not league_id or not team_id:
            return "league_id and team_id required", 400

        league = db_session.query(League).filter_by(league_id=league_id).first()
        roster = db_session.query(Roster).filter_by(league_id=league_id, team_id=team_id).first()

        if not league or not roster:
            return "League or team not found", 404

        return render_template('team_home.html', league=league, roster=roster)
    except Exception as e:
        logger.error(f"Team home error: {str(e)}")
        return f"Error: {str(e)}", 500

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

@app.route('/briefing')
def view_briefing():
    try:
        league_id = request.args.get('league_id') or os.getenv('SLEEPER_LEAGUE_ID')
        team_id = request.args.get('team_id')

        if not team_id:
            return "team_id required", 400

        briefing = db_session.query(Briefing).filter_by(
            league_id=league_id, team_id=team_id
        ).order_by(Briefing.created_at.desc()).first()

        if not briefing:
            return "Briefing not found. Generate one first.", 404

        league = db_session.query(League).filter_by(league_id=league_id).first()

        return render_template('briefing.html', briefing=briefing.content, league=league, team_id=team_id)
    except Exception as e:
        logger.error(f"Briefing view error: {str(e)}")
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
