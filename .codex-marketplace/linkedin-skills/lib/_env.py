"""Load configuration from the plugin's own .env file only."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

_ENV_LOADED = False


def load_env(force: bool = False, env_path: Optional[Path] = None) -> None:
    """Load environment variables from one trusted, explicit location.

    Safe no-op if python-dotenv is missing, preserving Tier 0 (manual)
    zero-dependency operation. By default only the repository/plugin root is
    considered. Set ``LINKEDIN_SKILLS_ENV_FILE`` or pass ``env_path`` to use a
    different file deliberately. The caller's working directory is never
    searched, and existing process environment variables are preserved.
    """
    global _ENV_LOADED
    if _ENV_LOADED and not force:
        return

    try:
        from dotenv import load_dotenv

        configured = os.getenv("LINKEDIN_SKILLS_ENV_FILE")
        selected = Path(configured).expanduser() if configured else env_path
        selected = selected or (Path(__file__).resolve().parents[1] / ".env")
        if selected.is_file():
            load_dotenv(selected, override=False)
    except ImportError:
        pass

    _ENV_LOADED = True
