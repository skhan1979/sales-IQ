"""
Sales IQ - FastAPI Application Entry Point
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.api.v1.router import api_router
from app.middleware.audit import AuditMiddleware
from app.middleware.i18n import I18nMiddleware
from app.middleware.performance import PerformanceMiddleware
from app.middleware.error_handler import register_error_handlers

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown events."""
    # Startup
    print(f"[START] Starting {settings.APP_NAME} v0.1.0 ({settings.APP_ENV})")
    yield
    # Shutdown
    print(f"[STOP] Shutting down {settings.APP_NAME}")


app = FastAPI(
    title=settings.APP_NAME,
    description="Agentic Revenue Intelligence Platform for GCC Mid-Market",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url="/redoc" if settings.DEBUG else None,
)

# Register structured error handlers (must be before middleware)
register_error_handlers(app)

# Middleware (order matters — outermost first)
app.add_middleware(PerformanceMiddleware)
app.add_middleware(I18nMiddleware)
app.add_middleware(AuditMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.BACKEND_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API Router
app.include_router(api_router, prefix=settings.API_V1_PREFIX)


@app.get("/health")
async def health_check():
    """Health check endpoint for Docker / load balancer."""
    return {
        "status": "healthy",
        "app": settings.APP_NAME,
        "version": "0.1.0",
        "environment": settings.APP_ENV,
    }
