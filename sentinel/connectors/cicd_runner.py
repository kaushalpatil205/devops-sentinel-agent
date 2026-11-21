import logging
import subprocess
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger("sentinel.cicd")

@dataclass
class PipelineStage:
    name: str
    command: Optional[str] = None
    status: str = "PENDING"  # PENDING, RUNNING, PASSED, FAILED, SKIPPED
    duration_secs: float = 0.0
    stdout: str = ""
    stderr: str = ""
    error_code: int = 0

@dataclass
class PipelineRun:
    pipeline_id: str
    commit_sha: str
    branch: str
    stages: List[PipelineStage] = field(default_factory=list)
    overall_status: str = "PENDING"
    started_at: float = field(default_factory=time.time)
    finished_at: Optional[float] = None

class CICDRunner:
    """
    CI/CD pipeline orchestrator that runs or simulates pipeline stages (Lint, Test, Docker Build, K8s Deploy).
    Captures exact stage logs, triggers remediation agents on failures, and resumes execution.
    """
    def __init__(self, mock_mode: bool = True):
        self.mock_mode = mock_mode
        self.runs: Dict[str, PipelineRun] = {}

    def trigger_pipeline(self, pipeline_id: str, commit_sha: str, branch: str, stages: Optional[List[PipelineStage]] = None) -> PipelineRun:
        if not stages:
            stages = [
                PipelineStage(name="lint", command="flake8 sentinel/"),
                PipelineStage(name="unit-tests", command="pytest tests/"),
                PipelineStage(name="docker-build", command="docker build -t app:latest ."),
                PipelineStage(name="k8s-deploy", command="kubectl apply -f manifests/")
            ]
        run = PipelineRun(
            pipeline_id=pipeline_id,
            commit_sha=commit_sha,
            branch=branch,
            stages=stages
        )
        self.runs[pipeline_id] = run
        return run

    def execute_stage(self, stage: PipelineStage, custom_exec: Optional[Callable[[], Tuple[int, str, str]]] = None) -> bool:
        stage.status = "RUNNING"
        t0 = time.time()

        if custom_exec:
            code, out, err = custom_exec()
            stage.duration_secs = round(time.time() - t0, 2)
            stage.stdout = out
            stage.stderr = err
            stage.error_code = code
            stage.status = "PASSED" if code == 0 else "FAILED"
            return code == 0

        if self.mock_mode or not stage.command:
            stage.duration_secs = 0.5
            stage.status = "PASSED"
            stage.stdout = f"Stage {stage.name} simulated successfully."
            return True

        try:
            res = subprocess.run(stage.command, shell=True, capture_output=True, text=True, timeout=60)
            stage.duration_secs = round(time.time() - t0, 2)
            stage.stdout = res.stdout
            stage.stderr = res.stderr
            stage.error_code = res.returncode
            stage.status = "PASSED" if res.returncode == 0 else "FAILED"
            return res.returncode == 0
        except Exception as e:
            stage.duration_secs = round(time.time() - t0, 2)
            stage.stderr = str(e)
            stage.error_code = 1
            stage.status = "FAILED"
            return False
