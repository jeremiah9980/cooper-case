"""Configuration loading and defaults."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any


DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)


@dataclass
class NotifyConfig:
    console: bool = True
    webhook_url: str = ""
    webhook_format: str = "slack"  # slack | discord | generic


@dataclass
class Config:
    case_number: str = "24-CR-1362"
    portal_base_url: str = "https://portalnav19.galvestoncountytx.gov/Portal"
    case_detail_url: str = ""
    data_dir: str = "data"
    poll_interval_seconds: int = 420  # 7 minutes
    headless: bool = True
    user_agent: str = DEFAULT_UA
    notify: NotifyConfig = field(default_factory=NotifyConfig)

    # --- paths derived from data_dir ---------------------------------------
    @property
    def data_path(self) -> Path:
        return Path(self.data_dir)

    @property
    def state_file(self) -> Path:
        """Playwright storage state (cookies) captured during bootstrap."""
        return self.data_path / "session_state.json"

    @property
    def latest_snapshot_file(self) -> Path:
        return self.data_path / "latest_snapshot.json"

    @property
    def snapshots_dir(self) -> Path:
        return self.data_path / "snapshots"

    @property
    def changelog_file(self) -> Path:
        return self.data_path / "changelog.jsonl"

    @property
    def bootstrap_file(self) -> Path:
        """Stores the captured case_detail_url from a bootstrap run."""
        return self.data_path / "bootstrap.json"

    @property
    def dashboard_file(self) -> Path:
        return self.data_path / "dashboard.html"

    def ensure_dirs(self) -> None:
        self.data_path.mkdir(parents=True, exist_ok=True)
        self.snapshots_dir.mkdir(parents=True, exist_ok=True)

    def resolved_case_detail_url(self) -> str:
        """Detail URL from config, falling back to a saved bootstrap result."""
        if self.case_detail_url:
            return self.case_detail_url
        if self.bootstrap_file.exists():
            try:
                data = json.loads(self.bootstrap_file.read_text())
                return data.get("case_detail_url", "")
            except (json.JSONDecodeError, OSError):
                return ""
        return ""


def _env_overrides(cfg: Config) -> None:
    """Environment variables override file/default values where set."""
    if v := os.environ.get("GALV_CASE_NUMBER"):
        cfg.case_number = v
    if v := os.environ.get("GALV_CASE_DETAIL_URL"):
        cfg.case_detail_url = v
    if v := os.environ.get("GALV_DATA_DIR"):
        cfg.data_dir = v
    if v := os.environ.get("GALV_POLL_INTERVAL"):
        cfg.poll_interval_seconds = int(v)
    if v := os.environ.get("GALV_WEBHOOK_URL"):
        cfg.notify.webhook_url = v
    if v := os.environ.get("GALV_HEADLESS"):
        cfg.headless = v.strip().lower() not in ("0", "false", "no")


def load_config(path: str | os.PathLike[str] | None = None) -> Config:
    """Load config from a JSON file (if present), then apply env overrides.

    Missing file is fine -- defaults + env vars are used.
    """
    data: dict[str, Any] = {}
    if path:
        p = Path(path)
        if p.exists():
            data = json.loads(p.read_text())
    elif Path("config.json").exists():
        data = json.loads(Path("config.json").read_text())

    notify_data = data.get("notify", {}) or {}
    notify = NotifyConfig(
        console=notify_data.get("console", True),
        webhook_url=notify_data.get("webhook_url", ""),
        webhook_format=notify_data.get("webhook_format", "slack"),
    )
    cfg = Config(
        case_number=data.get("case_number", Config.case_number),
        portal_base_url=data.get("portal_base_url", Config.portal_base_url),
        case_detail_url=data.get("case_detail_url", ""),
        data_dir=data.get("data_dir", Config.data_dir),
        poll_interval_seconds=data.get("poll_interval_seconds", Config.poll_interval_seconds),
        headless=data.get("headless", Config.headless),
        user_agent=data.get("user_agent", DEFAULT_UA),
        notify=notify,
    )
    _env_overrides(cfg)
    return cfg


def config_to_dict(cfg: Config) -> dict[str, Any]:
    d = asdict(cfg)
    return d
