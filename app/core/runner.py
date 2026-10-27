"""
Pipeline execution orchestrator and background runner.

Purpose:
    Manages asynchronous background thread execution of pipeline stages (s01-s07),
    state transitions, cooperative cancellation checks, stage checkpointing,
    and automatic recovery of interrupted jobs upon application restart.

Design Notes:
    - Single-worker ThreadPoolExecutor guarantees that only one pipeline runs at a time,
      respecting SQLite concurrency and free-tier LLM rate limits.
"""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import time
from typing import Any, Callable, Dict, List, Optional
import uuid

from app.core.config import settings
from app.core.db import get_db_context
from app.core.errors import ReviewIntelError, RunCancelledError
from app.core.logging import run_logger_context
from app.core.models import Run, RunStage, RunWarning, utc_now

logger = logging.getLogger("review_intel.runner")

# Single-worker background executor for deterministic serial pipeline execution
_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="pipeline_worker")

# Cancellation registry to track cooperative stop requests between batches
_cancel_requested: Dict[str, bool] = {}
# Active run tracking for graceful SIGTERM shutdown
_active_run_id: Optional[str] = None


def set_active_run_id(run_id: Optional[str]) -> None:
    """Track the currently executing run ID."""
    global _active_run_id
    _active_run_id = run_id


def get_active_run_id() -> Optional[str]:
    """Retrieve the currently executing run ID."""
    return _active_run_id


def handle_sigterm_graceful(signum=None, frame=None):
    """Signal handler for SIGTERM to cancel active run before shutdown."""
    active = get_active_run_id()
    if active:
        logger.warning("SIGTERM received. Requesting cooperative cancel for active run %s", active)
        request_run_cancellation(active)


def request_run_cancellation(run_id: str) -> bool:
    """Request cooperative cancellation for an active run."""
    _cancel_requested[run_id] = True
    return True


def is_run_cancelled(run_id: str) -> bool:
    """Check if cancellation has been requested for a run."""
    return _cancel_requested.get(run_id, False)


def clear_run_cancellation(run_id: str) -> None:
    """Clear cancellation flag for a run."""
    _cancel_requested.pop(run_id, None)


def recover_interrupted_runs() -> int:
    """
    On system startup, marks any runs left in 'running' state as 'interrupted'.
    This prevents permanently stuck states when containers or processes restart.
    Returns the count of recovered runs.
    """
    count = 0
    with get_db_context() as db:
        stuck_runs = db.query(Run).filter(Run.status == "running").all()
        for r in stuck_runs:
            r.status = "interrupted"
            r.error_code = "INTERRUPTED"
            r.error_message = "Container or application process restarted while run was active. Run can be resumed."
            count += 1
        if count > 0:
            db.commit()
    return count


def execute_pipeline(run_id: str, reuse_snapshot: bool = False, resume_from_stage: Optional[str] = None) -> None:
    """
    Main orchestration loop executing pipeline stages s01 through s07.
    """
    set_active_run_id(run_id)
    clear_run_cancellation(run_id)
    logger.info("Starting pipeline execution for run_id=%s (reuse_snapshot=%s, resume=%s)", run_id, reuse_snapshot, resume_from_stage)

    # List of sequential pipeline stages
    stage_names = [
        "s01_collect",
        "s02_clean",
        "s03_sample_taxonomy",
        "s04_classify",
        "s05_reconcile",
        "s06_summarize",
        "s07_aggregate",
    ]

    with get_db_context() as db:
        run = db.query(Run).filter(Run.id == run_id).first()
        if not run:
            logger.error("Run %s not found in database.", run_id)
            return

        run.status = "running"
        run.started_at = utc_now()
        db.commit()

        # Initialize stage rows if not already present
        existing_stages = {s.stage_name: s for s in run.stages}
        for s_name in stage_names:
            if s_name not in existing_stages:
                stage_row = RunStage(
                    run_id=run_id,
                    stage_name=s_name,
                    status="pending",
                )
                db.add(stage_row)
        db.commit()

    run_dir = settings.get_run_dir(run_id)

    # Pipeline execution loop
    try:
        skip_prior = bool(resume_from_stage)

        for s_name in stage_names:
            if is_run_cancelled(run_id):
                raise RunCancelledError()

            # If resuming, skip stages that completed prior to resume_from_stage
            if skip_prior:
                if s_name == resume_from_stage:
                    skip_prior = False
                else:
                    with get_db_context() as db:
                        stg = db.query(RunStage).filter(RunStage.run_id == run_id, RunStage.stage_name == s_name).first()
                        if stg and stg.status == "completed":
                            logger.info("Skipping already completed stage %s for run %s", s_name, run_id)
                            continue

            # Check cooperative cancel again before starting stage
            if is_run_cancelled(run_id):
                raise RunCancelledError()

            _run_stage(run_id, s_name, reuse_snapshot)

        # All stages finished successfully
        with get_db_context() as db:
            run = db.query(Run).filter(Run.id == run_id).first()
            if run and run.status != "cancelled":
                run.status = "completed"
                run.finished_at = utc_now()
                db.commit()
        logger.info("Pipeline completed successfully for run_id=%s", run_id)

    except RunCancelledError:
        logger.warning("Pipeline cancelled for run_id=%s", run_id)
        with get_db_context() as db:
            run = db.query(Run).filter(Run.id == run_id).first()
            if run:
                run.status = "cancelled"
                run.error_code = "RUN_CANCELLED"
                run.error_message = "Run was cancelled by user request."
                run.finished_at = utc_now()
                db.commit()
    except ReviewIntelError as rie:
        logger.error("Pipeline failed with domain error on run_id=%s: %s", run_id, rie.message)
        _record_run_failure(run_id, rie.code, rie.message, rie.details)
    except Exception as exc:
        logger.exception("Unexpected error executing pipeline for run_id=%s: %s", run_id, exc)
        _record_run_failure(run_id, "INTERNAL_ERROR", str(exc), {})
    finally:
        set_active_run_id(None)
        clear_run_cancellation(run_id)


