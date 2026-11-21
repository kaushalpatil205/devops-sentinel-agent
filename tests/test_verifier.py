import pytest
from sentinel.connectors.k8s_client import KubernetesClient, PodInfo
from sentinel.core.verifier import VerificationAgent

def test_verify_healthy_deployment():
    k8s = KubernetesClient(use_mock=True)
    k8s.set_mock_pod(PodInfo(
        name="web-api-12345",
        namespace="default",
        status="Running",
        restarts=0,
        ready=True,
        image="web-api:latest"
    ))
    verifier = VerificationAgent(k8s)
    report = verifier.verify_deployment("web-api", auto_rollback=True)
    
    assert report.verified is True
    assert report.status == "HEALTHY"
    assert report.rollback_triggered is False
    assert report.health_checks_passed == report.total_health_checks
