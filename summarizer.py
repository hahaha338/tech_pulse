import re
import urllib3
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from html.parser import HTMLParser
from typing import Any, Dict, List

from qgeniechat_core import (
    QGenieChatClient, Message, AgentOptions, ToolOptions,
    WebSearchOptions, InternalQualcommSearch, PythonSandboxOptions,
    MermaidToolOptions, ImageGenerationOptions,
)

_TOOLS_OFF = ToolOptions(
    internal_qualcomm_search=InternalQualcommSearch(enabled=False),
    python_sandbox=PythonSandboxOptions(enabled=False),
    mermaid_tool=MermaidToolOptions(enabled=False),
    image_generation=ImageGenerationOptions(enabled=False),
    web_search_options=WebSearchOptions(enabled=False),
)

_qgenie_client: QGenieChatClient | None = None


def _get_qgenie_client() -> QGenieChatClient:
    global _qgenie_client
    if _qgenie_client is None:
        _qgenie_client = QGenieChatClient()
    return _qgenie_client

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


def _llm_batch_digest(
    items: List[Dict[str, Any]], llm_cfg: Dict[str, Any]
) -> Dict[int, str]:
    """Fetch article texts in parallel, then call LLM once to summarize all items.

    Returns a dict mapping item index -> digest string.
    """
    if not items:
        return {}

    max_chars = int(llm_cfg.get("max_summary_chars", 300))
    model = llm_cfg.get("model", "azure::gpt-5.5")

    # 并行抓取所有文章原文
    contents: Dict[int, str] = {}
    with ThreadPoolExecutor(max_workers=10) as executor:
        future_to_idx = {
            executor.submit(
                _fetch_article_text, item.get("link", "")
            ): i
            for i, item in enumerate(items)
        }
        for future in as_completed(future_to_idx):
            i = future_to_idx[future]
            text = future.result()
            contents[i] = text or items[i].get("summary", "").strip()

    # 构造批量 prompt
    articles = []
    for i, item in enumerate(items):
        title = item.get("title", "")
        content = contents.get(i, "")
        if content:
            articles.append(f"[{i+1}] 标题：{title}\n正文：{content[:1500]}")
        else:
            articles.append(f"[{i+1}] 标题：{title}")

    prompt = (
        f"你是手机相机工程师。以下是 {len(items)} 篇手机影像技术文章。\n\n"
        + "\n\n".join(articles)
        + f"\n\n请对每篇文章用三到五句话深度提炼相机核心技术要点，"
        f"涵盖传感器规格（尺寸、像素、光圈）、变焦能力、动态范围、ISP/算法创新及实际影像提升效果，"
        f"只写文章中有据可查的内容，不要复述标题。用中文输出，每篇不超过{max_chars}字。\n\n"
        f"输出格式（严格按此格式，每篇占一行，不要有其他内容）：\n"
        f"[1] 要点内容\n[2] 要点内容\n..."
    )

    try:
        client = _get_qgenie_client()
        response = client.chat(
            messages=[Message(role="user", content=prompt)],
            model_name=model,
            agent_options=AgentOptions(tool_options=_TOOLS_OFF),
            stream=False,
        )
        answer = response.first_content.strip()

        digests: Dict[int, str] = {}
        for line in answer.splitlines():
            line = line.strip()
            m = re.match(r"^\[(\d+)\]\s*(.+)$", line)
            if m:
                idx = int(m.group(1)) - 1
                digests[idx] = m.group(2).strip()
        return digests
    except Exception:
        return {}


def _render_items(
    items: List[Dict[str, Any]],
    count: int,
    llm_cfg: Dict[str, Any],
    lines: List[str],
) -> None:
    batch = items[:count]
    digests = _llm_batch_digest(batch, llm_cfg)

    for i, item in enumerate(batch):
        title = item.get("title", "")
        source = item.get("source", "")
        publisher = item.get("publisher", "")
        published = item.get("published", "")
        link = item.get("link", "")

        lines.append(f"- {title}")
        source_parts = [p for p in [source, publisher, published] if p]
        if source_parts:
            lines.append(f"  来源/时间：{' | '.join(source_parts)}")
        digest = digests.get(i, "")
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
    max_archive_items = int(external_cfg.get("max_report_items_archive", 5))
    llm_cfg = config.get("llm", {})

    lines = ["## 1. 手机厂商影像发展趋势", ""]
    oem_items = external_data.get("oem", [])
    if not oem_items:
        lines.append("- 本周期无明显手机厂商影像趋势更新。")
    else:
        _render_items(oem_items, max_report_items, llm_cfg, lines)

    archive_items = external_data.get("oem_archive", [])
    if archive_items:
        seen_product: set = set()
        deduped_archive = []
        for item in archive_items:
            key = item.get("product") or item.get("title", "").strip()[:30]
            key = key.lower()
            if key not in seen_product:
                seen_product.add(key)
                deduped_archive.append(item)
        lines.extend(["", "## 2. 往期产品参考", ""])
        _render_items(deduped_archive, max_archive_items, llm_cfg, lines)

    lines.extend(["", f"## {'3' if archive_items else '2'}. 外部影像技术趋势", ""])
    tech_items = external_data.get("tech", [])
    if not tech_items:
        lines.append("- 本周期无明显外部影像技术更新。")
    else:
        _render_items(tech_items, 3, llm_cfg, lines)

    return "\n".join(lines).strip()


def summarize(
    external_data: Dict[str, List[Dict[str, Any]]],
    config: Dict[str, Any],
    logger=None,
) -> str:
    if logger:
        logger.info("Generating template summary")
    return _template_summary(external_data, config)
