from fastapi.testclient import TestClient
from sentinel.api.server import app

client = TestClient(app)

def test_api_status():
    response = client.get("/api/status")
    assert response.status_code == 200
    data = response.json()
    assert data["agent"] == "DevOps Sentinel Agent"
    assert "version" in data

def test_api_scenarios_list():
    response = client.get("/api/scenarios")
    assert response.status_code == 200
    data = response.json()
    assert "scenarios" in data
    assert len(data["scenarios"]) >= 5

def test_api_run_scenario_oom():
    response = client.post("/api/scenarios/run/oom_killed")
    assert response.status_code == 200
    data = response.json()
    assert data["type"] == "incident"
    assert data["incident"]["diagnosis"]["failure_type"] == "OOMKilled"
    assert data["incident"]["status"] == "RESOLVED"

def test_api_cluster_pods():
    response = client.get("/api/cluster/pods")
    assert response.status_code == 200
    data = response.json()
    assert "pods" in data

def test_api_github_webhook():
    payload = {
        "ref": "refs/heads/main",
        "repository": {"name": "sample-repo"},
        "commits": [{"id": "abc1234", "message": "feat: release new microservice"}]
    }
    response = client.post("/api/webhook/github", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] in ("PIPELINE_SUCCESS", "HEALED_VIA_AGENT")
