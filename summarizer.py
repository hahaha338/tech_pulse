import os
import re
import urllib3
import requests
from html.parser import HTMLParser
from typing import Any, Dict, List

import dashscope
from dashscope import Generation

# 高通企业网络使用自签名 SSL 证书代理，需全局禁用验证
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
_orig_request = requests.Session.request


def _unverified_request(self, method, url, **kwargs):
    kwargs.setdefault("verify", False)
    return _orig_request(self, method, url, **kwargs)


requests.Session.request = _unverified_request


class _TextExtractor(HTMLParser):
    """Extract visible text from HTML, skipping scripts/styles."""

    SKIP_TAGS = {"script", "style", "noscript", "nav", "footer", "header", "aside"}

    def __init__(self):
        super().__init__()
        self._skip = 0
        self.parts: List[str] = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() in self.SKIP_TAGS:
            self._skip += 1

    def handle_endtag(self, tag):
        if tag.lower() in self.SKIP_TAGS and self._skip > 0:
            self._skip -= 1

    def handle_data(self, data):
        if self._skip == 0:
            text = data.strip()
            if text:
                self.parts.append(text)


def _resolve_url(url: str) -> str:
    """Resolve Google News redirect URL to the real article URL."""
    if not url or "news.google.com" not in url:
        return url
    try:
        from googlenewsdecoder import gnewsdecoder
        result = gnewsdecoder(url)
        if result.get("status") and result.get("decoded_url"):
            return result["decoded_url"]
    except Exception:
        pass
    return url


def _fetch_article_text(url: str, max_chars: int = 3000) -> str:
    """Fetch and extract plain text from an article URL."""
    if not url:
        return ""
    real_url = _resolve_url(url)
    try:
        headers = {"User-Agent": "Mozilla/5.0 TechPulse/1.0"}
        resp = requests.get(real_url, headers=headers, timeout=15)
        resp.raise_for_status()
        parser = _TextExtractor()
        parser.feed(resp.text)
        text = " ".join(parser.parts)
        text = re.sub(r"\s+", " ", text).strip()
        return text[:max_chars]
    except Exception:
        return ""


def _llm_digest(title: str, raw_summary: str, link: str, llm_cfg: Dict[str, Any]) -> str:
    api_key = os.environ.get("DASHSCOPE_API_KEY", "")
    if not api_key:
        return ""
    dashscope.api_key = api_key

    max_chars = int(llm_cfg.get("max_summary_chars", 300))
    model = llm_cfg.get("model", "qwen-turbo")

    # 优先读网页原文，没有则退回 RSS summary
    article_text = _fetch_article_text(link)
    content = article_text or raw_summary

    if content:
        prompt = (
            f"你是手机相机工程师。以下是一篇手机影像技术文章的正文内容。\n\n"
            f"正文：{content}\n\n"
            f"请用三到五句话深度提炼相机核心技术要点，涵盖传感器规格（尺寸、像素、光圈）、"
            f"变焦能力、动态范围、ISP/算法创新及实际影像提升效果，"
            f"只写正文中有据可查的内容，不要复述标题。"
            f"用中文输出，不超过{max_chars}字。"
        )
    else:
        prompt = (
            f"你是手机相机工程师。以下是一条手机影像技术新闻的标题。\n\n"
            f"标题：{title}\n\n"
            f"请用两到三句话解释这项技术的原理及对手机影像的意义，"
            f"体现专业深度，不要复述标题。用中文输出，不超过{max_chars}字。"
        )

    try:
        resp = Generation.call(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=400,
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
        digest = _llm_digest(title, raw_summary, link, llm_cfg)
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

    lines.extend(["", "## 2. 手机厂商影像发展趋势", ""])
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
