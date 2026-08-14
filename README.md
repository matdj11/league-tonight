# League Tonight

An AI-powered fantasy football app that generates weekly recaps and personalized briefings for your league.

## Features

- **League Tonight**: Weekly AI-generated recap with upset highlights, power rankings, and league storylines
- **Team Briefing**: Personalized daily briefing with roster-specific insights and sources
- **Prize Pool Tracking**: Stakes and payout information
- **Multi-Platform**: Supports Sleeper and ESPN fantasy platforms

## Quick Start

### Prerequisites

- Python 3.9+
- PostgreSQL database (via Neon)
- Claude API key
- Render account for hosting

### Environment Variables

Create a `.env` file with:

```
DATABASE_URL=postgresql://user:password@host/dbname
CLAUDE_API_KEY=sk-ant-...
SLEEPER_LEAGUE_ID=your-sleeper-league-id
SLEEPER_USERNAME=your-sleeper-username
ESPN_LEAGUE_ID=your-espn-league-id
ESPN_S2=your-espn-s2-cookie
ESPN_SWID=your-espn-swid-cookie
FLASK_ENV=production
```

### Local Development

1. Clone repository
2. Create virtual environment: `python -m venv venv`
3. Activate: `source venv/bin/activate` (or `venv\Scripts\activate` on Windows)
4. Install dependencies: `pip install -r requirements.txt`
5. Initialize database: `python -c "from database import init_db; init_db()"`
6. Run server: `python app.py`
7. Visit `http://localhost:5000/health`

### Deployment to Render

1. Push code to GitHub repository
2. Connect repository to Render (see setup guide)
3. Render will automatically:
   - Install dependencies from `requirements.txt`
   - Run `init_db()` on first deploy
   - Start server with `gunicorn app:app`

## API Endpoints

### Health & Testing

- `GET /health` - Health check
- `GET /api/test-db` - Test database connection
- `GET /api/test-sleeper` - Test Sleeper integration
- `GET /api/test-espn` - Test ESPN integration

### League Management

- `POST /api/league/sync` - Sync league data from Sleeper/ESPN
- `POST /api/init-db` - Initialize database tables

### Recap Generation

- `POST /api/recap/generate` - Generate weekly recap
- `POST /api/recap/publish` - Publish recap
- `GET /recap/<league_id>/<week>` - View published recap

### Briefings

- `POST /api/briefing/generate` - Generate personal briefing
- `GET /briefing?league_id=X&team_id=Y` - View briefing
- `POST /api/claim-team` - Claim a team for personal briefings

### Dashboard

- `GET /dashboard` - Commissioner dashboard

### Scheduled Jobs

- `POST /api/recap/scheduled` - Scheduled job (runs every Tuesday 8 AM)

## File Structure

```
league-tonight/
├── app.py                 # Main Flask application
├── database.py            # Database models and initialization
├── sleeper_client.py      # Sleeper API client
├── espn_client.py         # ESPN API client
├── claude_helper.py       # Claude integration for recaps/briefings
├── external_data.py       # Injury and weather data syncing
├── requirements.txt       # Python dependencies
├── .gitignore            # Git ignore rules
├── .env.example           # Environment variables template
└── templates/             # Flask HTML templates
    ├── dashboard.html     # Commissioner dashboard
    ├── recap.html         # Recap view
    └── briefing.html      # Briefing view
```

## How It Works

### Weekly Recap Generation

1. **Data Sync**: Pulls league rosters, matchups, and scores from Sleeper/ESPN
2. **Claude Processing**: Sends league data to Claude API with structured prompt
3. **Recap Generation**: Claude generates entertaining recap with:
   - Biggest upset
   - Closest game
   - Blowout of the week
   - Power rankings
   - Punishment watch
   - AI hot take
4. **Publishing**: Commissioner can publish to league, generating shareable link

### Personal Briefing

1. **Roster Sync**: Pulls manager's roster and league settings
2. **Data Enrichment**: Adds injury reports and weather forecasts
3. **Claude Processing**: Sends to Claude with briefing prompt
4. **Insight Generation**: Claude produces 3-5 roster-specific insights with:
   - Specific action items
   - Source attribution
   - Links to sources
5. **Display**: Shows in-app or sends via email

## Sleeper vs ESPN

### Sleeper
- **Pros**: Public API, no authentication needed, faster
- **Cons**: Must have Sleeper league

### ESPN
- **Pros**: Works with ESPN leagues
- **Cons**: Requires cookie authentication (less reliable)

For MVP, recommend starting with Sleeper. ESPN support via cookies is available but may require periodic re-authentication.

## Troubleshooting

### "Database connection failed"
- Verify `DATABASE_URL` is correct (copy fresh from Neon)
- Check that Neon IP allowlist includes Render's IP

### "Claude API key invalid"
- Verify key starts with `sk-ant-`
- Ensure no extra spaces in environment variable
- Generate new key from console.anthropic.com if needed

### "Sleeper league not found"
- Verify `SLEEPER_LEAGUE_ID` is just the ID (not a URL)
- Confirm league is public or you're logged in

### "ESPN connection failed"
- Re-extract `ESPN_S2` and `ESPN_SWID` from browser (cookies expire)
- Verify both values are present and complete

## Development

To test locally:

```bash
# Test database
curl http://localhost:5000/api/test-db

# Sync your league
curl -X POST "http://localhost:5000/api/league/sync?league_id=YOUR_ID"

# Generate recap
curl -X POST "http://localhost:5000/api/recap/generate"

# Generate briefing
curl -X POST "http://localhost:5000/api/briefing/generate?team_id=1"
```

## License

MIT
