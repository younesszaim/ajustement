"""Tests for the in-memory progress boundary, independent of FastAPI."""

import time

from streamlit_app.jobs import PreviewJobManager


def wait_for_terminal(manager, job_id):
    """Poll briefly because the test calculation runs in another thread."""
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        job = manager.get(job_id)
        if job["status"] in {"COMPLETED", "FAILED"}:
            return job
        time.sleep(0.01)
    raise AssertionError("Preview job did not reach a terminal state")


def test_job_exposes_stage_progress_and_result():
    manager = PreviewJobManager(max_workers=1)

    def calculation(progress):
        progress("reportline_code", 0, 2, "RUNNING")
        progress("reportline_code", 1, 2, "COMPLETED")
        progress("calculate_buckets", 1, 2, "RUNNING")
        progress("calculate_buckets", 2, 2, "COMPLETED")
        return {"adjusted": {"amount": 250}}

    submitted = manager.submit(calculation)
    completed = wait_for_terminal(manager, submitted["job_id"])

    assert completed["status"] == "COMPLETED"
    assert completed["progress"] == 100
    assert completed["completed_stages"] == ["reportline_code", "calculate_buckets"]
    assert completed["result"]["adjusted"]["amount"] == 250


def test_job_captures_calculation_failure_for_the_ui():
    manager = PreviewJobManager(max_workers=1)

    def calculation(progress):
        progress("calculate_buckets", 0, 1, "RUNNING")
        raise ValueError("Maturity date is missing")

    submitted = manager.submit(calculation)
    failed = wait_for_terminal(manager, submitted["job_id"])

    assert failed["status"] == "FAILED"
    assert failed["current_stage"] == "calculate_buckets"
    assert failed["error"] == "Maturity date is missing"
