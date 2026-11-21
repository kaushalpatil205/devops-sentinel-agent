import logging
from typing import Any, Dict, Optional
from sentinel.connectors.k8s_client import KubernetesClient, PodInfo, DeploymentInfo
from sentinel.core.orchestrator import AgentOrchestrator
from sentinel.simulator.scenarios import get_scenario

logger = logging.getLogger("sentinel.sim")

class ClusterSimulator:
    """
    Simulation sandbox environment allowing rapid end-to-end verification of
    autonomous agent diagnosis, remediation, drift detection, and rollback.
    """
    def __init__(self, orchestrator: Optional[AgentOrchestrator] = None):
        self.orchestrator = orchestrator or AgentOrchestrator(use_mock=True)

    def load_scenario(self, scenario_id: str) -> Dict[str, Any]:
        """Loads and primes the scenario in the simulator."""
        scenario = get_scenario(scenario_id)
        
        # If scenario defines mock pod, register it with the K8s client
        if "pod" in scenario:
            pod: PodInfo = scenario["pod"]
            self.orchestrator.k8s_client.set_mock_pod(pod)
            dep = DeploymentInfo(
                name=scenario["resource_name"],
                namespace=pod.namespace,
                desired_replicas=1,
                available_replicas=0,
                image=pod.image,
                revision=1,
                health_status="Degraded"
            )
            self.orchestrator.k8s_client.set_mock_deployment(dep)

        return scenario

    def run_scenario(self, scenario_id: str) -> Dict[str, Any]:
        """Executes the scenario through the autonomous agent loop."""
        scenario = self.load_scenario(scenario_id)

        if scenario_id == "iac_drift":
            report = self.orchestrator.run_drift_check(
                resource_name=scenario["resource_name"],
                namespace=scenario["namespace"],
                desired_spec=scenario["desired_spec"],
                live_spec=scenario["live_spec"]
            )
            return {
                "scenario": scenario["name"],
                "type": "drift",
                "drift_report": report.__dict__
            }

        # Otherwise it's an incident remediation scenario
        pod: Optional[PodInfo] = scenario.get("pod")
        logs = scenario.get("logs", "")
        if pod and not logs:
            logs = pod.last_log_snippet
        events = scenario.get("events", [])
        if pod and not events:
            events = pod.events

        incident_result = self.orchestrator.handle_incident(
            resource_name=scenario["resource_name"],
            pod_status=scenario.get("pod_status"),
            logs=logs,
            events=events,
            extra_context=scenario.get("extra_context")
        )

        return {
            "scenario": scenario["name"],
            "type": "incident",
            "incident": incident_result
        }
