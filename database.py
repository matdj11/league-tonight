import os
from sqlalchemy import create_engine, Column, String, Integer, Text, DateTime, Float, JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, scoped_session
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

# Database connection
DATABASE_URL = os.getenv('DATABASE_URL')
if not DATABASE_URL:
    raise ValueError("DATABASE_URL environment variable not set")

# Handle postgres vs postgresql URL scheme (Neon uses postgresql://)
if DATABASE_URL.startswith('postgres://'):
    DATABASE_URL = DATABASE_URL.replace('postgres://', 'postgresql://', 1)

engine = create_engine(DATABASE_URL, echo=False, pool_pre_ping=True, pool_recycle=280)
db_session = scoped_session(sessionmaker(bind=engine))

Base = declarative_base()

# ============ DATABASE MODELS ============

class League(Base):
    __tablename__ = 'leagues'
    
    id = Column(String, primary_key=True)
    league_id = Column(String, unique=True, nullable=False)
    name = Column(String, nullable=False)
    platform = Column(String, nullable=False)  # 'sleeper' or 'espn'
    settings = Column(JSON, default={})
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f"<League {self.name}>"

class User(Base):
    __tablename__ = 'users'
    
    id = Column(String, primary_key=True)
    email = Column(String, unique=True, nullable=False)
    claimed_teams = Column(String, default="")  # "league_id:team_id,league_id:team_id"
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f"<User {self.email}>"

class Roster(Base):
    __tablename__ = 'rosters'
    
    id = Column(String, primary_key=True)
    league_id = Column(String, nullable=False)
    team_id = Column(String, nullable=False)
    team_name = Column(String, nullable=False)
    owner_name = Column(String)
    players = Column(JSON, default=[])  # List of player IDs
    wins = Column(Integer, default=0)
    losses = Column(Integer, default=0)
    points_for = Column(Float, default=0.0)
    points_against = Column(Float, default=0.0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f"<Roster {self.team_name}>"

class Matchup(Base):
    __tablename__ = 'matchups'
    
    id = Column(String, primary_key=True)
    league_id = Column(String, nullable=False)
    week = Column(Integer, nullable=False)
    matchup_id = Column(String)
    team_1_id = Column(String, nullable=False)
    team_1_name = Column(String)
    team_1_score = Column(Float, default=0.0)
    team_2_id = Column(String, nullable=False)
    team_2_name = Column(String)
    team_2_score = Column(Float, default=0.0)
    winner = Column(String)  # team_1_id, team_2_id, or 'tie'
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f"<Matchup Week {self.week}: {self.team_1_name} vs {self.team_2_name}>"

class Score(Base):
    __tablename__ = 'scores'
    
    id = Column(String, primary_key=True)
    league_id = Column(String, nullable=False)
    week = Column(Integer, nullable=False)
    team_id = Column(String, nullable=False)
    team_name = Column(String)
    score = Column(Float, default=0.0)
    projected_score = Column(Float, default=0.0)
    rank = Column(Integer)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f"<Score Week {self.week}: {self.team_name} - {self.score}>"

class Recap(Base):
    __tablename__ = 'recaps'
    
    id = Column(String, primary_key=True)
    league_id = Column(String, nullable=False)
    week = Column(String, nullable=False)  # Can be 'current' or integer
    content = Column(Text, nullable=False)
    status = Column(String, default='draft')  # 'draft' or 'published'
    published_at = Column(DateTime)
    shareable_link = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f"<Recap Week {self.week}>"

class Briefing(Base):
    __tablename__ = 'briefings'
    
    id = Column(String, primary_key=True)
    league_id = Column(String, nullable=False)
    team_id = Column(String, nullable=False)
    team_name = Column(String)
    content = Column(JSON, default={})  # {"insights": [...], "sources": [...]}
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f"<Briefing {self.team_name}>"

class PlayerInjury(Base):
    __tablename__ = 'player_injuries'
    
    id = Column(String, primary_key=True)
    player_id = Column(String, nullable=False)
    player_name = Column(String, nullable=False)
    team = Column(String)
    status = Column(String)  # 'out', 'day_to_day', 'questionable', 'doubtful'
    injury_description = Column(String)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f"<Injury {self.player_name}: {self.status}>"

class GameWeather(Base):
    __tablename__ = 'game_weather'
    
    id = Column(String, primary_key=True)
    game_id = Column(String, nullable=False)
    team = Column(String, nullable=False)
    weather = Column(String)  # JSON: temperature, wind, rain, etc.
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f"<Weather {self.team}>"

# ============ INITIALIZATION ============

def init_db():
    """Create all tables"""
    try:
        Base.metadata.create_all(engine)
        logger.info("Database initialized successfully")
        return True
    except Exception as e:
        logger.error(f"Database initialization failed: {str(e)}")
        raise

# Cleanup function
def cleanup_db():
    db_session.remove()
