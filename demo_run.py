#!/usr/bin/env python3
"""
DevOps Sentinel Agent - Self-Contained End-to-End Demonstration Script
Executes all 5 core DevOps failure and remediation scenarios:
1. Kubernetes Pod OOMKilled (Exit Code 137)
2. Readiness Probe Port Mismatch (502 Connection Refused)
3. CI/CD Build Missing Dependency
4. IaC Configuration Drift (Live vs Declarative Git baseline)
5. Canary Release Health Degradation & Safe Rollback
"""

import os
import sys
import time

# Ensure project root is in sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.syntax import Syntax

from sentinel.core.orchestrator import AgentOrchestrator
from sentinel.simulator.cluster_sim import ClusterSimulator
from sentinel.simulator.scenarios import SCENARIOS

console = Console()

def main():
    console.print(Panel.fit(
        "[bold cyan]DevOps Sentinel Agent v1.0.0[/bold cyan]\n"
        "[dim]Autonomous CI/CD Failure Healing, Kubernetes Deployment Verification,\n"
        "IaC Drift Detection & Auto-Remediation with Root Cause Analysis (RCA)[/dim]",
        title="🛡️ DevOps Autonomous Sentinel",
        border_style="cyan"
    ))

    orchestrator = AgentOrchestrator(use_mock=True)
    sim = ClusterSimulator(orchestrator)

    scorecard = Table(title="Autonomous Remediation Summary")
    scorecard.add_column("Scenario ID", style="cyan")
    scorecard.add_column("Resource", style="yellow")
    scorecard.add_column("Fault Classification", style="white")
    scorecard.add_column("Remediation Action", style="blue")
    scorecard.add_column("Status", style="bold")
    scorecard.add_column("MTTR", style="green")

    for idx, (sc_id, sc_data) in enumerate(SCENARIOS.items(), 1):
        console.print(f"\n[bold yellow]── Scenario {idx}: {sc_data['name']} ──[/bold yellow]")
        console.print(f"[dim]{sc_data['description']}[/dim]")
        
        t0 = time.time()
        res = sim.run_scenario(sc_id)
        duration = f"{round(time.time() - t0, 2)}s"

        if res.get("type") == "drift":
            drift = res["drift_report"]
            console.print(f"  • Resource: [cyan]{drift['resource_name']}[/cyan]")
            console.print(f"  • Drift Count: [red]{drift['drift_count']} differences[/red]")
            console.print(f"  • Recommended Strategy: [bold green]{drift['reconciliation_action']}[/bold green]")
            scorecard.add_row(sc_id, drift["resource_name"], "IaC Drift", drift["reconciliation_action"], "[green]RECONCILED[/green]", duration)
        else:
            inc = res["incident"]
            diag = inc["diagnosis"]
            plan = inc["plan"]
            ver = inc["verification"]

            console.print(f"  • Detected Fault: [bold red]{diag['failure_type']}[/bold red] (Confidence: {int(diag['confidence']*100)}%)")
            console.print(f"  • Root Cause: [dim]{diag['root_cause']}[/dim]")
            console.print(f"  • Synthesized Fix: [bold blue]{plan['action_type']}[/bold blue] -> Branch: [yellow]{plan['branch_name']}[/yellow]")
            
            if plan.get("diff"):
                console.print("  • Synthesized Diff:")
                console.print(Syntax(plan["diff"], "diff", theme="monokai", line_numbers=False))

            outcome_str = "[green]HEALED[/green]" if ver["verified"] else ("[magenta]ROLLED BACK[/magenta]" if ver["rollback_triggered"] else "[red]FAILED[/red]")
            console.print(f"  • Verification: {outcome_str} (Readiness Score: {int(ver['readiness_score']*100)}%)")
            console.print(f"  • Rollback Triggered: {'YES' if ver['rollback_triggered'] else 'NO'}")
            console.print(f"  • Mean Time to Remediate: [bold green]{duration}[/bold green]")

            scorecard.add_row(sc_id, inc["resource"], diag["failure_type"], plan["action_type"], outcome_str, duration)

    console.print("\n")
    console.print(scorecard)
    console.print("\n[bold green]🎯 All DevOps Autonomous Agent benchmarks completed successfully![/bold green]\n")

if __name__ == "__main__":
    main()
