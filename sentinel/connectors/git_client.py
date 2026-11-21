import logging
import os
import subprocess
from typing import Any, Dict, List, Optional

logger = logging.getLogger("sentinel.git")

class GitClient:
    """
    Git wrapper for creating hotfix branches, staging automated remediation patches,
    and generating diffs for developer review.
    """
    def __init__(self, repo_path: str = ".", mock_mode: bool = False):
        self.repo_path = repo_path
        self.mock_mode = mock_mode
        self._mock_commits: List[Dict[str, Any]] = []
        self._current_mock_branch: str = "main"

    def _run_git(self, args: List[str]) -> Dict[str, Any]:
        if self.mock_mode:
            return {"exit_code": 0, "stdout": "mock git response", "stderr": ""}
        try:
            cmd = ["git"] + args
            res = subprocess.run(cmd, cwd=self.repo_path, capture_output=True, text=True, timeout=10)
            return {
                "exit_code": res.returncode,
                "stdout": res.stdout.strip(),
                "stderr": res.stderr.strip()
            }
        except Exception as e:
            logger.warning(f"Git command failed: {e}. Falling back to mock operation.")
            return {"exit_code": 1, "stdout": "", "stderr": str(e)}

    def get_current_branch(self) -> str:
        if self.mock_mode:
            return self._current_mock_branch
        res = self._run_git(["rev-parse", "--abbrev-ref", "HEAD"])
        return res["stdout"] if res["exit_code"] == 0 else "main"

    def create_and_checkout_branch(self, branch_name: str) -> bool:
        """Create a dedicated remediation branch (e.g., sentinel-hotfix/oom-fix)."""
        if self.mock_mode:
            self._current_mock_branch = branch_name
            return True
        res = self._run_git(["checkout", "-b", branch_name])
        if res["exit_code"] != 0:
            # Maybe already exists
            res = self._run_git(["checkout", branch_name])
        return res["exit_code"] == 0

    def commit_patch(self, file_paths: List[str], message: str) -> Dict[str, Any]:
        """Stages modified files and commits with conventional commit message."""
        if self.mock_mode:
            commit_record = {
                "branch": self._current_mock_branch,
                "files": file_paths,
                "message": message,
                "commit_hash": "a1b2c3d4"
            }
            self._mock_commits.append(commit_record)
            return {"success": True, "commit": "a1b2c3d4", "message": message}

        # Stage files
        for f in file_paths:
            self._run_git(["add", f])
        
        res = self._run_git(["commit", "-m", message])
        if res["exit_code"] == 0:
            rev = self._run_git(["rev-parse", "--short", "HEAD"])
            commit_hash = rev["stdout"] if rev["exit_code"] == 0 else "head"
            return {"success": True, "commit": commit_hash, "message": message}
        return {"success": False, "error": res["stderr"]}

    def get_diff(self, file_path: Optional[str] = None) -> str:
        """Retrieve unified git diff."""
        if self.mock_mode:
            return "--- a/manifest.yaml\n+++ b/manifest.yaml\n@@ -10,3 +10,3 @@\n- memory: 128Mi\n+ memory: 512Mi"
        args = ["diff"]
        if file_path:
            args.append(file_path)
        res = self._run_git(args)
        return res["stdout"]
