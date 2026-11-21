import json
import logging
import subprocess
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger("sentinel.k8s")

@dataclass
class PodInfo:
    name: str
    namespace: str
    status: str  # Running, Pending, CrashLoopBackOff, OOMKilled, ImagePullBackOff, Error
    restarts: int
    ready: bool
    image: str
    cpu_limit: str = "250m"
    memory_limit: str = "128Mi"
    ports: List[int] = field(default_factory=list)
    events: List[str] = field(default_factory=list)
    last_log_snippet: str = ""

@dataclass
class DeploymentInfo:
    name: str
    namespace: str
    desired_replicas: int
    available_replicas: int
    image: str
    revision: int = 1
    strategy: str = "RollingUpdate"
    service_port: int = 80
    target_port: int = 8080
    health_status: str = "Healthy"

class KubernetesClient:
    """
    Kubernetes adapter supporting both native kubectl CLI and programmatic mock cluster state.
    Provides deep visibility into pod states, container exit codes, readiness probes, and rollouts.
    """
    def __init__(self, use_mock: bool = True, namespace: str = "default"):
        self.use_mock = use_mock
        self.namespace = namespace
        self._mock_pods: Dict[str, PodInfo] = {}
        self._mock_deployments: Dict[str, DeploymentInfo] = {}
        self._mock_history: List[Dict[str, Any]] = []

    def run_kubectl(self, args: List[str]) -> Dict[str, Any]:
        """Execute a live kubectl command if running in live cluster mode."""
        if self.use_mock:
            return {"exit_code": 0, "stdout": "", "stderr": "Mock mode active"}
        try:
            cmd = ["kubectl"] + args + ["-n", self.namespace]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
            return {
                "exit_code": res.returncode,
                "stdout": res.stdout,
                "stderr": res.stderr
            }
        except Exception as e:
            logger.error(f"kubectl command failed: {e}")
            return {"exit_code": 1, "stdout": "", "stderr": str(e)}

    # --- Pod Operations ---
    def get_pods(self) -> List[PodInfo]:
        """Fetch current pods."""
        if self.use_mock:
            return list(self._mock_pods.values())
        
        res = self.run_kubectl(["get", "pods", "-o", "json"])
        if res["exit_code"] != 0:
            return list(self._mock_pods.values())
        try:
            data = json.loads(res["stdout"])
            pods = []
            for item in data.get("items", []):
                name = item["metadata"]["name"]
                status = item["status"]["phase"]
                container_statuses = item["status"].get("containerStatuses", [])
                restarts = 0
                ready = False
                if container_statuses:
                    c = container_statuses[0]
                    restarts = c.get("restartCount", 0)
                    ready = c.get("ready", False)
                    state = c.get("state", {})
                    if "waiting" in state:
                        status = state["waiting"].get("reason", status)
                    elif "terminated" in state:
                        status = state["terminated"].get("reason", status)
                pods.append(PodInfo(
                    name=name,
                    namespace=self.namespace,
                    status=status,
                    restarts=restarts,
                    ready=ready,
                    image=item["spec"]["containers"][0]["image"]
                ))
            return pods
        except Exception:
            return list(self._mock_pods.values())

    def get_pod_logs(self, pod_name: str, tail: int = 50) -> str:
        """Fetch recent stdout/stderr logs from a pod."""
        if self.use_mock:
            pod = self._mock_pods.get(pod_name)
            return pod.last_log_snippet if pod else "Pod not found in cluster."
        res = self.run_kubectl(["logs", pod_name, f"--tail={tail}"])
        return res["stdout"] or res["stderr"]

    def get_pod_events(self, pod_name: str) -> List[str]:
        """Retrieve recent Kubernetes warning or failure events for the target pod."""
        if self.use_mock:
            pod = self._mock_pods.get(pod_name)
            return pod.events if pod else []
        res = self.run_kubectl(["get", "events", "--field-selector", f"involvedObject.name={pod_name}", "-o", "json"])
        if res["exit_code"] == 0:
            try:
                events = json.loads(res["stdout"]).get("items", [])
                return [f"[{e.get('type')}] {e.get('reason')}: {e.get('message')}" for e in events]
            except Exception:
                pass
        return []

    # --- Deployment & Rollout Operations ---
    def get_deployment(self, name: str) -> Optional[DeploymentInfo]:
        return self._mock_deployments.get(name)

    def trigger_rollout(self, deployment_name: str, new_image: Optional[str] = None, memory_limit: Optional[str] = None) -> Dict[str, Any]:
        """Trigger an incremental rolling update."""
        if self.use_mock:
            dep = self._mock_deployments.get(deployment_name)
            if not dep:
                return {"status": "error", "message": f"Deployment {deployment_name} not found"}
            dep.revision += 1
            if new_image:
                dep.image = new_image
            # Update associated mock pods
            for p in list(self._mock_pods.values()):
                if p.name.startswith(deployment_name):
                    p.status = "Running"
                    p.ready = True
                    if memory_limit:
                        p.memory_limit = memory_limit
                    if new_image:
                        p.image = new_image
                    p.events.append(f"Normal: Scheduled pod to node (Revision {dep.revision})")
                    p.events.append("Normal: Container image pulled and started successfully")
            dep.health_status = "Healthy"
            self._mock_history.append({
                "action": "rollout",
                "deployment": deployment_name,
                "revision": dep.revision
            })
            return {"status": "success", "revision": dep.revision, "message": "Rollout completed successfully."}
        
        args = ["rollout", "restart", f"deployment/{deployment_name}"]
        return self.run_kubectl(args)

    def rollback(self, deployment_name: str, target_revision: Optional[int] = None) -> Dict[str, Any]:
        """Roll back deployment to previous stable revision."""
        if self.use_mock:
            dep = self._mock_deployments.get(deployment_name)
            if not dep:
                return {"status": "error", "message": f"Deployment {deployment_name} not found"}
            old_rev = dep.revision
            dep.revision = max(1, dep.revision - 1)
            dep.health_status = "RolledBack (Healthy)"
            # Restore pods to stable running state
            for p in list(self._mock_pods.values()):
                if p.name.startswith(deployment_name):
                    p.status = "Running"
                    p.ready = True
                    p.events.append(f"Warning: Rollback triggered from rev {old_rev} to rev {dep.revision}")
                    p.events.append("Normal: Container started from stable replica")
            self._mock_history.append({
                "action": "rollback",
                "deployment": deployment_name,
                "from_rev": old_rev,
                "to_rev": dep.revision
            })
            return {"status": "success", "message": f"Rollback to revision {dep.revision} completed."}
        
        args = ["rollout", "undo", f"deployment/{deployment_name}"]
        if target_revision:
            args.append(f"--to-revision={target_revision}")
        return self.run_kubectl(args)

    # --- Mock Helpers for Scenarios ---
    def set_mock_pod(self, pod: PodInfo):
        self._mock_pods[pod.name] = pod

    def set_mock_deployment(self, deployment: DeploymentInfo):
        self._mock_deployments[deployment.name] = deployment
