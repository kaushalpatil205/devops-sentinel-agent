"""
Telemetry Collector Microservice - Observability & Incident Detection
Continuously monitors registered microservices, scrapes Prometheus metrics,
ingests Alertmanager & Kubernetes events, and forwards structured incident
signals to the DevOps Sentinel Core Agent.
"""

import os
import time
import threading
import logging
from typing import Any, Dict, List, Optional
from fastapi import FastAPI, BackgroundTasks, Response
from pydantic import BaseModel
import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] [telemetry] %(message)s")
logger = logging.getLogger("telemetry_collector")

app = FastAPI(
    title="DevOps Sentinel: Telemetry Collector Microservice",
    version="1.2.0",
    description="Ingests pod events, scrapes Prometheus metrics, and dispatches incident triggers to Sentinel Core"
)

SENTINEL_CORE_URL = os.getenv("SENTINEL_CORE_URL", "http://localhost:8000")
POLL_INTERVAL_SECONDS = int(os.getenv("POLL_INTERVAL_SECONDS", "5"))

# Monitored Targets registry
TARGETS: Dict[str, Dict[str, Any]] = {
    "web-api": {
        "url": os.getenv("WEB_API_URL", "http://localhost:8080"),
        "health_endpoint": "/healthz",
        "ready_endpoint": "/ready",
        "metrics_endpoint": "/metrics",
        "status": "HEALTHY",
        "consecutive_failures": 0,
        "last_checked": 0
    },
    "order-service": {
        "url": os.getenv("ORDER_SERVICE_URL", "http://localhost:8081"),
        "health_endpoint": "/healthz",
        "ready_endpoint": "/ready",
        "metrics_endpoint": "/metrics",
        "status": "HEALTHY",
        "consecutive_failures": 0,
        "last_checked": 0
    }
}

EVENT_HISTORY: List[Dict[str, Any]] = []
COLLECTOR_RUNNING = True

class AlertWebhookPayload(BaseModel):
    receiver: Optional[str] = "sentinel-webhook"
    status: str  # "firing" or "resolved"
    alerts: List[Dict[str, Any]]

class K8sEventPayload(BaseModel):
    reason: str
    message: str
    resource: str
    namespace: Optional[str] = "production"
    type: str = "Warning"

