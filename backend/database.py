from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@db:5432/influencer_roi_db")

# SQLite (used in tests) needs a special connect arg and no pooling knobs.
_is_sqlite = DATABASE_URL.startswith("sqlite")
_engine_kwargs = (
    {"connect_args": {"check_same_thread": False}}
    if _is_sqlite
    else {
        # Recover transparently from connections dropped by Postgres idle timeout,
        # and recycle long-lived connections before the server closes them.
        "pool_pre_ping": True,
        "pool_recycle": 1800,
    }
)

engine = create_engine(DATABASE_URL, **_engine_kwargs)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()