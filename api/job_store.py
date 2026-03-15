"""In-memory job store for async backtest jobs.

Each job moves through: pending -> queued -> running -> done | error
  pending  — just created, task not yet scheduled
  queued   — waiting for the backtest lock (another job is running)
  running  — actively executing
  done     — completed successfully
  error    — failed
"""
from datetime import datetime, timezone
from uuid import uuid4

# job_id -> job dict
_jobs: dict[str, dict] = {}


def create_job() -> str:
    job_id = str(uuid4())[:8]
    _jobs[job_id] = {
        "job_id": job_id,
        "status": "pending",
        "result": None,
        "detail": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    return job_id


def get_job(job_id: str) -> dict | None:
    return _jobs.get(job_id)


def set_queued(job_id: str) -> None:
    _jobs[job_id]["status"] = "queued"


def set_running(job_id: str) -> None:
    _jobs[job_id]["status"] = "running"


def set_done(job_id: str, result: dict) -> None:
    _jobs[job_id]["status"] = "done"
    _jobs[job_id]["result"] = result


def set_error(job_id: str, detail: str) -> None:
    _jobs[job_id]["status"] = "error"
    _jobs[job_id]["detail"] = detail
