import os
from dataclasses import dataclass, field
from typing import List, Optional

@dataclass
class SentinelConfig:
    """Global configuration for the DevOps Sentinel Agent."""
    app_name: str = "DevOps Sentinel Agent"
    version: str = "1.0.0"
    env: str = os.getenv("SENTINEL_ENV", "simulation")  # "simulation" or "live"
    
    # K8s settings
    kubeconfig_path: Optional[str] = os.getenv("KUBECONFIG", None)
    default_namespace: str = os.getenv("K8S_NAMESPACE", "default")
    health_check_timeout_secs: int = int(os.getenv("HEALTH_CHECK_TIMEOUT", "30"))
    health_check_retries: int = int(os.getenv("HEALTH_CHECK_RETRIES", "3"))
    
    # Auto-remediation policy
    auto_remediate: bool = os.getenv("AUTO_REMEDIATE", "true").lower() in ("true", "1", "yes")
    require_human_approval: bool = os.getenv("REQUIRE_HUMAN_APPROVAL", "false").lower() in ("true", "1", "yes")
    max_remediation_attempts: int = int(os.getenv("MAX_REMEDIATION_ATTEMPTS", "3"))
    auto_rollback_on_failure: bool = os.getenv("AUTO_ROLLBACK", "true").lower() in ("true", "1", "yes")
    
    # Git & IaC settings
    git_repo_path: str = os.getenv("GIT_REPO_PATH", ".")
    manifests_dir: str = os.getenv("MANIFESTS_DIR", "./manifests")
    auto_commit_patches: bool = True
    branch_prefix: str = "sentinel-hotfix/"
    
    # Server / UI settings
    server_host: str = os.getenv("SENTINEL_HOST", "0.0.0.0")
    server_port: int = int(os.getenv("SENTINEL_PORT", "8000"))
    
    # Supported error signatures
    monitored_failure_types: List[str] = field(default_factory=lambda: [
        "CrashLoopBackOff",
        "OOMKilled",
        "ImagePullBackOff",
        "ReadinessProbeFailed",
        "PortMismatch",
        "ConfigDrift",
        "BuildDependencyMissing",
        "DockerfileSyntaxError",
        "CanaryHealthBreach"
    ])

config = SentinelConfig()
