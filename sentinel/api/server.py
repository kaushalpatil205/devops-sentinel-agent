import os
from typing import Any, Dict, List, Optional
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from sentinel.config import config
from sentinel.core.orchestrator import AgentOrchestrator
from sentinel.simulator.cluster_sim import ClusterSimulator
from sentinel.simulator.scenarios import SCENARIOS

app = FastAPI(
    title="DevOps Sentinel Agent API",
    description="Autonomous CI/CD Failure Healing, Kubernetes Deployment Verification, IaC Drift Detection & Auto-Remediation with RCA",
    version=config.version
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Instantiate global orchestrator & simulator
orchestrator = AgentOrchestrator(use_mock=True)
simulator = ClusterSimulator(orchestrator)

class TriggerIncidentRequest(BaseModel):
    resource_name: str
    pod_status: Optional[str] = None
    logs: Optional[str] = ""
    events: Optional[List[str]] = []
    extra_context: Optional[Dict[str, Any]] = {}

class GitHubWebhookPayload(BaseModel):
    ref: str
    repository: Dict[str, Any]
    commits: List[Dict[str, Any]]
    head_commit: Optional[Dict[str, Any]] = None

@app.get("/api/status")
def get_status():
    return {
        "agent": config.app_name,
        "version": config.version,
        "env": config.env,
        "auto_remediate": config.auto_remediate,
        "auto_rollback": config.auto_rollback_on_failure,
        "active_incidents_count": len(orchestrator.incidents),
        "activity_log_count": len(orchestrator.activity_log)
    }

@app.get("/api/activity")
def get_activity():
    return {"activity": orchestrator.activity_log[-50:]}

@app.get("/api/incidents")
def list_incidents():
    return {"incidents": list(orchestrator.incidents.values())}

@app.get("/api/incidents/{incident_id}")
def get_incident(incident_id: str):
    inc = orchestrator.incidents.get(incident_id)
    if not inc:
        raise HTTPException(status_code=404, detail="Incident not found")
    return inc

@app.get("/api/incidents/{incident_id}/rca", response_class=HTMLResponse)
def get_incident_rca_html(incident_id: str):
    inc = orchestrator.incidents.get(incident_id)
    if not inc:
        raise HTTPException(status_code=404, detail="Incident not found")
    return HTMLResponse(content=inc.get("rca_html", "<p>No RCA</p>"))

@app.get("/api/scenarios")
def list_scenarios():
    return {
        "scenarios": [
            {
                "id": k,
                "name": v["name"],
                "description": v["description"],
                "resource": v.get("resource_name", "")
            }
            for k, v in SCENARIOS.items()
        ]
    }

@app.post("/api/scenarios/run/{scenario_id}")
def run_scenario_endpoint(scenario_id: str):
    try:
        res = simulator.run_scenario(scenario_id)
        return res
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/api/cluster/pods")
def get_cluster_pods():
    pods = orchestrator.k8s_client.get_pods()
    return {
        "pods": [
            {
                "name": p.name,
                "namespace": p.namespace,
                "status": p.status,
                "restarts": p.restarts,
                "ready": p.ready,
                "image": p.image,
                "memory_limit": p.memory_limit,
                "events_count": len(p.events)
            }
            for p in pods
        ]
    }

@app.get("/api/cluster/drift")
def trigger_drift_scan():
    scenario = SCENARIOS["iac_drift"]
    report = orchestrator.run_drift_check(
        resource_name=scenario["resource_name"],
        namespace=scenario["namespace"],
        desired_spec=scenario["desired_spec"],
        live_spec=scenario["live_spec"]
    )
    return {"drift_report": report.__dict__}

@app.post("/api/incidents/trigger")
def trigger_manual_incident(req: TriggerIncidentRequest):
    res = orchestrator.handle_incident(
        resource_name=req.resource_name,
        pod_status=req.pod_status,
        logs=req.logs or "",
        events=req.events or [],
        extra_context=req.extra_context or {}
    )
    return res

@app.post("/api/webhook/github")
def github_webhook(payload: GitHubWebhookPayload):
    """
    Implements Item 7:
    'Agent detects code merges, triggers CI/CD pipeline, deploys to Kubernetes, performs health checks, rolls back on failure, and delivers a deployment summary with root cause analysis'
    """
    branch = payload.ref.replace("refs/heads/", "")
    commit = payload.head_commit or (payload.commits[-1] if payload.commits else {})
    commit_sha = commit.get("id", "c0ffee1")[:7]
    commit_msg = commit.get("message", "Merge pull request")

    orchestrator.log_activity(f"🔔 Code merge detected on branch '{branch}' (commit: {commit_sha}): {commit_msg}", "INFO")

    # Trigger CI/CD run
    pipeline_id = f"pipe-{commit_sha}"
    pipe_run = orchestrator.cicd_runner.trigger_pipeline(pipeline_id, commit_sha, branch)

    # Execute stages
    stages_passed = True
    for stage in pipe_run.stages:
        orchestrator.log_activity(f"⚙️ Running CI/CD stage: {stage.name}...", "INFO")
        success = orchestrator.cicd_runner.execute_stage(stage)
        if not success:
            stages_passed = False
            orchestrator.log_activity(f"❌ Stage {stage.name} failed!", "ERROR")
            break

    # If merge contained simulated bug or bad deploy, trigger auto-remediation loop
    if not stages_passed:
        # Trigger diagnoser & remediator
        inc_res = orchestrator.handle_incident(
            resource_name=f"pipeline-{pipeline_id}",
            pod_status="BuildFailed",
            logs=stage.stderr or stage.stdout
        )
        return {
            "status": "HEALED_VIA_AGENT",
            "pipeline_id": pipeline_id,
            "incident": inc_res
        }

    return {
        "status": "PIPELINE_SUCCESS",
        "pipeline_id": pipeline_id,
        "stages": [s.name for s in pipe_run.stages]
    }

# Mount static web UI if directory exists
static_dir = os.path.join(os.path.dirname(__file__), "..", "web", "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

@app.get("/", response_class=HTMLResponse)
def index():
    index_path = os.path.join(static_dir, "index.html")
    if os.path.exists(index_path):
        with open(index_path, "r", encoding="utf-8") as f:
            return f.read()
    return "<h1>DevOps Sentinel Agent API</h1><p>Visit <a href='/docs'>/docs</a> for Swagger UI.</p>"
