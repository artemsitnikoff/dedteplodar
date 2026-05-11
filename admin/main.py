"""FastAPI admin application for Teplodar RAG knowledge base."""
import base64
import os
import secrets
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

from admin.routers import products, categories, documents, chunks, faq, pipeline, query_logs, faq_entries, eval as eval_router

# ── HTTP Basic auth on every request (except static assets and health) ───────────────────
_ADMIN_USER = os.getenv("ADMIN_USER", "admin")
_ADMIN_PASS = os.getenv("ADMIN_PASS", "admin555")
_AUTH_FREE_PATHS = {"/health"}
_AUTH_FREE_PREFIXES = ("/assets/", "/vite.svg", "/favicon.ico")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Security check: refuse to serve prod with the well-known default password.
    # Moved out of module-level so pytest collection / `import admin.main`
    # don't crash; the check only runs when the app actually starts.
    if _ADMIN_PASS == "admin555" and os.getenv("ADMIN_ALLOW_DEFAULT_PASS") != "1":
        raise RuntimeError(
            "Default password detected! Set ADMIN_PASS environment variable or "
            "set ADMIN_ALLOW_DEFAULT_PASS=1 to allow default password in development."
        )
    yield


app = FastAPI(
    title="Teplodar Admin API",
    description="Admin interface for Teplodar RAG knowledge base",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)


def _unauthorized() -> Response:
    return Response(
        status_code=401,
        content="Unauthorized",
        headers={"WWW-Authenticate": 'Basic realm="DedTeplodar Admin"'},
    )


@app.middleware("http")
async def basic_auth(request: Request, call_next):
    path = request.url.path

    # Skip auth for public static assets and health endpoint
    if path in _AUTH_FREE_PATHS or path.startswith(_AUTH_FREE_PREFIXES):
        return await call_next(request)

    header = request.headers.get("authorization", "")
    if not header.startswith("Basic "):
        return _unauthorized()
    try:
        decoded = base64.b64decode(header[6:]).decode("utf-8")
        user, _, password = decoded.partition(":")
    except Exception:
        return _unauthorized()

    if not (
        secrets.compare_digest(user, _ADMIN_USER)
        and secrets.compare_digest(password, _ADMIN_PASS)
    ):
        return _unauthorized()

    return await call_next(request)


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,  # Can't use credentials with allow_origins=["*"]
    allow_methods=["*"],
    allow_headers=["*"],
)

# API routers — registered first so they take priority over SPA fallback
app.include_router(products.router, prefix="/api/v1")
app.include_router(categories.router, prefix="/api/v1")
app.include_router(documents.router, prefix="/api/v1")
app.include_router(chunks.router, prefix="/api/v1")
app.include_router(faq.router, prefix="/api/v1")
app.include_router(pipeline.router, prefix="/api/v1")
app.include_router(query_logs.router, prefix="/api/v1")
app.include_router(faq_entries.router, prefix="/api/v1")
app.include_router(eval_router.router, prefix="/api/v1")


@app.get("/health")
async def health():
    return {"status": "healthy"}


# Serve Vue SPA (static assets + index.html fallback)
_FRONTEND_DIST = Path(__file__).parent / "frontend" / "dist"

if _FRONTEND_DIST.is_dir():
    app.mount("/assets", StaticFiles(directory=str(_FRONTEND_DIST / "assets")), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa_fallback(full_path: str):
        # Never serve SPA for API routes — let FastAPI raise 404 normally
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="API endpoint not found")
        return FileResponse(str(_FRONTEND_DIST / "index.html"))
