import pytest
from sentinel.core.diagnoser import IncidentDiagnoserAgent

def test_diagnose_oomkilled():
    agent = IncidentDiagnoserAgent()
    logs = "Killed (SIGKILL, exit code 137). Memory cgroup out of memory."
    res = agent.diagnose("inc-1", "web-api", pod_status="OOMKilled", logs=logs)
    
    assert res.failure_type == "OOMKilled"
    assert res.severity == "CRITICAL"
    assert res.confidence >= 0.95
    assert "memory" in res.root_cause.lower()
    assert res.remediation_params["target"] == "512Mi"

def test_diagnose_port_mismatch():
    agent = IncidentDiagnoserAgent()
    events = ["Readiness probe failed: dial tcp 127.0.0.1:3000: connect: connection refused"]
    res = agent.diagnose("inc-2", "payment-service", pod_status="ReadinessProbeFailed", events=events, extra_context={"probe_port": 3000, "app_port": 8080})
    
    assert res.failure_type == "PortMismatch"
    assert res.severity == "HIGH"
    assert res.remediation_params["old_port"] == 3000
    assert res.remediation_params["new_port"] == 8080

def test_diagnose_missing_dependency():
    agent = IncidentDiagnoserAgent()
    logs = "ModuleNotFoundError: No module named 'pydantic'"
    res = agent.diagnose("inc-3", "ci-builder", logs=logs)
    
    assert res.failure_type == "BuildDependencyMissing"
    assert res.remediation_params["package"] == "pydantic"

def test_diagnose_canary_sla_breach():
    agent = IncidentDiagnoserAgent()
    res = agent.diagnose("inc-4", "checkout-api", extra_context={"error_rate": 0.20, "previous_revision": 1})
    
    assert res.failure_type == "CanaryHealthBreach"
    assert res.severity == "CRITICAL"
    assert res.suggested_action.startswith("Execute immediate rollback")
