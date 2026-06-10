from pathlib import Path
from typing import Any, Dict, Optional

import yaml


BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG_PATH = BASE_DIR / "config.yaml"


def load_config(config_path: Optional[str] = None) -> Dict[str, Any]:
    """Load YAML config.

    If config_path is not provided, load config.yaml from the project root.
    """
    path = Path(config_path) if config_path else DEFAULT_CONFIG_PATH

    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    with path.open("r", encoding="utf-8") as f:
        config = yaml.safe_load(f) or {}

    return config