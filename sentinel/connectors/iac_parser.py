import os
import re
from typing import Any, Dict, List, Optional, Tuple
import yaml

class IaCParser:
    """
    Parser and reconciler for Kubernetes YAML manifests, Dockerfiles, and IaC specs.
    Provides diff analysis, structural validation, and safe AST/text patching.
    """

    @staticmethod
    def load_yaml(file_path: str) -> Dict[str, Any]:
        """Loads a YAML file safely."""
        with open(file_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)

    @staticmethod
    def dump_yaml(data: Dict[str, Any], file_path: str) -> None:
        """Saves a dictionary to a YAML file."""
        with open(file_path, "w", encoding="utf-8") as f:
            yaml.dump(data, f, default_flow_style=False, sort_keys=False)

    @staticmethod
    def compare_specs(desired: Dict[str, Any], actual: Dict[str, Any], path: str = "") -> List[Dict[str, Any]]:
        """
        Recursively detects drift between desired configuration (Git/IaC) and live runtime state.
        Returns a list of detected drift records with JSONPath, desired value, and actual value.
        """
        drifts = []
        # Check all keys in desired
        for key, desired_val in desired.items():
            curr_path = f"{path}.{key}" if path else key
            if key not in actual:
                drifts.append({
                    "path": curr_path,
                    "drift_type": "MISSING_IN_LIVE",
                    "desired": desired_val,
                    "actual": None
                })
            else:
                actual_val = actual[key]
                if isinstance(desired_val, dict) and isinstance(actual_val, dict):
                    drifts.extend(IaCParser.compare_specs(desired_val, actual_val, curr_path))
                elif desired_val != actual_val:
                    drifts.append({
                        "path": curr_path,
                        "drift_type": "VALUE_MISMATCH",
                        "desired": desired_val,
                        "actual": actual_val
                    })
        
        # Check for unexpected items in actual that shouldn't be there
        for key, actual_val in actual.items():
            curr_path = f"{path}.{key}" if path else key
            if key not in desired:
                drifts.append({
                    "path": curr_path,
                    "drift_type": "EXTRA_IN_LIVE",
                    "desired": None,
                    "actual": actual_val
                })

        return drifts

    @staticmethod
    def patch_k8s_memory_limit(manifest_text: str, container_name: str, new_memory: str) -> str:
        """Patches container memory limit in a Kubernetes YAML string."""
        pattern = r"(limits:\s*\n\s*memory:\s*)[^\n]+"
        if re.search(pattern, manifest_text):
            return re.sub(pattern, rf"\g<1>{new_memory}", manifest_text)
        
        # If no limits block, insert one under resources
        resources_pattern = r"(resources:\s*\n)"
        if re.search(resources_pattern, manifest_text):
            replacement = rf"\g<1>          limits:\n            memory: {new_memory}\n"
            return re.sub(resources_pattern, replacement, manifest_text, count=1)
        
        return manifest_text

    @staticmethod
    def patch_k8s_probe_port(manifest_text: str, old_port: int, new_port: int) -> str:
        """Updates probe port or container port in a Kubernetes manifest."""
        return re.sub(rf"port:\s*{old_port}\b", f"port: {new_port}", manifest_text)

    @staticmethod
    def patch_dockerfile_dependency(dockerfile_text: str, missing_pkg: str) -> str:
        """Injects missing system or Python dependency into Dockerfile RUN command."""
        lines = dockerfile_text.splitlines()
        patched_lines = []
        injected = False

        for line in lines:
            if not injected and line.strip().startswith("RUN pip install"):
                patched_lines.append(f"{line} {missing_pkg}")
                injected = True
            elif not injected and line.strip().startswith("RUN apt-get update"):
                patched_lines.append(f"{line} {missing_pkg}")
                injected = True
            else:
                patched_lines.append(line)

        if not injected:
            # Fallback append
            patched_lines.append(f"RUN pip install --no-cache-dir {missing_pkg}")

        return "\n".join(patched_lines)
