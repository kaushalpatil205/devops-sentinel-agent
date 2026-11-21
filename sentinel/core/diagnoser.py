import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger("sentinel.diagnoser")

@dataclass
class DiagnosisResult:
    incident_id: str
    failure_type: str  # OOMKilled, CrashLoopBackOff, ReadinessProbeFailed, PortMismatch, BuildDependencyMissing, DockerfileSyntaxError, CanaryHealthBreach, ConfigDrift
    severity: str      # CRITICAL, HIGH, MEDIUM, LOW
    confidence: float  # 0.0 to 1.0
    root_cause: str
    evidence: List[str] = field(default_factory=list)
    affected_resource: str = ""
    suggested_action: str = ""
    remediation_params: Dict[str, Any] = field(default_factory=dict)

class IncidentDiagnoserAgent:
    """
    Intelligent incident reasoning agent. Parses logs, container exit codes,
    Kubernetes events, and telemetry to diagnose the exact root cause of failure.
    """

    def diagnose(self, 
                 incident_id: str, 
                 resource_name: str, 
                 pod_status: Optional[str] = None, 
                 logs: str = "", 
                 events: Optional[List[str]] = None,
                 extra_context: Optional[Dict[str, Any]] = None) -> DiagnosisResult:
        
        events = events or []
        extra_context = extra_context or {}
        combined_text = f"{pod_status or ''}\n{logs}\n" + "\n".join(events)

        logger.info(f"Agent diagnosing incident {incident_id} on resource '{resource_name}'...")

        # 1. Check for OOMKilled (Exit Code 137 or Kernel OOM Killer)
        if (pod_status == "OOMKilled" or 
            "exit code 137" in combined_text.lower() or 
            "oomkilled" in combined_text.lower() or 
            "out of memory" in combined_text.lower() or
            "memory limit exceeded" in combined_text.lower()):
            
            # Extract memory numbers if available
            current_limit = extra_context.get("current_memory_limit", "128Mi")
            target_limit = "512Mi" if current_limit in ("128Mi", "256Mi") else "1Gi"
            
            return DiagnosisResult(
                incident_id=incident_id,
                failure_type="OOMKilled",
                severity="CRITICAL",
                confidence=0.98,
                root_cause=f"Container exceeded allocated memory limit ({current_limit}) causing Linux kernel OOM Killer termination (SIGKILL exit code 137).",
                evidence=[
                    "Container termination reason: OOMKilled",
                    f"Observed memory usage peaked at or above limit {current_limit}",
                    "Kernel killed process to prevent node memory starvation"
                ],
                affected_resource=resource_name,
                suggested_action=f"Scale container memory limit from {current_limit} to {target_limit} in deployment manifest.",
                remediation_params={
                    "resource": resource_name,
                    "param": "memory_limit",
                    "current": current_limit,
                    "target": target_limit
                }
            )

        # 2. Check for Readiness Probe / Port Mismatch
        if ("readiness probe failed" in combined_text.lower() or 
            "connection refused" in combined_text.lower() or 
            "http probe failed with statuscode: 502" in combined_text.lower() or
            "port mismatch" in combined_text.lower()):
            
            # Detect port mismatch details
            m = re.search(r"connection refused.*:(\d+)", combined_text)
            attempted_port = int(m.group(1)) if m else extra_context.get("probe_port", 3000)
            target_app_port = extra_context.get("app_port", 8080)

            return DiagnosisResult(
                incident_id=incident_id,
                failure_type="PortMismatch",
                severity="HIGH",
                confidence=0.95,
                root_cause=f"Readiness probe targeting port {attempted_port} failed because container application is listening on port {target_app_port}.",
                evidence=[
                    f"Probe failure event: dial tcp : {attempted_port}: connect: connection refused",
                    f"Application server bound to 0.0.0.0:{target_app_port}"
                ],
                affected_resource=resource_name,
                suggested_action=f"Align Kubernetes service and readiness probe port from {attempted_port} to {target_app_port}.",
                remediation_params={
                    "resource": resource_name,
                    "param": "port",
                    "old_port": attempted_port,
                    "new_port": target_app_port
                }
            )

        # 3. Check for Missing Dependency in Build / CI
        missing_module = re.search(r"ModuleNotFoundError:\s+No module named ['\"]([^'\"]+)['\"]", combined_text)
        if missing_module or "pip install" in combined_text and "error" in combined_text.lower():
            pkg = missing_module.group(1) if missing_module else extra_context.get("missing_package", "pydantic")
            return DiagnosisResult(
                incident_id=incident_id,
                failure_type="BuildDependencyMissing",
                severity="HIGH",
                confidence=0.96,
                root_cause=f"CI/CD build failed due to uninstalled Python package '{pkg}'.",
                evidence=[
                    f"Traceback: ModuleNotFoundError: No module named '{pkg}'",
                    "Build stage exited with non-zero status during test execution"
                ],
                affected_resource=resource_name,
                suggested_action=f"Add '{pkg}' to requirements.txt and Dockerfile RUN layer.",
                remediation_params={
                    "resource": resource_name,
                    "package": pkg,
                    "target_file": "Dockerfile"
                }
            )

        # 4. Check for Dockerfile Syntax Error
        if ("unknown instruction:" in combined_text.lower() or 
            "dockerfile parse error" in combined_text.lower()):
            m = re.search(r"unknown instruction:\s*([A-Za-z0-9_-]+)", combined_text, re.IGNORECASE)
            bad_instruction = m.group(1) if m else "INSTRUCTION"
            return DiagnosisResult(
                incident_id=incident_id,
                failure_type="DockerfileSyntaxError",
                severity="HIGH",
                confidence=0.94,
                root_cause=f"Dockerfile parsing error: invalid Dockerfile keyword '{bad_instruction}'.",
                evidence=[f"Docker daemon returned unknown instruction: {bad_instruction}"],
                affected_resource=resource_name,
                suggested_action=f"Correct typo instruction '{bad_instruction}' to valid Dockerfile command.",
                remediation_params={
                    "resource": resource_name,
                    "bad_instruction": bad_instruction,
                    "fixed_instruction": "ENV" if bad_instruction.upper() == "ENVI" else "RUN"
                }
            )

        # 5. Check for Canary Degradation / SLA Breach
        if "canary" in combined_text.lower() or extra_context.get("error_rate", 0) > 0.05:
            err_rate = extra_context.get("error_rate", 0.15)
            return DiagnosisResult(
                incident_id=incident_id,
                failure_type="CanaryHealthBreach",
                severity="CRITICAL",
                confidence=0.99,
                root_cause=f"Canary deployment failed health SLA: 5xx error rate spiked to {err_rate*100:.1f}% (threshold: 1.0%).",
                evidence=[
                    f"Canary HTTP 500 error rate: {err_rate*100:.1f}%",
                    "Canary ingress router automatically degraded health score"
                ],
                affected_resource=resource_name,
                suggested_action="Execute immediate rollback to previous stable production revision.",
                remediation_params={
                    "resource": resource_name,
                    "action": "ROLLBACK",
                    "target_revision": extra_context.get("previous_revision", 1)
                }
            )

        # 6. Generic CrashLoopBackOff fallback
        return DiagnosisResult(
            incident_id=incident_id,
            failure_type="CrashLoopBackOff",
            severity="MEDIUM",
            confidence=0.75,
            root_cause="Pod entered continuous restart loop (CrashLoopBackOff).",
            evidence=["Pod status: CrashLoopBackOff", "Restarts > 3"],
            affected_resource=resource_name,
            suggested_action="Inspect application startup parameters and environment variables.",
            remediation_params={"resource": resource_name}
        )
