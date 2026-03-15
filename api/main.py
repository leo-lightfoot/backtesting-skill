import asyncio
import sys
from pathlib import Path

# Make scripts/ importable (run_backtest_from_schema, schema_adapter, strategies)
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from fastapi import FastAPI, HTTPException
from fastapi.encoders import jsonable_encoder
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, field_validator
from typing import Any

from api.templates import TEMPLATES, TEMPLATES_BY_ID
from api.job_store import create_job, get_job, set_queued, set_running, set_done, set_error
from run_backtest_from_schema import run_backtest

_FRONTEND = Path(__file__).parent.parent / "frontend"

app = FastAPI(title="Backtesting API", version="0.1.0")
app.mount("/static", StaticFiles(directory=str(_FRONTEND)), name="static")


# ---------------------------------------------------------------------------
# Request model
# ---------------------------------------------------------------------------

class BacktestRequest(BaseModel):
    template: str
    symbols: list[str]
    frequency: str = "daily"
    start: str
    end: str
    initial_cash: float = 100_000

    # two-tier strategy params — free-form dict, validated by the runner
    strategy: dict[str, Any] = {}

    # advanced block — optional, same structure as schema advanced block
    advanced: dict[str, Any] = {}

    # if True (default), fetch and ingest the bundle automatically when missing
    ingest_if_missing: bool = True

    @field_validator("template")
    @classmethod
    def template_must_exist(cls, v):
        if v not in TEMPLATES_BY_ID:
            raise ValueError(
                f"Unknown template '{v}'. "
                f"Available: {list(TEMPLATES_BY_ID.keys())}"
            )
        return v

    @field_validator("symbols")
    @classmethod
    def symbols_not_empty(cls, v):
        if not v:
            raise ValueError("symbols must contain at least one ticker")
        return [s.upper().strip() for s in v]


# ---------------------------------------------------------------------------
# Background task
# ---------------------------------------------------------------------------

# SQLite (assets.sqlite) does not support concurrent writers.
# This lock ensures only one backtest runs at a time.
_backtest_lock = asyncio.Lock()


async def _run_job(job_id: str, schema: dict, ingest_if_missing: bool) -> None:
    set_queued(job_id)
    async with _backtest_lock:
        set_running(job_id)
        try:
            result = await run_backtest(schema, ingest_if_missing=ingest_if_missing)
            set_done(job_id, jsonable_encoder(result))
        except Exception as exc:
            set_error(job_id, str(exc))


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/", include_in_schema=False)
async def serve_ui():
    return FileResponse(str(_FRONTEND / "index.html"))


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/templates")
async def get_templates():
    """Return all available strategy templates with their parameter metadata."""
    return TEMPLATES


@app.post("/backtest", status_code=202)
async def backtest(req: BacktestRequest):
    """Submit a backtest job. Returns a job_id immediately.

    Poll GET /jobs/{job_id} to check status and retrieve the result.
    Status values: pending -> running -> done | error
    """
    # Build schema dict in two-tier format
    schema = {
        "template": req.template,
        "symbols": req.symbols,
        "frequency": req.frequency,
        "start": req.start,
        "end": req.end,
        "initial_cash": req.initial_cash,
    }
    if req.strategy:
        schema["strategy"] = req.strategy

    # Always enable allow_yahoo_ingest so the runner permits auto-fetching
    advanced = dict(req.advanced)
    advanced["allow_yahoo_ingest"] = True
    schema["advanced"] = advanced

    job_id = create_job()
    asyncio.create_task(_run_job(job_id, schema, req.ingest_if_missing))

    return {"job_id": job_id, "status": "pending"}


@app.get("/jobs/{job_id}")
async def get_job_status(job_id: str):
    """Poll for backtest job status and result.

    Returns:
        status=pending|running  — job not yet complete, poll again
        status=done             — result field contains the full backtest output
        status=error            — detail field contains the error message
    """
    job = get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")
    return job
