from datetime import datetime
from pathlib import Path
from typing import Any, Dict

from utils.config import BASE_DIR


def build_report(summary_body: str) -> str:
    """Build final Markdown report."""
    today = datetime.now().strftime("%Y-%m-%d")

    return f"""# 📡 TechPulse 技术追踪 | {today}

{summary_body.strip()}

---
由 TechPulse Auto-Push 自动生成。
"""


def save_report(report: str, config: Dict[str, Any]) -> Path:
    """Save report to output directory and return file path."""
    output_cfg = config.get("output", {})
    archive_dir = output_cfg.get("archive_dir", "output")
    report_prefix = output_cfg.get("report_prefix", "techpulse")

    output_dir = Path(archive_dir)
    if not output_dir.is_absolute():
        output_dir = BASE_DIR / output_dir

    output_dir.mkdir(parents=True, exist_ok=True)

    today = datetime.now().strftime("%Y-%m-%d")
    report_path = output_dir / f"{report_prefix}_{today}.md"

    report_path.write_text(report, encoding="utf-8")
    return report_path