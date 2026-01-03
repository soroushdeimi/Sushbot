"""FastAPI application for admin panel."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from api.routes import (
    admin,
    auth,
    panels,
    payments,
    product_categories,
    products,
    refunds,
    reports,
    resellers,
    services,
    subscription,
    tickets,
    transfers,
    users,
)
from config.settings import settings
from database.session import close_db, init_db
from services.migrations import run_migrations


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for FastAPI startup and shutdown."""
    # Startup
    logger.info("Initializing database...")
    try:
        await run_migrations()
    except Exception as e:
        logger.error(f"Migrations failed: {e}", exc_info=e)
    await init_db()
    logger.info("Database initialized")
    yield
    # Shutdown
    logger.info("Shutting down API...")
    await close_db()
    logger.info("API shutdown complete")


# Create FastAPI app
app = FastAPI(
    title="SushBotSeller Admin Panel",
    description="Admin panel API for SushBotSeller VPN Bot",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS middleware - SECURITY: Never use allow_origins=["*"] with credentials!
# Configure CORS_ORIGINS in .env for your admin dashboard domain(s)
_cors_origins = settings.cors_origins if settings.cors_origins else []
if not _cors_origins:
    # Default: restrictive same-origin policy when no origins configured
    logger.warning(
        "CORS_ORIGINS not configured - API will reject cross-origin requests. "
        "Set CORS_ORIGINS=['https://your-admin-panel.com'] in .env for production."
    )
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,  # Explicitly configured origins only
    allow_credentials=True if _cors_origins else False,  # Only with explicit origins
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH"],  # Explicit methods
    allow_headers=["Authorization", "Content-Type", "X-Requested-With"],  # Explicit headers
)


# Request body size limiter - DoS protection
@app.middleware("http")
async def limit_request_body_size(request, call_next):
    """Reject oversized request bodies to prevent memory exhaustion attacks."""
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > settings.max_request_body_bytes:
                from starlette.responses import JSONResponse

                return JSONResponse(
                    status_code=413,
                    content={
                        "detail": f"Request body too large. Max: {settings.max_request_body_bytes // (1024 * 1024)}MB"
                    },
                )
        except ValueError:
            pass  # Invalid content-length header, let it proceed
    return await call_next(request)


# Include routers
app.include_router(auth.router, prefix="/api/auth", tags=["Authentication"])
app.include_router(admin.router, prefix="/api/admin", tags=["Admin"])
app.include_router(users.router, prefix="/api/users", tags=["Users"])
app.include_router(panels.router, prefix="/api/panels", tags=["Panels"])
app.include_router(products.router, prefix="/api/products", tags=["Products"])
app.include_router(
    product_categories.router, prefix="/api/product-categories", tags=["Product Categories"]
)
app.include_router(services.router, prefix="/api/services", tags=["Services"])
app.include_router(payments.router, prefix="/api/payments", tags=["Payments"])
app.include_router(tickets.router, prefix="/api/tickets", tags=["Tickets"])
app.include_router(subscription.router, prefix="/api", tags=["Subscription"])
app.include_router(reports.router, prefix="/api/reports", tags=["Reports"])
app.include_router(refunds.router, prefix="/api/refunds", tags=["Refunds"])
app.include_router(transfers.router, prefix="/api/transfers", tags=["Transfers"])
app.include_router(resellers.router, prefix="/api/resellers", tags=["Resellers"])


@app.get("/")
async def root() -> dict[str, str]:
    """Root endpoint."""
    return {"message": "SushBotSeller Admin Panel API", "version": "1.0.0"}


@app.get("/health")
async def health() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "api.main:app",
        host=settings.web_panel_host,
        port=settings.web_panel_port,
        reload=True,
    )
