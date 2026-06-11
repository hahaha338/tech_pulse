from typing import Any, Dict, List


def _template_summary(
    external_data: Dict[str, List[Dict[str, Any]]],
    config: Dict[str, Any],
) -> str:
    """Build a deterministic Markdown summary from collected trend data."""
    external_cfg = config.get("external", {})
    max_report_items = int(external_cfg.get("max_report_items_per_section", 5))

    lines = [
        "## 1. 外部影像技术趋势",
        "",
    ]

    tech_items = external_data.get("tech", [])
    if not tech_items:
        lines.append("- 本周期无明显外部影像技术更新。")
    else:
        for item in tech_items[: max(3, max_report_items // 2)]:
            title = item.get("title", "")
            source = item.get("source", "")
            publisher = item.get("publisher", "")
            published = item.get("published", "")
            link = item.get("link", "")
            lines.append(f"- {title}")
            source_parts = [part for part in [source, publisher, published] if part]
            if source_parts:
                lines.append(f"  来源/时间：{' | '.join(source_parts)}")
            if link:
                lines.append(f"  链接：{link}")

    lines.extend(
        [
            "",
            "## 2. 大手机厂商影像发展趋势",
            "",
        ]
    )

    oem_items = external_data.get("oem", [])
    if not oem_items:
        lines.append("- 本周期无明显手机厂商影像趋势更新。")
    else:
        for item in oem_items[:max_report_items]:
            title = item.get("title", "")
            source = item.get("source", "")
            publisher = item.get("publisher", "")
            published = item.get("published", "")
            link = item.get("link", "")
            lines.append(f"- {title}")
            source_parts = [part for part in [source, publisher, published] if part]
            if source_parts:
                lines.append(f"  来源/时间：{' | '.join(source_parts)}")
            if link:
                lines.append(f"  链接：{link}")

    return "\n".join(lines).strip()


def summarize(
    external_data: Dict[str, List[Dict[str, Any]]],
    config: Dict[str, Any],
    logger=None,
) -> str:
    """Summarize collected external trend data without external LLM services."""
    if logger:
        logger.info("Generating template summary")

    return _template_summary(external_data, config)