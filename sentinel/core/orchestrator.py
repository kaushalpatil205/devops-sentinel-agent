import logging
import time
import uuid
from typing import Any, Dict, List, Optional
from sentinel.config import config
from sentinel.connectors.k8s_client import KubernetesClient
from sentinel.connectors.git_client import GitClient
from sentinel.connectors.iac_parser import IaCParser
from sentinel.connectors.cicd_runner import CICDRunner
from sentinel.core.diagnoser import IncidentDiagnoserAgent, DiagnosisResult
from sentinel.core.remediator import RemediationAgent, RemediationPlan
from sentinel.core.verifier import VerificationAgent, VerificationReport
from sentinel.core.rca_generator import RCAReporter
from sentinel.core.drift_detector import DriftDetector, DriftReport

logger = logging.getLogger("sentinel.orchestrator")

class AgentOrchestrator:
    """
    Master Autonomous DevOps Agent Orchestrator.
    Drives the complete end-to-end incident lifecycle:
    Detection -> Deep Diagnosis -> Remediation Planning -> Patch Application -> Verification -> Rollback on Failure -> RCA Delivery.
    """
    def __init__(self, use_mock: bool = True):
        self.use_mock = use_mock
        self.k8s_client = KubernetesClient(use_mock=use_mock)
        self.git_client = GitClient(mock_mode=use_mock)
        self.iac_parser = IaCParser()
        self.cicd_runner = CICDRunner(mock_mode=use_mock)
        
        # Subagents
        self.diagnoser = IncidentDiagnoserAgent()
        self.remediator = RemediationAgent(self.iac_parser, self.git_client, self.k8s_client)
        self.verifier = VerificationAgent(self.k8s_client)
        self.drift_detector = DriftDetector(self.iac_parser)
        
        # Incident history & live state
        self.incidents: Dict[str, Dict[str, Any]] = {}
        self.activity_log: List[Dict[str, Any]] = []

    def log_activity(self, message: str, level: str = "INFO", details: Optional[Dict[str, Any]] = None):
        entry = {
            "timestamp": time.strftime("%H:%M:%S"),
            "level": level,
            "message": message,
            "details": details or {}
        }
        self.activity_log.append(entry)
        if level == "ERROR":
            logger.error(message)
        elif level == "WARNING":
            logger.warning(message)
        else:
            logger.info(message)

    def handle_incident(self, 
                        resource_name: str, 
                        pod_status: Optional[str] = None, 
                        logs: str = "", 
                        events: Optional[List[str]] = None,
                        extra_context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Executes the full automated incident healing loop.
        """
        incident_id = f"inc-{uuid.uuid4().hex[:8]}"
        t_start = time.time()
        timeline = []

        self.log_activity(f"🚨 Incident {incident_id} detected on target resource '{resource_name}'", "WARNING")
        timeline.append({"time": "00:00:00", "stage": "Detection", "detail": f"Anomaly on {resource_name} ({pod_status or 'Error'})"})

        # Step 1: Intelligent Diagnosis
        self.log_activity(f"🔍 Diagnoser Agent analyzing telemetry and stack traces for {incident_id}...", "INFO")
        diagnosis: DiagnosisResult = self.diagnoser.diagnose(
            incident_id=incident_id,
            resource_name=resource_name,
            pod_status=pod_status,
            logs=logs,
            events=events,
            extra_context=extra_context
        )
        timeline.append({"time": "00:00:01", "stage": "Diagnosis", "detail": f"Classified as {diagnosis.failure_type} (conf: {int(diagnosis.confidence*100)}%)"})
        self.log_activity(f"💡 Diagnosis: {diagnosis.failure_type} - {diagnosis.root_cause}", "INFO")

        # Step 2: Remediation Planning
        self.log_activity(f"🛠️ Remediation Agent synthesizing patch plan for {incident_id}...", "INFO")
        plan: RemediationPlan = self.remediator.plan_remediation(diagnosis)
        timeline.append({"time": "00:00:02", "stage": "Planning", "detail": f"Action {plan.action_type} formulated (Branch: {plan.branch_name})"})

        # Step 3: Patch Application / Execution
        apply_result = {}
        if config.auto_remediate:
            self.log_activity(f"🚀 Applying remediation plan {plan.plan_id} to cluster...", "INFO")
            apply_result = self.remediator.apply_plan(plan)
            timeline.append({"time": "00:00:03", "stage": "Execution", "detail": apply_result.get("message", "Applied")})
        else:
            self.log_activity(f"⏸️ Auto-remediation paused. Human approval required for plan {plan.plan_id}.", "WARNING")
            timeline.append({"time": "00:00:03", "stage": "Awaiting Approval", "detail": "Human approval gate active"})

        # Step 4: Verification & Safety Rollback
        self.log_activity(f"🩺 Verification Agent checking deployment health probes for '{resource_name}'...", "INFO")
        verification: VerificationReport = self.verifier.verify_deployment(
            deployment_name=resource_name,
            auto_rollback=config.auto_rollback_on_failure
        )
        status_msg = "HEALTHY" if verification.verified else ("ROLLED_BACK" if verification.rollback_triggered else "FAILED")
        timeline.append({"time": "00:00:04", "stage": "Verification", "detail": f"Status: {status_msg} (Score: {verification.readiness_score*100:.0f}%)"})
        
        if verification.rollback_triggered:
            self.log_activity(f"⚠️ Health check failed! Automated rollback triggered for '{resource_name}'.", "WARNING")
        else:
            self.log_activity(f"✅ Resource '{resource_name}' successfully verified healthy!", "INFO")

        # Step 5: Deliver Post-Mortem RCA Report
        duration = round(time.time() - t_start, 2)
        rca_markdown = RCAReporter.generate_markdown(
            incident_id=incident_id,
            diagnosis=diagnosis,
            plan=plan,
            verification=verification,
            timeline_events=timeline,
            duration_seconds=duration
        )
        rca_html = RCAReporter.generate_html(rca_markdown)

        incident_record = {
            "incident_id": incident_id,
            "resource": resource_name,
            "status": "RESOLVED" if verification.verified else ("ROLLED_BACK" if verification.rollback_triggered else "FAILED"),
            "diagnosis": diagnosis.__dict__,
            "plan": plan.__dict__,
            "verification": verification.__dict__,
            "timeline": timeline,
            "duration_seconds": duration,
            "rca_markdown": rca_markdown,
            "rca_html": rca_html
        }
        self.incidents[incident_id] = incident_record
        return incident_record

    def run_drift_check(self, resource_name: str, namespace: str, desired_spec: Dict[str, Any], live_spec: Dict[str, Any]) -> DriftReport:
        """Executes IaC configuration drift check and triggers remediation if needed."""
        self.log_activity(f"🔎 Scanning for IaC configuration drift in {resource_name}...", "INFO")
        report = self.drift_detector.detect_drift(
            resource_type="Deployment",
            resource_name=resource_name,
            namespace=namespace,
            desired_spec=desired_spec,
            live_spec=live_spec
        )
        if report.drift_detected:
            self.log_activity(f"⚠️ Drift detected in {resource_name}: {report.drift_count} differences. Action: {report.reconciliation_action}", "WARNING")
        else:
            self.log_activity(f"✅ Zero drift in {resource_name}. Spec matches Git baseline.", "INFO")
        return report
