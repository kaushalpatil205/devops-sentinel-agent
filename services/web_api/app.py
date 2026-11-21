"""
Web API Microservice - Target Monitored Workload
Exposes business endpoints, standard Kubernetes probes (/healthz, /ready),
Prometheus metrics, and dynamic fault simulation triggers for DevOps Sentinel.
"""

import os
import time
from typing import Dict, List, Optional
from fastapi import FastAPI, Response, status
from pydantic import BaseModel

app = FastAPI(
    title="Target Workload: Web API Microservice",
    version="2.4.1",
    description="Sample production backend service monitored and healed by DevOps Sentinel Agent"
)

# Internal service state
START_TIME = time.time()
SERVICE_STATE = {
    "healthy": True,
    "ready": True,
    "port": int(os.getenv("PORT", "8080")),
    "memory_leak_buffer": [],
    "restarts": 0,
    "total_requests": 0,
    "error_count": 0
}

class ChaosRequest(BaseModel):
    action: str  # "oom", "crash", "probe_fail", "reset"
    params: Optional[Dict[str, str]] = {}

@app.middleware("http")
async def track_requests(request, call_next):
    SERVICE_STATE["total_requests"] += 1
    response = await call_next(request)
    if response.status_code >= 500:
        SERVICE_STATE["error_count"] += 1
    return response

@app.get("/")
def get_root():
    return {
        "service": "web-api",
        "version": "2.4.1",
        "status": "healthy" if SERVICE_STATE["healthy"] else "unhealthy",
        "ready": SERVICE_STATE["ready"],
        "uptime_seconds": round(time.time() - START_TIME, 2),
        "requests_processed": SERVICE_STATE["total_requests"],
        "memory_buffer_mb": len(SERVICE_STATE["memory_leak_buffer"]) * 10
    }

@app.get("/healthz")
def liveness_probe(response: Response):
    """Kubernetes liveness probe"""
    if not SERVICE_STATE["healthy"]:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "DEAD", "reason": "Simulated pod crash/unhealthy state"}
    return {"status": "UP", "timestamp": time.time()}

@app.get("/ready")
def readiness_probe(response: Response):
    """Kubernetes readiness probe"""
    if not SERVICE_STATE["ready"] or not SERVICE_STATE["healthy"]:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "NOT_READY", "reason": "Readiness probe failed / misconfigured"}
    return {"status": "READY", "port": SERVICE_STATE["port"]}

@app.get("/metrics")
def get_metrics():
    """Prometheus-style metrics endpoint"""
    uptime = time.time() - START_TIME
    mem_mb = len(SERVICE_STATE["memory_leak_buffer"]) * 10 + 25
    lines = [
        f'# HELP web_api_uptime_seconds Total service uptime in seconds',
        f'# TYPE web_api_uptime_seconds gauge',
        f'web_api_uptime_seconds {uptime:.1f}',
        f'# HELP web_api_memory_usage_bytes Current estimated memory usage',
        f'# TYPE web_api_memory_usage_bytes gauge',
        f'web_api_memory_usage_bytes {mem_mb * 1024 * 1024}',
        f'# HELP web_api_http_requests_total Total HTTP requests handled',
        f'# TYPE web_api_http_requests_total counter',
        f'web_api_http_requests_total {SERVICE_STATE["total_requests"]}',
        f'# HELP web_api_http_errors_total Total HTTP 5xx errors generated',
        f'# TYPE web_api_http_errors_total counter',
        f'web_api_http_errors_total {SERVICE_STATE["error_count"]}',
        f'# HELP web_api_healthy Service health flag (1=UP, 0=DOWN)',
        f'# TYPE web_api_healthy gauge',
        f'web_api_healthy {1 if SERVICE_STATE["healthy"] else 0}'
    ]
    return Response(content="\n".join(lines) + "\n", media_type="text/plain")

@app.get("/api/v1/items")
def list_items():
    if not SERVICE_STATE["healthy"]:
        return Response(status_code=500, content='{"error": "Internal Service Error - Pod Crashed"}')
    return {
        "items": [
            {"id": "itm-001", "name": "Compute Cloud Engine", "category": "Infra"},
            {"id": "itm-002", "name": "Kubernetes Ingress Gateway", "category": "Networking"},
            {"id": "itm-003", "name": "Managed Telemetry Store", "category": "Observability"}
        ]
    }

@app.post("/simulate/memory-load")
def simulate_memory_load(size_mb: int = 50):
    """Simulate memory leak / high memory consumption"""
    chunks = size_mb // 10
    for _ in range(max(1, chunks)):
        SERVICE_STATE["memory_leak_buffer"].append(b"X" * (10 * 1024 * 1024))
    
    total_mb = len(SERVICE_STATE["memory_leak_buffer"]) * 10
    oom_triggered = False
    # If simulated usage passes 128MB limit, trigger OOM status
    if total_mb >= 128:
        SERVICE_STATE["healthy"] = False
        oom_triggered = True
        
    return {
        "allocated_mb": size_mb,
        "total_simulated_mb": total_mb,
        "oom_triggered": oom_triggered,
        "status": "OOMKilled" if oom_triggered else "HIGH_MEMORY"
    }

@app.post("/simulate/crash")
def simulate_crash():
    """Simulate container crash / SIGSEGV / unhealthy state"""
    SERVICE_STATE["healthy"] = False
    return {"status": "CRASHED", "message": "Simulated container crash (Exit Code 1)"}

@app.post("/simulate/misconfig")
def simulate_misconfig(broken_probe: bool = True):
    """Simulate readiness probe port mismatch or connection failure"""
    SERVICE_STATE["ready"] = not broken_probe
    return {
        "status": "MISCONFIGURED" if broken_probe else "HEALTHY",
        "ready": SERVICE_STATE["ready"],
        "message": "Readiness probe port 3000 refused (listening on 8080)"
    }

@app.post("/reset")
def reset_service():
    """Reset service state back to 100% healthy"""
    SERVICE_STATE["healthy"] = True
    SERVICE_STATE["ready"] = True
    SERVICE_STATE["memory_leak_buffer"].clear()
    SERVICE_STATE["error_count"] = 0
    return {"status": "RESET", "healthy": True, "ready": True}

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8080"))
    uvicorn.run(app, host="0.0.0.0", port=port)
