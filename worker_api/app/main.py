"""
FluxVPN Worker/API Service
FastAPI application for backend orchestration
"""

import asyncio
import logging
from contextlib import asynccontextmanager
from time import perf_counter

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.core.config import settings
from app.core.database import Base, SessionLocal, engine
from app.core.exceptions import ConfigurationError
from app.services.monitoring import admin_health_metrics

# Configure logging
logging.basicConfig(
    level=logging.INFO if not settings.DEBUG else logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Module-level state for bot manager init — visible to /health
_BOT_MANAGER_STATUS: str = "unknown"  # one of: "ok", "failed", "unknown"
_BOT_MANAGER_ERROR: str | None = None

# Background task state
_autoscaling_task = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan handler replacing all @app.on_event decorators."""
    global _BOT_MANAGER_STATUS, _BOT_MANAGER_ERROR, _autoscaling_task

    # ===== Startup =====
    logger.info("Starting FluxVPN Worker/API Service...")
    logger.info(f"Environment: {settings.ENVIRONMENT}")
    logger.info(f"Debug mode: {settings.DEBUG}")

    # Seed super admin account for Reseller Platform (idempotent)
    try:
        from app.core.auth.seed import seed_super_admin

        db = SessionLocal()
        try:
            seed_super_admin(db)
        finally:
            db.close()
    except Exception as exc:
        logger.warning(f"Super admin seed failed (non-fatal): {exc}")

    # Create database tables (in production, use Alembic migrations)
    if settings.DEBUG:
        logger.info("Creating database tables...")
        # Base.metadata.create_all(bind=engine)  # Uncomment if needed

    logger.info("Worker/API Service started successfully!")

    # Initialize reseller bot manager (non-fatal on failure)
    try:
        from app.services.bots.end_user_start import register_end_user_handlers
        from app.services.bots.reseller_bot_manager import ResellerBotManager

        db = SessionLocal()
        manager = ResellerBotManager(
            db,
            handler_registrar=register_end_user_handlers,
        )
        reseller_bot_webhook.configure_bot_manager(manager)
        bot_config_api.configure_bot_manager(manager)
        super_admin_bots_api.configure_bot_manager(manager)
        _BOT_MANAGER_STATUS = "ok"
        _BOT_MANAGER_ERROR = None
        logger.info("Reseller bot manager initialized")
    except Exception as exc:
        _BOT_MANAGER_STATUS = "failed"
        _BOT_MANAGER_ERROR = str(exc)
        logger.error("Reseller bot manager init FAILED: %s", exc, exc_info=True)

    # Start background tasks (auto-scaling)
    if settings.ENVIRONMENT != "test":
        _autoscaling_task = asyncio.create_task(autoscaling_loop())
        logger.info("Background tasks started")

    yield  # App runs here

    # ===== Shutdown =====
    # Stop background tasks
    if _autoscaling_task:
        _autoscaling_task.cancel()
        try:
            await _autoscaling_task
        except asyncio.CancelledError:
            pass
        logger.info("Background tasks stopped")

    logger.info("Shutting down FluxVPN Worker/API Service...")


# Create FastAPI app
app = FastAPI(
    title="FluxVPN Worker/API",
    description="Backend orchestration service for FluxVPN platform",
    version="1.0.0",
    docs_url="/api/docs" if settings.DEBUG else None,
    redoc_url="/api/redoc" if settings.DEBUG else None,
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Exception handlers
# ---------------------------------------------------------------------------
@app.exception_handler(ValueError)
async def value_error_handler(_request: Request, exc: ValueError):
    """Client-input / state validation errors -> HTTP 400.

    Operator/admin APIs raise ValueError for actionable validation failures
    (e.g. pinning a TLD with 0 healthy domains). Server-side misconfig uses
    ConfigurationError instead (see below).
    """
    return JSONResponse(status_code=400, content={"detail": str(exc)})


@app.exception_handler(ConfigurationError)
async def configuration_error_handler(_request: Request, exc: ConfigurationError):
    """Server-side misconfiguration -> HTTP 500 (detail logged, not leaked)."""
    logger.error("Server configuration error: %s", exc)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server configuration error"},
    )


@app.middleware("http")
async def telemetry_middleware(_request: Request, call_next):
    """
    Capture API latency/request telemetry with buffered persistence.
    """
    started = perf_counter()
    try:
        return await call_next(_request)
    finally:
        elapsed_ms = (perf_counter() - started) * 1000.0
        admin_health_metrics.record_request(elapsed_ms)

        if admin_health_metrics.should_flush():
            db = SessionLocal()
            try:
                admin_health_metrics.flush_pending(db)
            except Exception as exc:
                logger.debug("Failed to flush API telemetry batch: %s", str(exc))
            finally:
                db.close()


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "service": "FluxVPN Worker/API",
        "version": "1.0.0",
        "status": "running",
        "environment": settings.ENVIRONMENT,
    }


@app.get("/health")
async def health_check():
    """Health check endpoint — includes bot_manager sub-status."""
    return {
        "status": "healthy" if _BOT_MANAGER_STATUS == "ok" else "degraded",
        "service": "worker-api",
        "environment": settings.ENVIRONMENT,
        "bot_manager": {
            "status": _BOT_MANAGER_STATUS,
            "error": _BOT_MANAGER_ERROR,
        },
    }


@app.get("/health/db")
async def health_check_database():
    """Database health check"""
    try:
        from app.core.database import SessionLocal

        db = SessionLocal()
        db.execute(text("SELECT 1"))
        db.close()
        return {"status": "ok", "database": "connected"}
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        return JSONResponse(
            status_code=503,
            content={"status": "error", "database": "disconnected", "error": str(e)},
        )


@app.get("/health/redis")
async def health_check_redis():
    """Redis health check"""
    try:
        from app.core.redis_client import get_redis

        redis = get_redis()
        if redis is None:
            return {"status": "ok", "redis": "disabled"}
        redis.ping()
        return {"status": "ok", "redis": "connected"}
    except Exception as e:
        logger.error(f"Redis health check failed: {e}")
        return JSONResponse(
            status_code=503,
            content={"status": "error", "redis": "disconnected", "error": str(e)},
        )


# Include API routers
from app.api.v1.endpoints import (
    admin,
    admin_api,
    admin_dashboard,
    admin_packages_api,
    auth,
    auth_v2,
    bot_config_api,
    broadcast_api,
    credentials,
    end_user,
    fdm,
    free_config_api,
    free_config_global_api,
    internal_v2,
    ip_management,
    migrate,
    mvp,
    nodes,
    payments,
    referral_api,
    reseller_bot_webhook,
    routing_rules_api,
    subscriptions,
    super_admin,
    super_admin_bots_api,
    support,
    user_orders_api,
    users,
    webhooks,
)

# Week 5 routers
app.include_router(auth.router, prefix="/api/v1")

# Reseller Platform auth (username+password, role-based JWT)
app.include_router(auth_v2.router, prefix="/api/v1")
app.include_router(users.router, prefix="/api/v1")
app.include_router(subscriptions.router, prefix="/api/v1")
app.include_router(payments.router, prefix="/api/v1")

# Week 6 routers
app.include_router(ip_management.router, prefix="/api/v1")
app.include_router(support.router, prefix="/api/v1")
app.include_router(credentials.router, prefix="/api/v1")
app.include_router(admin.router, prefix="/api/v1")

# Week 7 routers (Payment webhooks)
app.include_router(webhooks.router, prefix="/api/v1")

# Phase 5 routers (Protocol Deployments)
app.include_router(nodes.router, prefix="/api/v1")

# Admin Dashboard (comprehensive management)
app.include_router(admin_dashboard.router, prefix="/api/v1")

# Database migrations
app.include_router(migrate.router, prefix="/api/v1")

# MVP endpoints (simplified public API)
app.include_router(mvp.router, prefix="/api/v1")

# Flux DNS Manager (FDM) endpoints
app.include_router(fdm.router, prefix="/api/v1")

# Super Admin (Reseller Platform management)
app.include_router(super_admin.router, prefix="/api/v1")

# Admin API (Admin CRUD: users, connections, wallet, regions, analytics)
app.include_router(admin_api.router, prefix="/api/v1")

# Bot Config (Reseller bot registration CRUD)
app.include_router(bot_config_api.router, prefix="/api/v1")

app.include_router(broadcast_api.router, prefix="/api/v1")
app.include_router(broadcast_api.superadmin_router, prefix="/api/v1")

# Super Admin - Bot management (platform-wide)
app.include_router(super_admin_bots_api.router, prefix="/api/v1")

# Admin Packages (Reseller subscription package CRUD)
app.include_router(admin_packages_api.router, prefix="/api/v1")

# User Orders (Reseller order management)
app.include_router(user_orders_api.router, prefix="/api/v1")

# Free Config (Reseller shared free public config)
app.include_router(free_config_api.router, prefix="/api/v1")

# Free Config - Superadmin global settings, verification token, channels
app.include_router(free_config_global_api.router, prefix="/api/v1")

# Routing rules (reseller ban list + website allow/direct)
app.include_router(routing_rules_api.router, prefix="/api/v1")

# Referral program (per-reseller config + earnings)
app.include_router(referral_api.router, prefix="/api/v1")

# End User portal (read-only: connections, usage, profile)
app.include_router(end_user.router, prefix="/api/v1")

# Internal API for VPN containers (traffic reports, credential lookups)
app.include_router(internal_v2.router, prefix="/api/v1")

# Reseller bot webhook receiver (root-level, NOT under /api/v1)
app.include_router(reseller_bot_webhook.router)


# =============================================================================
# BACKGROUND TASKS (Auto-scaling scheduler)
# =============================================================================


async def autoscaling_loop():
    """Background loop for auto-scaling checks"""
    from app.core.database import SessionLocal
    from app.services.autoscaling import AutoScaler

    logger.info("Auto-scaling background task started")
    check_interval = 300  # 5 minutes

    while True:
        try:
            await asyncio.sleep(check_interval)

            db = SessionLocal()
            try:
                autoscaler = AutoScaler()
                if autoscaler.global_rule.enabled:
                    result = await autoscaler.check_and_scale(db)
                    if result.get("actions"):
                        logger.info(
                            f"Auto-scaling: {len(result['actions'])} actions taken"
                        )
            finally:
                db.close()

        except asyncio.CancelledError:
            logger.info("Auto-scaling background task cancelled")
            break
        except Exception as e:
            logger.error(f"Auto-scaling check error: {e}")
            await asyncio.sleep(60)  # Wait 1 minute on error


if __name__ == "__main__":
    import uvicorn

    # nosec: B104 - Binding to 0.0.0.0 is necessary for reachable container services
    uvicorn.run(app, host="0.0.0.0", port=8080, reload=settings.DEBUG)
