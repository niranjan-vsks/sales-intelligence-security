"""Sales intelligence platform over Shodan banner exports."""

import subprocess
from pathlib import Path

__version__ = "0.1.0"


def _pipeline_version() -> str:
    """Git short sha of the checkout this code runs from, or "dev" outside a repo."""
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=Path(__file__).resolve().parent,
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        )
    except (OSError, subprocess.SubprocessError):
        return "dev"
    return out.stdout.strip() or "dev"


PIPELINE_VERSION = _pipeline_version()
