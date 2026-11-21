"""
Order Service Microservice - Target Monitored Workload
Exposes e-commerce checkout flow, canary deployments (v1 vs v2),
synthetic latency injection, error-rate spikes, and health probes.
"""

import os
import time
import random
from typing import Dict, List, Optional
from fastapi import FastAPI, Response, status
from pydantic import BaseModel

app = FastAPI(
    title="Target Workload: Order Processing Microservice",
    version="1.9.0",
    description="E-Commerce order fulfillment service with canary release controls monitored by DevOps Sentinel"
)

START_TIME = time.time()
SERVICE_STATE = {
    "healthy": True,
    "ready": True,
    "active_version": "v1.9.0",
    "canary_enabled": False,
    "canary_version": "v2.0.0-rc1",
    "canary_traffic_percent": 0,
    "error_rate_spike": False,
    "simulated_latency_sec": 0.0,
    "total_orders": 0,
    "failed_orders": 0
}

class CreateOrderRequest(BaseModel):
    item_id: str
    quantity: int = 1
    customer_id: str

class CanaryConfigRequest(BaseModel):
    enabled: bool
    traffic_percent: int = 20
    inject_errors: bool = False
    latency_sec: float = 0.0

@app.get("/")
def get_root():
    return {
        "service": "order-service",
        "active_version": SERVICE_STATE["active_version"],
        "canary_enabled": SERVICE_STATE["canary_enabled"],
        "canary_version": SERVICE_STATE["canary_version"] if SERVICE_STATE["canary_enabled"] else None,
        "traffic_split": f"{100 - SERVICE_STATE['canary_traffic_percent']}% v1 / {SERVICE_STATE['canary_traffic_percent']}% canary",
        "error_rate_active": SERVICE_STATE["error_rate_spike"],
        "simulated_latency": f"{SERVICE_STATE['simulated_latency_sec']}s",
        "total_orders": SERVICE_STATE["total_orders"],
        "failed_orders": SERVICE_STATE["failed_orders"],
        "uptime_seconds": round(time.time() - START_TIME, 2)
    }

@app.get("/healthz")
def liveness_probe(response: Response):
    if not SERVICE_STATE["healthy"]:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "DEAD", "reason": "Order service internal panic"}
    return {"status": "UP", "version": SERVICE_STATE["active_version"]}

@app.get("/ready")
def readiness_probe(response: Response):
    if not SERVICE_STATE["ready"]:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "NOT_READY", "reason": "Database connection pool saturated"}
    return {"status": "READY"}

@app.get("/metrics")
def get_metrics():
    """Prometheus-style metrics endpoint"""
    uptime = time.time() - START_TIME
    error_rate = (SERVICE_STATE["failed_orders"] / max(1, SERVICE_STATE["total_orders"])) * 100
    lines = [
        f'# HELP order_service_uptime_seconds Total service uptime',
        f'# TYPE order_service_uptime_seconds gauge',
        f'order_service_uptime_seconds {uptime:.1f}',
        f'# HELP order_service_orders_total Total orders placed',
        f'# TYPE order_service_orders_total counter',
        f'order_service_orders_total {SERVICE_STATE["total_orders"]}',
        f'# HELP order_service_failed_orders_total Total failed orders',
        f'# TYPE order_service_failed_orders_total counter',
        f'order_service_failed_orders_total {SERVICE_STATE["failed_orders"]}',
        f'# HELP order_service_error_rate_percent Percentage of failing orders',
        f'# TYPE order_service_error_rate_percent gauge',
        f'order_service_error_rate_percent {error_rate:.2f}'
    ]
    return Response(content="\n".join(lines) + "\n", media_type="text/plain")

@app.post("/api/orders")
def create_order(order: CreateOrderRequest, response: Response):
    SERVICE_STATE["total_orders"] += 1
    
    # Inject latency if configured
    if SERVICE_STATE["simulated_latency_sec"] > 0:
        time.sleep(SERVICE_STATE["simulated_latency_sec"])
        
    # Check if canary is routed
    is_canary = False
    if SERVICE_STATE["canary_enabled"] and random.randint(1, 100) <= SERVICE_STATE["canary_traffic_percent"]:
        is_canary = True
        
    # Check error simulation
    if SERVICE_STATE["error_rate_spike"] or (is_canary and SERVICE_STATE["canary_enabled"]):
        # Simulate canary 500 error spike
        SERVICE_STATE["failed_orders"] += 1
        response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        return {
            "error": "InternalServerError: NullPointerException in checkout pipeline",
            "served_by": SERVICE_STATE["canary_version"] if is_canary else SERVICE_STATE["active_version"],
            "canary": is_canary
        }

    return {
        "order_id": f"ord-{int(time.time()*1000)}",
        "customer_id": order.customer_id,
        "item_id": order.item_id,
        "quantity": order.quantity,
        "status": "CONFIRMED",
        "served_by": SERVICE_STATE["canary_version"] if is_canary else SERVICE_STATE["active_version"],
        "canary": is_canary
    }

@app.post("/simulate/canary")
def configure_canary(config: CanaryConfigRequest):
    """Enable or configure canary deployment with simulated failures"""
    SERVICE_STATE["canary_enabled"] = config.enabled
    SERVICE_STATE["canary_traffic_percent"] = config.traffic_percent
    SERVICE_STATE["error_rate_spike"] = config.inject_errors
    SERVICE_STATE["simulated_latency_sec"] = config.latency_sec
    return {
        "status": "CANARY_CONFIGURED",
        "canary_enabled": SERVICE_STATE["canary_enabled"],
        "traffic_percent": SERVICE_STATE["canary_traffic_percent"],
        "error_injection": SERVICE_STATE["error_rate_spike"]
    }

@app.post("/simulate/rollback")
def rollback_canary():
    """Execute rollback back to stable v1"""
    SERVICE_STATE["canary_enabled"] = False
    SERVICE_STATE["canary_traffic_percent"] = 0
    SERVICE_STATE["error_rate_spike"] = False
    SERVICE_STATE["simulated_latency_sec"] = 0.0
    SERVICE_STATE["active_version"] = "v1.9.0"
    SERVICE_STATE["healthy"] = True
    SERVICE_STATE["ready"] = True
    return {
        "status": "ROLLED_BACK",
        "active_version": SERVICE_STATE["active_version"],
        "canary_enabled": False,
        "message": "Successfully aborted canary deployment and rolled back to stable revision v1.9.0"
    }

@app.post("/reset")
def reset_service():
    SERVICE_STATE["healthy"] = True
    SERVICE_STATE["ready"] = True
    SERVICE_STATE["canary_enabled"] = False
    SERVICE_STATE["canary_traffic_percent"] = 0
    SERVICE_STATE["error_rate_spike"] = False
    SERVICE_STATE["simulated_latency_sec"] = 0.0
    SERVICE_STATE["failed_orders"] = 0
    return {"status": "RESET", "healthy": True}

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8081"))
    uvicorn.run(app, host="0.0.0.0", port=port)
