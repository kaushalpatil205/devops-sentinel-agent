import pytest
from sentinel.core.diagnoser import DiagnosisResult
from sentinel.core.remediator import RemediationAgent

def test_remediate_oomkilled_plan():
    agent = RemediationAgent()
    diag = DiagnosisResult(
        incident_id="inc-test-1",
        failure_type="OOMKilled",
        severity="CRITICAL",
        confidence=0.98,
        root_cause="Out of memory",
        affected_resource="web-api",
        remediation_params={"target": "512Mi", "current": "128Mi"}
    )
    plan = agent.plan_remediation(diag)
    assert plan.action_type == "PATCH_MANIFEST"
    assert "memory: 512Mi" in plan.diff
    assert plan.safe_to_apply is True
    assert "sentinel-hotfix" in plan.branch_name

def test_remediate_port_mismatch_plan():
    agent = RemediationAgent()
    diag = DiagnosisResult(
        incident_id="inc-test-2",
        failure_type="PortMismatch",
        severity="HIGH",
        confidence=0.95,
        root_cause="Port mismatch",
        affected_resource="payment-service",
        remediation_params={"old_port": 3000, "new_port": 8080}
    )
    plan = agent.plan_remediation(diag)
    assert plan.action_type == "PATCH_MANIFEST"
    assert "port: 8080" in plan.diff