def _run_stage(run_id: str, stage_name: str, reuse_snapshot: bool) -> None:
    """Executes a single pipeline stage by dispatching to its module."""
    start_time = utc_now()

    with get_db_context() as db:
        stage = db.query(RunStage).filter(RunStage.run_id == run_id, RunStage.stage_name == stage_name).first()
        if stage:
            stage.status = "running"
            stage.started_at = start_time
            stage.error_message = None
            db.commit()

    with run_logger_context(run_id, stage_name) as stage_logger:
        stage_logger.info(">>> Starting stage: %s", stage_name)
        stage_summary: Dict[str, Any] = {}

        try:
            # Dynamically dispatch to the pipeline stage function
            if stage_name == "s01_collect":
                from app.pipeline.s01_collect import run_stage as run_s01
                stage_summary = run_s01(run_id, reuse_snapshot=reuse_snapshot)
            elif stage_name == "s02_clean":
                from app.pipeline.s02_clean import run_stage as run_s02
                stage_summary = run_s02(run_id)
            elif stage_name == "s03_sample_taxonomy":
                from app.pipeline.s03_sample_taxonomy import run_stage as run_s03
                stage_summary = run_s03(run_id)
            elif stage_name == "s04_classify":
                from app.pipeline.s04_classify import run_stage as run_s04
                stage_summary = run_s04(run_id)
            elif stage_name == "s05_reconcile":
                from app.pipeline.s05_reconcile import run_stage as run_s05
                stage_summary = run_s05(run_id)
            elif stage_name == "s06_summarize":
                from app.pipeline.s06_summarize import run_stage as run_s06
                stage_summary = run_s06(run_id)
            elif stage_name == "s07_aggregate":
                from app.pipeline.s07_aggregate import run_stage as run_s07
                stage_summary = run_s07(run_id)
            else:
                raise ValueError(f"Unknown stage name: {stage_name}")

            finish_time = utc_now()
            duration = (finish_time - start_time).total_seconds()
            stage_logger.info("<<< Completed stage %s in %.2fs. Summary: %s", stage_name, duration, stage_summary)

            with get_db_context() as db:
                stage = db.query(RunStage).filter(RunStage.run_id == run_id, RunStage.stage_name == stage_name).first()
                if stage:
                    stage.status = "completed"
                    stage.finished_at = finish_time
                    stage.duration_seconds = duration
                    stage.output_summary = json.dumps(stage_summary)
                    db.commit()

        except Exception as exc:
            finish_time = utc_now()
            duration = (finish_time - start_time).total_seconds()
            stage_logger.exception("Failed stage %s: %s", stage_name, exc)

            with get_db_context() as db:
                stage = db.query(RunStage).filter(RunStage.run_id == run_id, RunStage.stage_name == stage_name).first()
                if stage:
                    stage.status = "failed"
                    stage.finished_at = finish_time
                    stage.duration_seconds = duration
                    stage.error_message = str(exc)
                    db.commit()
            raise


def _record_run_failure(run_id: str, code: str, message: str, details: Dict[str, Any]) -> None:
    """Persists run error status in SQLite and writes error.json in run dir."""
    run_dir = settings.get_run_dir(run_id)
    error_payload = {
        "run_id": run_id,
        "error_code": code,
        "error_message": message,
        "details": details,
        "timestamp": utc_now().isoformat(),
    }
    try:
        error_file = run_dir / "error.json"
        with open(error_file, "w", encoding="utf-8") as f:
            json.dump(error_payload, f, indent=2)
    except Exception as io_err:
        logger.error("Failed to write error.json for run %s: %s", run_id, io_err)

    with get_db_context() as db:
        run = db.query(Run).filter(Run.id == run_id).first()
        if run:
            run.status = "failed"
            run.error_code = code
            run.error_message = message
            run.error_details = json.dumps(details)
            run.finished_at = utc_now()
            db.commit()


def launch_run_in_background(run_id: str, reuse_snapshot: bool = False, resume_from_stage: Optional[str] = None) -> None:
    """Submit pipeline task to the single-worker background thread executor."""
    _executor.submit(execute_pipeline, run_id, reuse_snapshot, resume_from_stage)
