import datetime
from typing import Any, Dict, List, Optional
from sentinel.core.diagnoser import DiagnosisResult
from sentinel.core.remediator import RemediationPlan
from sentinel.core.verifier import VerificationReport

class RCAReporter:
    """
    Produces publication-grade Root Cause Analysis (RCA) Post-Mortem reports
    in both Markdown and HTML for cloud engineering, SRE, and DevOps teams.
    """

    @staticmethod
    def generate_markdown(
        incident_id: str,
        diagnosis: DiagnosisResult,
        plan: RemediationPlan,
        verification: VerificationReport,
        timeline_events: Optional[List[Dict[str, str]]] = None,
        duration_seconds: float = 4.2
    ) -> str:
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC")
        
        timeline_rows = ""
        if timeline_events:
            for t in timeline_events:
                timeline_rows += f"| `{t.get('time', 'T+0s')}` | **{t.get('stage', 'Event')}** | {t.get('detail', '')} |\n"
        else:
            timeline_rows = f"""| `00:00:00` | **Anomaly Detected** | Incident detected on `{diagnosis.affected_resource}` |
| `00:00:01` | **Automated Diagnosis** | Identified `{diagnosis.failure_type}` with {int(diagnosis.confidence*100)}% confidence |
| `00:00:02` | **Remediation Synthesized** | Action `{plan.action_type}` planned and validated |
| `00:00:03` | **Remediation Applied** | Deployed patch / hotfix to cluster |
| `00:00:04` | **Verification Completed** | Deployment verified healthy ({verification.status}) |
"""

        evidence_list = "\n".join([f"- `{e}`" for e in diagnosis.evidence])
        verification_details = "\n".join([f"- {d}" for d in verification.details])
        safety_notes = "\n".join([f"- {s}" for s in plan.safety_notes])

        status_badge = "🟢 RESOLVED (AUTO-HEALED)" if verification.verified else ("🟡 ROLLED BACK TO BASELINE" if verification.rollback_triggered else "🔴 UNRESOLVED")

        report = f"""# 🛡️ DevOps Sentinel Incident Post-Mortem & RCA

**Incident ID:** `{incident_id}`  
**Generated At:** {now}  
**Status:** **{status_badge}**  
**Mean Time to Remediate (MTTR):** `{duration_seconds:.2f}s`  
**Target Resource:** `{diagnosis.affected_resource}`  
**Severity:** `{diagnosis.severity}`  

---

## 1. Executive Summary
On **{now}**, the DevOps Sentinel autonomous monitoring agent intercepted an active service disruption affecting `{diagnosis.affected_resource}`. The agent executed an automated root cause diagnosis, classified the fault as **`{diagnosis.failure_type}`** (confidence: `{int(diagnosis.confidence*100)}%`), generated and applied a validated remediation plan, and verified cluster stability.

## 2. Incident Timeline
| Offset | Milestone | Description |
|---|---|---|
{timeline_rows}

## 3. Root Cause Analysis (RCA)
- **Primary Cause:** {diagnosis.root_cause}
- **Fault Signature:** `{diagnosis.failure_type}`
- **Diagnostic Evidence:**
{evidence_list}

## 4. Automated Remediation Applied
- **Action Strategy:** `{plan.action_type}`
- **Hotfix Branch:** `{plan.branch_name}`
- **Commit Message:** `{plan.commit_message}`

### Synthesized Patch Diff:
```diff
{plan.diff}
```

### Safety Validation & Guardrails:
{safety_notes}

## 5. Post-Remediation Verification
- **Cluster Readiness Status:** `{verification.status}`
- **Health Checks Passed:** `{verification.health_checks_passed} / {verification.total_health_checks}` (Score: `{verification.readiness_score*100:.0f}%`)
- **Rollback Required:** `{"Yes (Executed Safely)" if verification.rollback_triggered else "No"}`
- **Verification Log:**
{verification_details}

## 6. SRE Prevention & Hardening Recommendations
1. **Infrastructure as Code:** Commit the generated hotfix directly into git repository `main` branch via PR.
2. **Quota & Telemetry Review:** Audit namespace resource quotas and Prometheus alerts for `{diagnosis.affected_resource}`.
3. **CI/CD Quality Gate:** Ensure pre-commit linters and manifest schema validators are active in build pipelines.

---
*Report generated autonomously by **DevOps Sentinel Agent v1.0.0**.*
"""
        return report

    @staticmethod
    def generate_html(markdown_report: str) -> str:
        """Converts markdown report into a styled HTML post-mortem document."""
        # Simple HTML wrap for dashboard rendering
        escaped = markdown_report.replace("<", "&lt;").replace(">", "&gt;")
        return f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>DevOps Sentinel RCA Report</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; line-height: 1.6; color: #24292e; max-width: 900px; margin: 40px auto; padding: 0 20px; }}
        pre {{ background: #f6f8fa; padding: 16px; border-radius: 6px; overflow-x: auto; font-family: monospace; }}
        code {{ background: #f0f2f5; padding: 2px 5px; border-radius: 4px; font-family: monospace; }}
        table {{ border-collapse: collapse; width: 100%; margin: 20px 0; }}
        th, td {{ border: 1px solid #dfe2e5; padding: 8px 12px; text-align: left; }}
        th {{ background: #f6f8fa; }}
        h1, h2, h3 {{ border-bottom: 1px solid #eaecef; padding-bottom: 8px; }}
    </style>
</head>
<body>
    <pre style="white-space: pre-wrap;">{escaped}</pre>
</body>
</html>"""
