from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.db.base import Base
from app.db.session import engine
from app.api.router import api_router
from app.middleware.logging import LoggingMiddleware
from app.middleware.exceptions import ExceptionHandlerMiddleware
from app.middleware.audit_logging import AuditLoggingMiddleware


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Asynchronous lifespan manager.
    Initializes PostgreSQL tables on service startup.
    """
    print("Initializing Database tables...")
    Base.metadata.create_all(bind=engine)
    print("Database tables initialized successfully.")
    yield
    print("Shutting down backend services...")


app = FastAPI(
    title=settings.PROJECT_NAME,
    description="Enterprise-grade high-fidelity Bank Statement and internal ledger Reconciliation Engine.",
    version="1.0.0",
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    docs_url=f"{settings.API_V1_STR}/docs",
    redoc_url=f"{settings.API_V1_STR}/redoc",
    lifespan=lifespan,
    debug=settings.DEBUG
)

# 1. Custom Global Error Handling Middleware (Inbound-Outbound Interceptor)
app.add_middleware(ExceptionHandlerMiddleware)

# 2. Custom Logging & Metric Middleware
app.add_middleware(LoggingMiddleware)

# 2.5. Custom Cryptographic Immutable Audit Logging Middleware
app.add_middleware(AuditLoggingMiddleware)

# 3. CORS Middleware Configuration
if settings.BACKEND_CORS_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[str(origin) for origin in settings.BACKEND_CORS_ORIGINS],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

# 4. Versioned API v1 Router Registration
app.mount("", app)  # Sub-app or route mount mapping
app.include_router(api_router, prefix=settings.API_V1_STR)


@app.get("/", tags=["healthcheck"])
def read_root():
    """
    Basic health check landing page.
    """
    return {
        "success": True,
        "message": f"Welcome to the {settings.PROJECT_NAME} API backplane.",
        "version": "1.0.0",
        "documentation": f"{settings.API_V1_STR}/docs"
    }
