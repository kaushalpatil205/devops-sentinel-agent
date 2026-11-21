import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from sentinel.connectors.iac_parser import IaCParser

logger = logging.getLogger("sentinel.drift")

@dataclass
class DriftReport:
    resource_type: str
    resource_name: str
    namespace: str
    drift_detected: bool
    drift_count: int
    differences: List[Dict[str, Any]] = field(default_factory=list)
    reconciliation_action: str = "NONE"  # GIT_OVERWRITE_LIVE, ALERT_DEV_OPS, AUTO_SYNC

class DriftDetector:
    """
    Detects configuration drift between the declarative IaC state in Git (YAML/Terraform)
    and the actual running state in the Kubernetes cluster.
    """
    def __init__(self, parser: Optional[IaCParser] = None):
        self.parser = parser or IaCParser()

    def detect_drift(self, resource_type: str, resource_name: str, namespace: str, desired_spec: Dict[str, Any], live_spec: Dict[str, Any]) -> DriftReport:
        """
        Compare desired spec from repository with live running spec.
        """
        differences = self.parser.compare_specs(desired_spec, live_spec)
        drift_found = len(differences) > 0

        action = "NONE"
        if drift_found:
            # Determine appropriate reconciliation strategy
            has_replica_drift = any("replicas" in d["path"] for d in differences)
            has_image_drift = any("image" in d["path"] for d in differences)
            has_resource_drift = any("resources" in d["path"] or "limits" in d["path"] for d in differences)

            if has_image_drift or has_replica_drift or has_resource_drift:
                action = "AUTO_RECONCILE_TO_GIT"
            else:
                action = "ALERT_DEV_OPS"

        report = DriftReport(
            resource_type=resource_type,
            resource_name=resource_name,
            namespace=namespace,
            drift_detected=drift_found,
            drift_count=len(differences),
            differences=differences,
            reconciliation_action=action
        )

        if drift_found:
            logger.warning(f"Configuration drift detected in {resource_type}/{resource_name}: {len(differences)} mismatched fields.")
        else:
            logger.info(f"Zero drift detected for {resource_type}/{resource_name}. State is in sync with Git.")

        return report

    def generate_reconcile_manifest(self, desired_spec: Dict[str, Any]) -> Dict[str, Any]:
        """
        Produce a pristine reconciliation manifest restoring the desired Git state.
        """
        return desired_spec
