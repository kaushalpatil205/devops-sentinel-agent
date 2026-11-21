"""
Unit and Integration Tests for DevOps Sentinel Multi-Microservice Fleet
Covers:
- Web API Microservice (Health probes, chaos triggers, reset)
- Order Service Microservice (Canary deployment, error injection, auto-rollback)
- Telemetry Collector Microservice (Alert ingestion, target health checks)
- CI/CD Pipeline Runner Microservice (Stage progression, build failures, hotfix re-run)
- Core Agent Microservices Status Aggregator
"""

import pytest
from fastapi.testclient import TestClient

# Import microservice FastAPI apps
from services.web_api.app import app as web_api_app
from services.order_service.app import app as order_service_app
from services.telemetry_collector.collector import app as collector_app
from services.cicd_runner.runner import app as cicd_runner_app
from sentinel.api.server import app as sentinel_core_app

web_client = TestClient(web_api_app)
order_client = TestClient(order_service_app)
collector_client = TestClient(collector_app)
cicd_client = TestClient(cicd_runner_app)
sentinel_client = TestClient(sentinel_core_app)


# --- 1. Web API Microservice Tests ---

def test_web_api_health_and_probes():
    res = web_client.get("/")
    assert res.status_code == 200
    assert res.json()["service"] == "web-api"

    res = web_client.get("/healthz")
    assert res.status_code == 200
    assert res.json()["status"] == "UP"

    res = web_client.get("/ready")
    assert res.status_code == 200
    assert res.json()["status"] == "READY"

def test_web_api_metrics():
    res = web_client.get("/metrics")
    assert res.status_code == 200
    assert "web_api_uptime_seconds" in res.text
    assert "web_api_healthy 1" in res.text

def test_web_api_memory_and_crash_simulation():
    # Simulate high memory load
    res = web_client.post("/simulate/memory-load?size_mb=140")
    assert res.status_code == 200
    assert res.json()["oom_triggered"] is True

    # Check healthz reflects down
    h_res = web_client.get("/healthz")
    assert h_res.status_code == 503

    # Reset
    reset_res = web_client.post("/reset")
    assert reset_res.status_code == 200
    assert web_client.get("/healthz").status_code == 200


# --- 2. Order Service Microservice Tests ---

def test_order_service_lifecycle():
    res = order_client.get("/")
    assert res.status_code == 200
    assert res.json()["service"] == "order-service"

    # Place successful order
    order_res = order_client.post("/api/orders", json={
        "customer_id": "cust-99",
        "item_id": "itm-001",
        "quantity": 2
    })
    assert order_res.status_code == 200
    assert order_res.json()["status"] == "CONFIRMED"

def test_order_service_canary_and_rollback():
    # Enable canary with error injection
    canary_res = order_client.post("/simulate/canary", json={
        "enabled": True,
        "traffic_percent": 100,
        "inject_errors": True,
        "latency_sec": 0.0
    })
    assert canary_res.status_code == 200
    assert canary_res.json()["canary_enabled"] is True

    # Order should now fail
    err_order = order_client.post("/api/orders", json={
        "customer_id": "cust-fail",
        "item_id": "itm-002",
        "quantity": 1
    })
    assert err_order.status_code == 500

    # Execute rollback
    rb_res = order_client.post("/simulate/rollback")
    assert rb_res.status_code == 200
    assert rb_res.json()["status"] == "ROLLED_BACK"

    # Reset
    order_client.post("/reset")


# --- 3. Telemetry Collector Microservice Tests ---

def test_telemetry_collector_endpoints():
    res = collector_client.get("/")
    assert res.status_code == 200
    assert res.json()["service"] == "telemetry-collector"

    targets_res = collector_client.get("/targets")
    assert targets_res.status_code == 200
    assert "web-api" in targets_res.json()["targets"]
    assert "order-service" in targets_res.json()["targets"]

def test_telemetry_collector_alert_ingestion():
    alert_payload = {
        "status": "firing",
        "alerts": [
            {
                "labels": {
                    "alertname": "PodMemoryUsageHighOOM",
                    "instance": "web-api",
                    "severity": "critical"
                },
                "annotations": {
                    "summary": "Container web-api approaching memory ceiling 128Mi"
                }
            }
        ]
    }
    res = collector_client.post("/webhook/alerts", json=alert_payload)
    assert res.status_code == 200
    assert res.json()["status"] == "ALERTS_PROCESSED"
    assert res.json()["count"] == 1


# --- 4. CI/CD Runner Microservice Tests ---

def test_cicd_runner_pipeline_success():
    trigger_res = cicd_client.post("/pipelines/trigger", json={
        "service_name": "web-api",
        "branch": "feature/cache-layer",
        "commit_message": "feat: add redis cache layer",
        "inject_failure": None
    })
    assert trigger_res.status_code == 200
    pipe_id = trigger_res.json()["pipeline_id"]

    pipe_info = cicd_client.get(f"/pipelines/{pipe_id}")
    assert pipe_info.status_code == 200
    assert pipe_info.json()["id"] == pipe_id

def test_cicd_runner_failure_and_remediation():
    # Trigger failing pipeline (missing dependency)
    fail_res = cicd_client.post("/pipelines/trigger", json={
        "service_name": "inventory-service",
        "branch": "main",
        "commit_message": "feat: add schema validator",
        "inject_failure": "missing_dependency"
    })
    assert fail_res.status_code == 200
    pipe_id = fail_res.json()["pipeline_id"]

    # Remediate via hotfix
    rem_res = cicd_client.post("/pipelines/remediate", json={
        "pipeline_id": pipe_id,
        "hotfix_branch": "sentinel-hotfix/pydantic-fix",
        "patch_summary": "Add pydantic to requirements.txt",
        "remediation_diff": "+ pydantic>=2.6.0"
    })
    assert rem_res.status_code == 200
    assert rem_res.json()["status"] == "HOTFIX_PIPELINE_QUEUED"


# --- 5. Sentinel Core Service Status & Chaos Trigger Tests ---

def test_sentinel_services_status_endpoint():
    res = sentinel_client.get("/api/services/status")
    assert res.status_code == 200
    data = res.json()
    assert "services" in data
    assert "sentinel_core" in data["services"]
    assert data["services"]["sentinel_core"]["status"] == "ONLINE"

def test_sentinel_chaos_trigger():
    res = sentinel_client.post("/api/chaos/trigger", json={
        "target": "web-api",
        "chaos_type": "oom"
    })
    assert res.status_code == 200
    data = res.json()
    assert data["type"] == "incident"
    assert data["incident"]["diagnosis"]["failure_type"] == "OOMKilled"
    assert data["incident"]["status"] == "RESOLVED"
