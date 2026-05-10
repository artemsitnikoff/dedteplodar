"""FastAPI admin application for Teplodar RAG knowledge base."""
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from admin.routers import products, categories, documents, chunks, faq, pipeline, query_logs, faq_entries, eval as eval_router

app = FastAPI(
    title="Teplodar Admin API",
    description="Admin interface for Teplodar RAG knowledge base",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
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
