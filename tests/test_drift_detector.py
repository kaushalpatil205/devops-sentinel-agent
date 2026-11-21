import pytest
from sentinel.core.drift_detector import DriftDetector
from sentinel.connectors.iac_parser import IaCParser

def test_zero_drift():
    detector = DriftDetector()
    desired = {"replicas": 3, "image": "api:v1.0"}
    live = {"replicas": 3, "image": "api:v1.0"}
    
    report = detector.detect_drift("Deployment", "web-api", "default", desired, live)
    assert not report.drift_detected
    assert report.drift_count == 0
    assert report.reconciliation_action == "NONE"

def test_detected_drift_replica_and_image():
    detector = DriftDetector()
    desired = {"replicas": 3, "image": "api:v1.0", "resources": {"limits": {"memory": "256Mi"}}}
    live = {"replicas": 1, "image": "api:v1.0-debug", "resources": {"limits": {"memory": "256Mi"}}}
    
    report = detector.detect_drift("Deployment", "web-api", "default", desired, live)
    assert report.drift_detected
    assert report.drift_count == 2
    assert report.reconciliation_action == "AUTO_RECONCILE_TO_GIT"
