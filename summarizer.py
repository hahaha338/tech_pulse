import os
import urllib3
import requests
from typing import Any, Dict, List

# 高通企业网络使用自签名 SSL 证书代理，需全局禁用验证
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
_orig_request = requests.Session.request


def _unverified_request(self, method, url, **kwargs):
    kwargs.setdefault("verify", False)
    return _orig_request(self, method, url, **kwargs)


requests.Session.request = _unverified_request


def _llm_digest(title: str, raw_summary: str, llm_cfg: Dict[str, Any]) -> str:
    import dashscope
    from dashscope import Generation

    api_key = os.environ.get("DASHSCOPE_API_KEY", "")
    if not api_key:
        return ""
    dashscope.api_key = api_key

    max_chars = int(llm_cfg.get("max_summary_chars", 150))
    model = llm_cfg.get("model", "qwen-turbo")
    prompt = (
        f"以下是一篇关于影像/相机技术的新闻标题和原文摘要，"
        f"请用中文提炼其中与手机影像、相机传感器、计算摄影相关的核心技术要点，"
        f"不超过{max_chars}字，不要复述标题，直接写要点。\n\n"
        f"标题：{title}\n摘要：{raw_summary or '（无原文摘要）'}"
    )
    try:
        resp = Generation.call(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=200,
            temperature=0.3,
            result_format="message",
        )
        if resp.status_code == 200:
            return resp.output.choices[0].message.content.strip()
        return ""
    except Exception:
        return ""


def _render_items(
    items: List[Dict[str, Any]],
    count: int,
    llm_cfg: Dict[str, Any],
    lines: List[str],
) -> None:
    for item in items[:count]:
        title = item.get("title", "")
        source = item.get("source", "")
        publisher = item.get("publisher", "")
        published = item.get("published", "")
        link = item.get("link", "")
        raw_summary = item.get("summary", "").strip()

        lines.append(f"- {title}")
        source_parts = [p for p in [source, publisher, published] if p]
        if source_parts:
            lines.append(f"  来源/时间：{' | '.join(source_parts)}")
        digest = _llm_digest(title, raw_summary, llm_cfg)
        if digest:
            lines.append(f"  要点：{digest}")
        if link:
            lines.append(f"  链接：{link}")


def _template_summary(
    external_data: Dict[str, List[Dict[str, Any]]],
    config: Dict[str, Any],
) -> str:
    external_cfg = config.get("external", {})
    max_report_items = int(external_cfg.get("max_report_items_per_section", 5))
    llm_cfg = config.get("llm", {})

    lines = ["## 1. 外部影像技术趋势", ""]
    tech_items = external_data.get("tech", [])
    if not tech_items:
        lines.append("- 本周期无明显外部影像技术更新。")
    else:
        _render_items(tech_items, max(3, max_report_items // 2), llm_cfg, lines)

    lines.extend(["", "## 2. 大手机厂商影像发展趋势", ""])
    oem_items = external_data.get("oem", [])
    if not oem_items:
        lines.append("- 本周期无明显手机厂商影像趋势更新。")
    else:
        _render_items(oem_items, max_report_items, llm_cfg, lines)

    return "\n".join(lines).strip()


def summarize(
    external_data: Dict[str, List[Dict[str, Any]]],
    config: Dict[str, Any],
    logger=None,
) -> str:
    if logger:
        logger.info("Generating template summary")
    return _template_summary(external_data, config)
