"""Configuration helpers for the MCP runner bridge."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping, Optional

DEFAULT_BASE_URL = "http://127.0.0.1:8000"
DEFAULT_REPORT_ROOT = Path("reports")
DEFAULT_SCREENSHOT_ROOT = Path("reports")


@dataclass
class RunnerAuth:
    """
    Authentication material for the runner API.

    The slots optimization is removed for compatibility with Python 3.9+,
    as some environments may have older Python versions in their path.
    """

    token: Optional[str] = None

    def headers(self) -> Mapping[str, str]:
        """Return HTTP headers for authenticated requests."""
        if not self.token:
            return {}
        return {"Authorization": f"Bearer {self.token}"}


@dataclass
class ServerConfig:
    """
    Resolved configuration for the MCP server instance.

    This config is loaded from environment variables at startup, allowing
    the MCP server to connect to different runner backend instances without
    code changes. See from_env() for the complete list of env vars.
    """

    base_url: str = DEFAULT_BASE_URL
    auth: RunnerAuth = field(default_factory=RunnerAuth)
    report_dir: Path = DEFAULT_REPORT_ROOT
    screenshot_dir: Path = DEFAULT_SCREENSHOT_ROOT

    @classmethod
    def from_env(cls) -> "ServerConfig":
        """Construct a configuration object based on environment variables."""

        base_url = os.getenv("RUNNER_BASE_URL", DEFAULT_BASE_URL).rstrip("/")
        report_dir = Path(
            os.getenv("RUNNER_REPORT_DIR", str(DEFAULT_REPORT_ROOT))
        ).expanduser()
        screenshot_dir = Path(
            os.getenv("RUNNER_SCREENSHOT_DIR", str(DEFAULT_SCREENSHOT_ROOT))
        ).expanduser()
        auth = RunnerAuth(token=_read_token_from_env())
        return cls(
            base_url=base_url,
            auth=auth,
            report_dir=report_dir,
            screenshot_dir=screenshot_dir,
        )


def _read_token_from_env() -> Optional[str]:
    """Read an API token from `RUNNER_API_KEY` or the file located at `RUNNER_API_KEY_PATH`."""

    direct = os.getenv("RUNNER_API_KEY")
    if direct:
        return direct.strip()
    path_value = os.getenv("RUNNER_API_KEY_PATH")
    if not path_value:
        return None
    path = Path(path_value).expanduser()
    if not path.exists():
        return None
    try:
        data = path.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    if not data:
        return None
    try:
        payload = json.loads(data)
    except json.JSONDecodeError:
        return data
    # Support JSON payloads such as {"token": "..."}
    if isinstance(payload, Mapping):
        for key in ("token", "api_key", "key"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    if isinstance(payload, str):
        return payload.strip()
    return None


__all__ = ["RunnerAuth", "ServerConfig"]
