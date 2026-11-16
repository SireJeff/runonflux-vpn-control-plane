"""
Database connection and session management
"""

from typing import Any, Dict

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from app.core.config import settings


def build_engine_args(database_url: str) -> Dict[str, Any]:
    """Assemble create_engine() kwargs for the given DATABASE_URL.

    Postgres connections get two per-session guards (via libpq ``options``):

    - ``lock_timeout``: bound how long any statement waits on a row lock. The
      FDM liveness gate does a *synchronous* ``INSERT INTO fdm_ip_liveness``
      inside an async method; if it blocks on a lock held by a transaction
      orphaned by a previously SIGKILLed ``fdm.sync_all_deployments`` cycle, the
      blocking call freezes the whole asyncio event loop for the task's entire
      3600s hard limit -> SIGKILL -> yet another orphaned lock -> a
      self-sustaining cascade that froze every region's FDM sync (2026-08-18).
      A short lock_timeout makes the INSERT fail fast; the gate already
      fail-opens on error, so the cycle completes instead of hanging.
    - ``idle_in_transaction_session_timeout``: auto-reap transactions left idle
      (leaked when a task is killed mid-transaction) so they stop holding locks.
    """
    args: Dict[str, Any] = {
        "pool_pre_ping": True,  # Verify connections before using
        "echo": settings.DEBUG,  # Log SQL queries in debug mode
    }

    if "sqlite" in database_url:
        args["connect_args"] = {"check_same_thread": False}
    else:
        args["pool_size"] = settings.DATABASE_POOL_SIZE
        args["max_overflow"] = settings.DATABASE_MAX_OVERFLOW
        args["connect_args"] = {
            "options": (
                "-c lock_timeout=10s "
                "-c idle_in_transaction_session_timeout=300s"
            )
        }

    return args


engine = create_engine(settings.DATABASE_URL, **build_engine_args(settings.DATABASE_URL))

# Create session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Create declarative base for models
Base = declarative_base()


def get_db():
    """
    Dependency for FastAPI routes to get database session

    Usage in routes:
        @app.get("/users")
        def get_users(db: Session = Depends(get_db)):
            users = db.query(User).all()
            return users
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
