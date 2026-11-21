"""
CI/CD Pipeline Runner Microservice - Build, Test & Deployment Automation
Simulates continuous integration pipelines with multi-stage verification
(lint, test, build, deploy). Detects failures, triggers Sentinel webhooks,
and re-runs pipelines upon receiving automated hotfix branches.
"""

import os
import time
import uuid
import logging
from typing import Any, Dict, List, Optional
from fastapi import FastAPI, BackgroundTasks, HTTPException
from pydantic import BaseModel
import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] [cicd_runner] %(message)s")
logger = logging.getLogger("cicd_runner")

app = FastAPI(
    title="DevOps Sentinel: CI/CD Pipeline Runner Microservice",
    version="1.1.0",
    description="Multi-stage CI/CD execution engine simulating GitHub Actions / ArgoCD pipeline runs"
)

SENTINEL_CORE_URL = os.getenv("SENTINEL_CORE_URL", "http://localhost:8000")

# In-memory pipeline runs database
PIPELINE_RUNS: Dict[str, Dict[str, Any]] = {}

class TriggerPipelineRequest(BaseModel):
    service_name: str = "web-api"
    branch: str = "main"
    commit_sha: Optional[str] = None
    commit_message: str = "feat: upgrade microservice core features"
    inject_failure: Optional[str] = None  # None, "missing_dependency", "test_failure", "build_failure"

class RemediatePipelineRequest(BaseModel):
    pipeline_id: str
    hotfix_branch: str
    patch_summary: str
    remediation_diff: Optional[str] = ""

def notify_sentinel_webhook(payload: Dict[str, Any]):
    """Notify Sentinel Core API of pipeline completion or failure"""
    try:
        url = f"{SENTINEL_CORE_URL}/api/webhook/github"
        res = requests.post(url, json=payload, timeout=5)
        logger.info("Notified Sentinel Core webhook (status=%s)", res.status_code)
    except Exception as exc:
        logger.warning("Could not reach Sentinel Core (%s): %s", SENTINEL_CORE_URL, exc)

def execute_pipeline(run_id: str, inject_failure: Optional[str] = None):
    """Execute multi-stage pipeline run"""
    run = PIPELINE_RUNS[run_id]
    stages = run["stages"]
    
    time.sleep(0.1)
    # Stage 1: Checkout & Lint
    stages["checkout"] = {"status": "SUCCESS", "duration_sec": 0.4}
    stages["lint"] = {"status": "SUCCESS", "duration_sec": 0.8}
    
    # Stage 2: Unit Tests
    if inject_failure == "test_failure":
        stages["test"] = {
            "status": "FAILED",
            "duration_sec": 1.2,
            "error": "AssertionError: 200 != 500 in test_order_fulfillment"
        }
        run["status"] = "FAILED"
        run["failed_stage"] = "test"
        run["logs"].append("FAILED tests/test_order.py::test_order_fulfillment - AssertionError")
        notify_sentinel_webhook({
            "ref": f"refs/heads/{run['branch']}",
            "repository": {"name": run["service_name"]},
            "commits": [{"id": run["commit_sha"], "message": run["commit_message"]}],
            "pipeline_status": "FAILED",
            "failed_stage": "test",
            "logs": run["logs"]
        })
        return

    stages["test"] = {"status": "SUCCESS", "duration_sec": 1.1}
    
    # Stage 3: Container Build
    if inject_failure == "missing_dependency":
        stages["build"] = {
            "status": "FAILED",
            "duration_sec": 1.8,
            "error": "ModuleNotFoundError: No module named 'pydantic'"
        }
        run["status"] = "FAILED"
        run["failed_stage"] = "build"
        run["logs"].append("Step 4/6: RUN python -m pytest")
        run["logs"].append("ModuleNotFoundError: No module named 'pydantic'")
        run["logs"].append("ERROR: Service failed to build container image. Non-zero exit code: 1")
        notify_sentinel_webhook({
            "ref": f"refs/heads/{run['branch']}",
            "repository": {"name": run["service_name"]},
            "commits": [{"id": run["commit_sha"], "message": run["commit_message"]}],
            "pipeline_status": "FAILED",
            "failed_stage": "build",
            "logs": "\n".join(run["logs"])
        })
        return

    stages["build"] = {"status": "SUCCESS", "duration_sec": 2.0}
    
    # Stage 4: Deploy Kubernetes
    stages["deploy"] = {"status": "SUCCESS", "duration_sec": 1.5}
    run["status"] = "SUCCESS"
    run["logs"].append(f"Deployment rolled out successfully to namespace 'production': {run['service_name']}")
    
    notify_sentinel_webhook({
        "ref": f"refs/heads/{run['branch']}",
        "repository": {"name": run["service_name"]},
        "commits": [{"id": run["commit_sha"], "message": run["commit_message"]}],
        "pipeline_status": "SUCCESS",
        "logs": "Pipeline executed successfully across all 4 stages."
    })

