import os
from typing import Any, Dict, List

import requests


def _format_external_items(items: List[Dict[str, Any]]) -> str:
    if not items:
        return "- 本周期无明显更新。"

    lines = []
    for item in items:
        title = item.get("title", "")
        source = item.get("source", "")
        link = item.get("link", "")
        published = item.get("published", "")
        summary = item.get("summary", "")

        line = f"- [{source}] {title}"
        if published:
            line += f" | {published}"
        if link:
            line += f"\n  链接：{link}"
        if summary:
            line += f"\n  摘要：{summary}"

        lines.append(line)

    return "\n".join(lines)


def _build_prompt(
    external_data: Dict[str, List[Dict[str, Any]]],
    config: Dict[str, Any],
) -> str:
    external_cfg = config.get("external", {})
    max_report_items = int(external_cfg.get("max_report_items_per_section", 5))

    tech_text = _format_external_items(external_data.get("tech", [])[:max_report_items])
    oem_text = _format_external_items(external_data.get("oem", [])[:max_report_items])

    return f"""
你是 Camera / ISP / Computational Photography 技术分析助手。

请基于输入内容生成 Markdown 中文摘要。
不要编造输入中不存在的信息。
不要输出一级标题，直接从 "## 1. 外部影像技术趋势" 开始。
不要输出英文翻译，不要输出 "English:" 字段。

输出结构必须为：

## 1. 外部影像技术趋势
- 中文摘要：

## 2. 大手机厂商影像发展趋势
- 中文摘要：

要求：
1. 如果某部分没有有效数据，写“本周期无明显更新”。
2. 每个部分最多 {max_report_items} 条。
3. 每条中文不超过 80 字。
4. 优先关注 camera、ISP、IQ、HDR、AF、sensor、AI imaging、computational photography。
5. 手机厂商趋势只关注厂商近期发布、预热、曝光或报道的影像新技术，例如传感器、长焦、潜望、HDR、ISP、AI 影像、计算摄影、夜景、人像算法等。
6. 忽略榜单、导购、评测、横评、DxOMark 排名、价格和促销类内容。
7. 输入标题如果是英文，可以保留原始标题，但摘要和解释必须使用中文。

输入内容如下：

[External Imaging Tech Trends]
{tech_text}

[Smartphone OEM Imaging Trends]
{oem_text}
""".strip()


def _template_summary(
    external_data: Dict[str, List[Dict[str, Any]]],
    config: Dict[str, Any],
) -> str:
    """Fallback summary when QGenie is unavailable."""
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
        for item in tech_items[:max_report_items]:
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


def _summarize_with_qgenie(prompt: str, config: Dict[str, Any]) -> str:
    qgenie_cfg = config.get("qgenie", {})
    endpoint = qgenie_cfg.get("endpoint", "")
    model = qgenie_cfg.get("model", "qgenie-default")
    timeout_seconds = int(qgenie_cfg.get("timeout_seconds", 60))
    api_key_env = qgenie_cfg.get("api_key_env", "QGENIE_API_KEY")
    api_key = os.environ.get(api_key_env)

    if not endpoint:
        raise ValueError("QGenie endpoint is not configured.")
    if not api_key:
        raise ValueError(f"Environment variable {api_key_env} is not set.")

    response = requests.post(
        endpoint,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": model,
            "messages": [
                {
                    "role": "user",
                    "content": prompt,
                }
            ],
        },
        timeout=timeout_seconds,
    )
    response.raise_for_status()

    data = response.json()
    return data["choices"][0]["message"]["content"].strip()


def summarize(
    external_data: Dict[str, List[Dict[str, Any]]],
    config: Dict[str, Any],
    logger=None,
) -> str:
    """Summarize collected external trend data.

    QGenie is used when enabled and available.
    If QGenie fails, a simple template report is returned.
    """
    qgenie_enabled = bool(config.get("qgenie", {}).get("enabled", True))

    if not qgenie_enabled:
        if logger:
            logger.info("QGenie is disabled. Using template summary.")
        return _template_summary(external_data, config)

    prompt = _build_prompt(external_data, config)

    try:
        if logger:
            logger.info("Calling QGenie for Chinese summary")
        return _summarize_with_qgenie(prompt, config)
    except Exception as exc:
        if logger:
            logger.warning("QGenie failed. Falling back to template summary. Error: %s", exc)
        return _template_summary(external_data, config)
