"""Main FastAPI application entrypoint and frontend server."""

import logging
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import router as api_router
from app.config.settings import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

app = FastAPI(
    title=settings.APP_NAME,
    description="Local-First Financial Document Automation & AI Research Assistant",
    version="1.0.0",
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler ensuring every unhandled API exception is logged."""
    logger.exception(
        "Unhandled exception processing request [%s %s]: %s",
        request.method,
        request.url.path,
        exc,
    )
    return JSONResponse(
        status_code=500,
        content={
            "status": "error",
            "message": "An internal server error occurred while processing the request.",
            "error_details": str(exc),
            "path": request.url.path,
        },
    )


# Include API Router
app.include_router(api_router)

# Mount Frontend Static Assets
frontend_dir = Path(__file__).resolve().parent.parent / "frontend"
if frontend_dir.exists():
    try:
        app.mount("/static", StaticFiles(directory=str(frontend_dir)), name="static")
        logger.info("Mounted static frontend assets from: %s", frontend_dir)
    except Exception as exc:
        logger.exception("Failed to mount static directory '%s': %s", frontend_dir, exc)


@app.get("/", include_in_schema=False)
def serve_index():
    """Serve the single-page frontend application dashboard."""
    try:
        index_file = frontend_dir / "index.html"
        if index_file.exists():
            return FileResponse(str(index_file))
        logger.warning("Frontend index file not found at %s", index_file)
        return {"message": f"Welcome to {settings.APP_NAME}. API is running at /api/health"}
    except Exception as exc:
        logger.exception("Error serving frontend index page: %s", exc)
        return JSONResponse(status_code=500, content={"error": "Failed to load index page."})


@app.get("/graph", include_in_schema=False)
def serve_graph():
    """Serve the standalone Neo4j-style Knowledge Graph Database Visualizer."""
    try:
        graph_file = frontend_dir / "graph.html"
        if graph_file.exists():
            return FileResponse(str(graph_file))
        return serve_index()
    except Exception as exc:
        logger.exception("Error serving graph page: %s", exc)
        return JSONResponse(status_code=500, content={"error": "Failed to load graph explorer."})

