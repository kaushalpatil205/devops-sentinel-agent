import copy
from typing import Any, Dict, List
from sentinel.connectors.k8s_client import PodInfo, DeploymentInfo

SCENARIOS: Dict[str, Dict[str, Any]] = {
    "oom_killed": {
        "id": "oom_killed",
        "name": "Scenario 1: Kubernetes Pod OOMKilled (Exit Code 137)",
        "description": "Production pod killed by Linux kernel OOM Killer due to insufficient memory limit under traffic spike.",
        "resource_name": "web-api",
        "pod_status": "OOMKilled",
        "pod": PodInfo(
            name="web-api-7b89f899d-xk92m",
            namespace="production",
            status="OOMKilled",
            restarts=4,
            ready=False,
            image="app/web-api:v2.4.1",
            memory_limit="128Mi",
            events=[
                "Normal: Scheduled pod to node gke-worker-pool-1",
                "Normal: Container web-api started",
                "Warning: OOMKilled: Container web-api in pod web-api-7b89f899d-xk92m was terminated: Exit Code 137 (Reason: OOMKilled)",
                "Warning: Back-off restarting failed container"
            ],
            last_log_snippet="""[2026-11-21 11:15:02] INFO: Processing bulk data export payload...
[2026-11-21 11:15:04] INFO: Memory consumption reaching 127.8MiB / 128MiB ceiling.
[2026-11-21 11:15:05] FATAL: Out of memory: Kill process 18241 (python) score 954 or sacrifice child.
Killed (SIGKILL, exit code 137)"""
        ),
        "extra_context": {
            "current_memory_limit": "128Mi",
            "suggested_memory_limit": "512Mi"
        }
    },
    
    "probe_port_mismatch": {
        "id": "probe_port_mismatch",
        "name": "Scenario 2: Readiness Probe Port Mismatch (502 / Connection Refused)",
        "description": "Kubernetes readiness probe configured for TCP port 3000 while application listens on 8080.",
        "resource_name": "payment-service",
        "pod_status": "ReadinessProbeFailed",
        "pod": PodInfo(
            name="payment-service-58dc4769c-87qtw",
            namespace="production",
            status="Running",
            restarts=0,
            ready=False,
            image="app/payment-service:v1.9.0",
            ports=[8080],
            events=[
                "Normal: Scheduled pod to node-3",
                "Normal: Pulled image app/payment-service:v1.9.0",
                "Normal: Created container payment-service",
                "Warning: Unhealthy: Readiness probe failed: dial tcp 10.244.1.42:3000: connect: connection refused"
            ],
            last_log_snippet="""[2026-11-21 11:18:00] INFO: Payment service initialized.
[2026-11-21 11:18:01] INFO: Server listening on HTTP 0.0.0.0:8080
[2026-11-21 11:18:02] INFO: Waiting for incoming traffic..."""
        ),
        "extra_context": {
            "probe_port": 3000,
            "app_port": 8080
        }
    },

    "build_dependency_missing": {
        "id": "build_dependency_missing",
        "name": "Scenario 3: CI/CD Build Failure (Missing Dependency)",
        "description": "Continuous Integration build broken due to unpinned/missing dependency in test suite.",
        "resource_name": "inventory-pipeline",
        "pod_status": "BuildFailed",
        "logs": """Running stage: Unit Tests
============================= test session starts ==============================
collecting ... 
tests/test_api.py:3: in <module>
    import pydantic
E   ModuleNotFoundError: No module named 'pydantic'
=========================== 1 error in 0.12s ===================================
ERROR: Job failed: exit code 1""",
        "events": [
            "CI Runner: job failed with exit code 1",
            "Build Artifact: container image build canceled"
        ],
        "extra_context": {
            "missing_package": "pydantic"
        }
    },

    "iac_drift": {
        "id": "iac_drift",
        "name": "Scenario 4: IaC Configuration Drift (Manual Live Cluster Change)",
        "description": "Production deployment modified directly in cluster out-of-band: replicas reduced and untracked debug image applied.",
        "resource_name": "auth-service",
        "namespace": "production",
        "desired_spec": {
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "metadata": {"name": "auth-service", "namespace": "production"},
            "spec": {
                "replicas": 3,
                "template": {
                    "spec": {
                        "containers": [{
                            "name": "auth-service",
                            "image": "auth-service:v3.1.0",
                            "resources": {"limits": {"memory": "256Mi", "cpu": "500m"}}
                        }]
                    }
                }
            }
        },
        "live_spec": {
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "metadata": {"name": "auth-service", "namespace": "production"},
            "spec": {
                "replicas": 1,  # Drifted!
                "template": {
                    "spec": {
                        "containers": [{
                            "name": "auth-service",
                            "image": "auth-service:v3.1.0-debug-experimental",  # Drifted!
                            "resources": {"limits": {"memory": "256Mi", "cpu": "500m"}}
                        }]
                    }
                }
            }
        }
    },

    "canary_regression": {
        "id": "canary_regression",
        "name": "Scenario 5: Canary Health SLA Breach & Automated Rollback",
        "description": "New canary release v2.0 causes 18% HTTP 500 error spike. Agent detects breach, aborts canary, and executes safe rollback.",
        "resource_name": "checkout-api",
        "pod_status": "CanaryHealthBreach",
        "logs": """[Canary Telemetry Stream]
Time: 11:24:10 UTC - Total Requests: 1200 - 200 OK: 984 - 500 InternalServerError: 216
Error Rate: 18.0% (Allowed SLA: < 1.0%)
Latency p99: 1840ms (Allowed SLA: < 250ms)
ALERT: Canary health check failed: Ingress error rate threshold breached.""",
        "events": [
            "PrometheusAlert: HighErrorRateCanary [FIRING]",
            "Canary Controller: Traffic gate halted at 20%"
        ],
        "extra_context": {
            "error_rate": 0.18,
            "previous_revision": 1
        }
    }
}

def get_scenario(scenario_id: str) -> Dict[str, Any]:
    if scenario_id not in SCENARIOS:
        raise ValueError(f"Unknown scenario ID '{scenario_id}'. Available: {list(SCENARIOS.keys())}")
    return copy.deepcopy(SCENARIOS[scenario_id])
