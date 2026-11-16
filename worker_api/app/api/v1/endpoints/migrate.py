"""
Database migration endpoint (admin only)
"""

from fastapi import APIRouter, HTTPException
from sqlalchemy import inspect

from app import (  # noqa: F401  # Ensure model metadata is registered
    models as _all_models,
)
from app.core.database import Base, engine

router = APIRouter(prefix="/migrate", tags=["Admin"])


@router.post("")
async def run_database_migrations():
    """
    Create all database tables using SQLAlchemy models

    **Admin only endpoint**
    Uses Base.metadata.create_all() to create all tables defined in models
    """
    try:
        # Get inspector to check existing tables
        inspector = inspect(engine)
        existing_tables = inspector.get_table_names()

        # Create all tables
        Base.metadata.create_all(bind=engine)

        # Get all table names from metadata
        all_tables = [table.name for table in Base.metadata.sorted_tables]

        # Determine which were created
        created_tables = [t for t in all_tables if t not in existing_tables]
        skipped_tables = [t for t in all_tables if t in existing_tables]

        return {
            "message": "Database migration completed",
            "total_tables": len(all_tables),
            "created": created_tables,
            "already_existed": skipped_tables,
            "status": "success",
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Migration failed: {str(e)}")
