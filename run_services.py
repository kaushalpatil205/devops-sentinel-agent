#!/usr/bin/env python3
"""
DevOps Sentinel - Multi-Microservice Fleet Supervisor
Launches and manages the entire 5-microservice DevOps agent ecosystem concurrently:
1. sentinel_core (Port 8000) - Autonomous AI Agent Engine, Dashboard & REST API
2. telemetry_collector (Port 8001) - Ingestion & K8s Event / Prometheus Alert Forwarder
3. cicd_runner (Port 8002) - CI/CD Pipeline Simulator & Webhook Engine
4. web_api (Port 8080) - Target Monitored Microservice (Probes, Memory Leaks, Crashes)
5. order_service (Port 8081) - Target Monitored Microservice (Canary Rollouts, Latency)
"""

import os
import sys
import time
import signal
import subprocess
import urllib.request
import urllib.error
from typing import Dict, List, Tuple

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

# Microservice configuration
SERVICES = [
    {
        "name": "sentinel_core",
        "title": "🧠 DevOps Sentinel Core Agent",
        "port": 8000,
        "health_url": "http://127.0.0.1:8000/api/status",
        "cmd": [sys.executable, "-m", "uvicorn", "sentinel.api.server:app", "--host", "0.0.0.0", "--port", "8000"],
        "cwd": BASE_DIR
    },
    {
        "name": "telemetry_collector",
        "title": "📡 Telemetry Collector Service",
        "port": 8001,
        "health_url": "http://127.0.0.1:8001/",
        "cmd": [sys.executable, "services/telemetry_collector/collector.py"],
        "cwd": BASE_DIR
    },
    {
        "name": "cicd_runner",
        "title": "🚀 CI/CD Pipeline Runner Service",
        "port": 8002,
        "health_url": "http://127.0.0.1:8002/",
        "cmd": [sys.executable, "services/cicd_runner/runner.py"],
        "cwd": BASE_DIR
    },
    {
        "name": "web_api",
        "title": "💻 Target Workload: Web API",
        "port": 8080,
        "health_url": "http://127.0.0.1:8080/healthz",
        "cmd": [sys.executable, "services/web_api/app.py"],
        "cwd": BASE_DIR
    },
    {
        "name": "order_service",
        "title": "🛒 Target Workload: Order Service",
        "port": 8081,
        "health_url": "http://127.0.0.1:8081/healthz",
        "cmd": [sys.executable, "services/order_service/app.py"],
        "cwd": BASE_DIR
    }
]

processes: List[Tuple[Dict, subprocess.Popen]] = []

def check_port_listening(url: str, timeout: float = 1.0) -> bool:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "SentinelSupervisor/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status in (200, 503)  # 503 is also alive (probe check)
    except urllib.error.HTTPError as he:
        return he.code in (200, 503)
    except Exception:
        return False

def stop_all_services(signum=None, frame=None):
    print("\n🛑 Shutting down all DevOps Sentinel microservices...")
    for svc, proc in processes:
        if proc.poll() is None:
            try:
                proc.terminate()
                proc.wait(timeout=2)
            except Exception:
                proc.kill()
    print("✅ All microservices stopped successfully.")
    sys.exit(0)

def main():
    signal.signal(signal.SIGINT, stop_all_services)
    signal.signal(signal.SIGTERM, stop_all_services)

    is_test_mode = "--check" in sys.argv or "--test" in sys.argv

    print("=" * 75)
    print("🛡️  DEVOPS SENTINEL MULTI-MICROSERVICE FLEET SUPERVISOR")
    print("=" * 75)
    print(f"Starting {len(SERVICES)} microservices concurrently in local runtime...")

    # Start all services
    for svc in SERVICES:
        env = os.environ.copy()
        env["PORT"] = str(svc["port"])
        env["SENTINEL_CORE_URL"] = "http://127.0.0.1:8000"
        env["WEB_API_URL"] = "http://127.0.0.1:8080"
        env["ORDER_SERVICE_URL"] = "http://127.0.0.1:8081"
        
        proc = subprocess.Popen(
            svc["cmd"],
            cwd=svc["cwd"],
            env=env,
            stdout=subprocess.DEVNULL if is_test_mode else None,
            stderr=subprocess.DEVNULL if is_test_mode else None
        )
        processes.append((svc, proc))
        print(f"  ▶️  Spawned {svc['title']} on port {svc['port']} (PID: {proc.pid})")

    # Polling wait until all are responsive
    print("\nWaiting for all microservices to report healthy...")
    start_wait = time.time()
    all_ready = False
    
    while time.time() - start_wait < 15:
        statuses = [check_port_listening(s["health_url"]) for s in SERVICES]
        if all(statuses):
            all_ready = True
            break
        time.sleep(0.5)

    print("-" * 75)
    if all_ready:
        print("🎉 ALL 5 MICROSERVICES ARE ONLINE AND OPERATIONAL!")
        print("-" * 75)
        print("  • DevOps Sentinel UI & Core API: http://localhost:8000")
        print("  • Telemetry Collector Service:  http://localhost:8001/status")
        print("  • CI/CD Pipeline Runner:        http://localhost:8002/status")
        print("  • Monitored Workload: Web API:  http://localhost:8080/healthz")
        print("  • Monitored Workload: Orders:   http://localhost:8081/healthz")
        print("=" * 75)
    else:
        print("⚠️ Warning: Some services did not report ready within timeout:")
        for s in SERVICES:
            is_up = check_port_listening(s["health_url"])
            print(f"  - {s['title']} (: {s['port']}): {'ONLINE' if is_up else 'TIMEOUT'}")

    if is_test_mode:
        print("\nTest mode check completed. Shutting down...")
        stop_all_services()
        return

    print("\nPress Ctrl+C at any time to gracefully stop all services.")
    try:
        while True:
            time.sleep(1)
            # Check if any process crashed unexpectedly
            for svc, proc in processes:
                ret = proc.poll()
                if ret is not None:
                    print(f"❌ Service '{svc['name']}' exited unexpectedly with code {ret}!")
    except KeyboardInterrupt:
        stop_all_services()

if __name__ == "__main__":
    main()