@app.get("/")
def get_root():
    return {
        "service": "cicd-pipeline-runner",
        "version": "1.1.0",
        "total_pipelines_run": len(PIPELINE_RUNS),
        "sentinel_core_url": SENTINEL_CORE_URL
    }

@app.get("/status")
def get_status():
    success_count = sum(1 for p in PIPELINE_RUNS.values() if p["status"] == "SUCCESS")
    failed_count = sum(1 for p in PIPELINE_RUNS.values() if p["status"] == "FAILED")
    running_count = sum(1 for p in PIPELINE_RUNS.values() if p["status"] == "RUNNING")
    return {
        "runner_status": "ONLINE",
        "total": len(PIPELINE_RUNS),
        "success": success_count,
        "failed": failed_count,
        "running": running_count,
        "latest_pipelines": list(PIPELINE_RUNS.values())[-5:]
    }

@app.get("/pipelines")
def list_pipelines():
    return {"pipelines": list(PIPELINE_RUNS.values())}

@app.get("/pipelines/{pipeline_id}")
def get_pipeline(pipeline_id: str):
    if pipeline_id not in PIPELINE_RUNS:
        raise HTTPException(status_code=404, detail="Pipeline run not found")
    return PIPELINE_RUNS[pipeline_id]

@app.post("/pipelines/trigger")
def trigger_pipeline(req: TriggerPipelineRequest, background_tasks: BackgroundTasks):
    """Trigger a new CI/CD pipeline execution"""
    run_id = f"pipe-{uuid.uuid4().hex[:8]}"
    commit_sha = req.commit_sha or uuid.uuid4().hex[:7]
    
    run_entry = {
        "id": run_id,
        "service_name": req.service_name,
        "branch": req.branch,
        "commit_sha": commit_sha,
        "commit_message": req.commit_message,
        "status": "RUNNING",
        "inject_failure": req.inject_failure,
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "stages": {
            "checkout": {"status": "PENDING"},
            "lint": {"status": "PENDING"},
            "test": {"status": "PENDING"},
            "build": {"status": "PENDING"},
            "deploy": {"status": "PENDING"}
        },
        "logs": [f"Triggered CI/CD pipeline {run_id} for {req.service_name} on branch {req.branch}"]
    }
    PIPELINE_RUNS[run_id] = run_entry
    
    background_tasks.add_task(execute_pipeline, run_id, req.inject_failure)
    return {"status": "QUEUED", "pipeline_id": run_id, "run": run_entry}

@app.post("/pipelines/remediate")
def remediate_pipeline(req: RemediatePipelineRequest, background_tasks: BackgroundTasks):
    """Trigger automated remediation pipeline re-run on hotfix branch"""
    if req.pipeline_id not in PIPELINE_RUNS:
        raise HTTPException(status_code=404, detail="Original pipeline not found")
        
    orig = PIPELINE_RUNS[req.pipeline_id]
    retest_id = f"pipe-hotfix-{uuid.uuid4().hex[:6]}"
    
    retest_entry = {
        "id": retest_id,
        "service_name": orig["service_name"],
        "branch": req.hotfix_branch,
        "commit_sha": uuid.uuid4().hex[:7],
        "commit_message": f"fix(sentinel): {req.patch_summary}",
        "status": "RUNNING",
        "inject_failure": None,  # Fix applied -> pass!
        "parent_pipeline_id": req.pipeline_id,
        "remediation_diff": req.remediation_diff,
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "stages": {
            "checkout": {"status": "PENDING"},
            "lint": {"status": "PENDING"},
            "test": {"status": "PENDING"},
            "build": {"status": "PENDING"},
            "deploy": {"status": "PENDING"}
        },
        "logs": [
            f"Remediation pipeline {retest_id} triggered for hotfix branch {req.hotfix_branch}",
            f"Applied automated patch: {req.patch_summary}"
        ]
    }
    PIPELINE_RUNS[retest_id] = retest_entry
    
    background_tasks.add_task(execute_pipeline, retest_id, None)
    return {
        "status": "HOTFIX_PIPELINE_QUEUED",
        "remediation_pipeline_id": retest_id,
        "hotfix_branch": req.hotfix_branch
    }

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8002"))
    uvicorn.run(app, host="0.0.0.0", port=port)