def forward_incident_to_sentinel(incident_payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Forward incident to Sentinel Core API"""
    try:
        url = f"{SENTINEL_CORE_URL}/api/incident/trigger"
        res = requests.post(url, json=incident_payload, timeout=5)
        if res.status_code == 200:
            logger.info("Successfully dispatched incident to Sentinel Core: %s", incident_payload.get("resource_name"))
            return res.json()
        else:
            logger.warning("Sentinel Core returned status %s: %s", res.status_code, res.text)
    except Exception as exc:
        logger.error("Failed to forward incident to Sentinel Core (%s): %s", SENTINEL_CORE_URL, exc)
    return None

def check_target(name: str, target: Dict[str, Any]):
    """Probe target service and detect failures"""
    base_url = target["url"]
    health_url = f"{base_url}{target['health_endpoint']}"
    ready_url = f"{base_url}{target['ready_endpoint']}"
    
    target["last_checked"] = time.time()
    failure_reason = None
    pod_status = "Running"
    logs = ""
    events = []
    extra_context = {}

    try:
        # Check liveness
        resp = requests.get(health_url, timeout=2)
        if resp.status_code != 200:
            target["consecutive_failures"] += 1
            target["status"] = "UNHEALTHY"
            failure_reason = f"Liveness probe returned HTTP {resp.status_code}"
            pod_status = "CrashLoopBackOff"
            logs = f"FATAL: Container health check failed: {resp.text}"
            events.append(f"Warning: Unhealthy: Liveness probe failed on {health_url}")
        else:
            # Check readiness
            r_resp = requests.get(ready_url, timeout=2)
            if r_resp.status_code != 200:
                target["consecutive_failures"] += 1
                target["status"] = "NOT_READY"
                failure_reason = f"Readiness probe returned HTTP {r_resp.status_code}"
                pod_status = "ReadinessProbeFailed"
                events.append(f"Warning: Readiness probe failed: connection refused or port mismatch")
                extra_context["probe_port"] = 3000
                extra_context["app_port"] = 8080
            else:
                target["consecutive_failures"] = 0
                target["status"] = "HEALTHY"

        # Check metrics for error rate / canary degradation if available
        metrics_url = f"{base_url}{target['metrics_endpoint']}"
        try:
            m_resp = requests.get(metrics_url, timeout=2)
            if m_resp.status_code == 200:
                lines = m_resp.text.splitlines()
                for line in lines:
                    if "order_service_error_rate_percent" in line and not line.startswith("#"):
                        parts = line.strip().split()
                        if len(parts) >= 2:
                            err_rate = float(parts[1])
                            if err_rate > 10.0:
                                failure_reason = f"Canary SLA Error Rate Breach: {err_rate}% errors"
                                pod_status = "CanaryHealthBreach"
                                extra_context["error_rate"] = err_rate / 100.0
                                extra_context["previous_revision"] = 1
        except Exception:
            pass

    except requests.exceptions.ConnectionError:
        target["consecutive_failures"] += 1
        target["status"] = "DOWN"
        failure_reason = f"Connection refused to {base_url}"
        pod_status = "CrashLoopBackOff"
        logs = f"ConnectionRefused: dial tcp {base_url}: connect: connection refused"
        events.append(f"Warning: Failed to connect to pod {name}")
    except Exception as e:
        target["status"] = "ERROR"
        failure_reason = str(e)

    if failure_reason:
        event = {
            "timestamp": time.strftime("%H:%M:%S"),
            "target": name,
            "status": target["status"],
            "pod_status": pod_status,
            "reason": failure_reason
        }
        EVENT_HISTORY.append(event)
        
        # Dispatch incident
        payload = {
            "resource_name": name,
            "pod_status": pod_status,
            "logs": logs or f"Service {name} failure detected by telemetry collector: {failure_reason}",
            "events": events or [f"Warning: Telemetry anomaly detected on {name}"],
            "extra_context": extra_context
        }
        forward_incident_to_sentinel(payload)

def background_poller():
    """Background polling loop for targets"""
    logger.info("Started telemetry poller loop (interval=%ds)", POLL_INTERVAL_SECONDS)
    while COLLECTOR_RUNNING:
        for name, target in list(TARGETS.items()):
            try:
                check_target(name, target)
            except Exception as e:
                logger.error("Error polling target %s: %s", name, e)
        time.sleep(POLL_INTERVAL_SECONDS)

# Launch background poller thread
poller_thread = threading.Thread(target=background_poller, daemon=True)
poller_thread.start()

@app.get("/")
def get_root():
    return {
        "service": "telemetry-collector",
        "version": "1.2.0",
        "sentinel_core_url": SENTINEL_CORE_URL,
        "monitored_targets_count": len(TARGETS),
        "total_events_captured": len(EVENT_HISTORY)
    }

@app.get("/status")
def get_status():
    return {
        "collector": "active",
        "targets": TARGETS,
        "recent_events": EVENT_HISTORY[-10:]
    }

@app.get("/targets")
def list_targets():
    return {"targets": TARGETS}

@app.post("/targets/poll")
def trigger_manual_poll():
    """Trigger immediate health check sweep across all targets"""
    results = {}
    for name, target in TARGETS.items():
        check_target(name, target)
        results[name] = target["status"]
    return {"status": "SWEEP_COMPLETED", "results": results}

@app.post("/webhook/alerts")
def receive_prometheus_alert(payload: AlertWebhookPayload):
    """Receive Prometheus / Alertmanager alerts and dispatch incidents"""
    dispatched = []
    for alert in payload.alerts:
        alert_name = alert.get("labels", {}).get("alertname", "UnknownAlert")
        resource = alert.get("labels", {}).get("instance", alert.get("labels", {}).get("service", "unknown-service"))
        summary = alert.get("annotations", {}).get("summary", alert.get("annotations", {}).get("description", "Alert firing"))
        severity = alert.get("labels", {}).get("severity", "critical")
        
        event_entry = {
            "timestamp": time.strftime("%H:%M:%S"),
            "target": resource,
            "status": "ALERT_FIRING",
            "pod_status": "OOMKilled" if "OOM" in alert_name else "CrashLoopBackOff",
            "reason": f"{alert_name}: {summary}"
        }
        EVENT_HISTORY.append(event_entry)

        incident_payload = {
            "resource_name": resource,
            "pod_status": "OOMKilled" if "OOM" in alert_name else "CrashLoopBackOff",
            "logs": f"Prometheus Alert '{alert_name}' (severity={severity}): {summary}",
            "events": [f"Alert: {alert_name} firing on {resource}"],
            "extra_context": {"alert_name": alert_name, "severity": severity}
        }
        res = forward_incident_to_sentinel(incident_payload)
        dispatched.append({"alert": alert_name, "result": res})
        
    return {"status": "ALERTS_PROCESSED", "count": len(payload.alerts), "dispatched": dispatched}

@app.post("/events/k8s")
def receive_k8s_event(payload: K8sEventPayload):
    """Ingest Kubernetes Warning/Error events"""
    entry = {
        "timestamp": time.strftime("%H:%M:%S"),
        "target": payload.resource,
        "status": payload.type,
        "pod_status": payload.reason,
        "reason": payload.message
    }
    EVENT_HISTORY.append(entry)
    
    incident_payload = {
        "resource_name": payload.resource,
        "pod_status": payload.reason,
        "logs": f"K8s Event {payload.type}: {payload.message}",
        "events": [f"{payload.type}: {payload.reason} - {payload.message}"],
        "extra_context": {"namespace": payload.namespace}
    }
    res = forward_incident_to_sentinel(incident_payload)
    return {"status": "EVENT_INGESTED", "dispatched": res}

@app.get("/events/history")
def get_event_history():
    return {"total": len(EVENT_HISTORY), "events": EVENT_HISTORY[-50:]}

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8001"))
    uvicorn.run(app, host="0.0.0.0", port=port)
