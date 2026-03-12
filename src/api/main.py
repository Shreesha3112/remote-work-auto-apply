import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from src.database import init_db
from src.api.routes import jobs, scrape, profile

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize DB on startup."""
    logger.info("Initializing database...")
    init_db()
    logger.info("Database ready.")
    yield
    logger.info("Shutting down.")


app = FastAPI(
    title="Remote Work Auto-Apply",
    description="Job discovery and matching for remote Gen AI roles",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# API routes
app.include_router(jobs.router)
app.include_router(scrape.router)
app.include_router(profile.router)


@app.get("/api/stats")
async def get_stats():
    """Dashboard stats: counts by status and source."""
    from src.database import get_session
    from src.models import Job
    from sqlalchemy import func

    with get_session() as session:
        total = session.query(func.count(Job.id)).scalar()

        status_counts = dict(
            session.query(Job.status, func.count(Job.id))
            .group_by(Job.status)
            .all()
        )
        source_counts = dict(
            session.query(Job.source, func.count(Job.id))
            .group_by(Job.source)
            .all()
        )
        avg_score = session.query(func.avg(Job.score)).filter(Job.score.isnot(None)).scalar()

    return {
        "total": total,
        "by_status": status_counts,
        "by_source": source_counts,
        "avg_score": round(avg_score, 1) if avg_score else None,
    }


@app.get("/api/health")
async def health():
    from src.llm.client import llm_client
    vllm_ok = await llm_client.is_available()
    return {"status": "ok", "vllm_available": vllm_ok}


# Serve frontend
frontend_dir = Path("frontend")
if frontend_dir.exists():
    app.mount("/static", StaticFiles(directory=str(frontend_dir)), name="static")

    @app.get("/", include_in_schema=False)
    async def serve_frontend():
        return FileResponse(str(frontend_dir / "index.html"))
