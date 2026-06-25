import os
import re
from collections import OrderedDict, defaultdict, deque
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote_plus, urljoin

import dashscope
import feedparser
import requests
import urllib3
from dashscope import Generation
from requests.exceptions import SSLError


GOOGLE_NEWS_RSS = "https://news.google.com/rss/search?q={query}&hl={hl}&gl={gl}&ceid={ceid}"

MONTHS_PATTERN = (
    "January|February|March|April|May|June|July|August|September|October|November|December|"
    "Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec"
)
GENERIC_HTML_TITLES = {
    "image sensor",
    "mobile image sensor",
    "automotive image sensor",
    "news",
    "newsroom",
    "press release",
    "press releases",
    "events",
    "products",
    "solutions",
    "support",
    "contact us",
    "learn more",
    "read more",
    "view all",
}

DOMESTIC_RSS_SOURCES = {"IT之家", "少数派", "爱范儿", "雷峰网"}
OFFICIAL_SOURCE_HINTS = ("Newsroom", "News", "Blog", "Semiconductor")


class SimpleLinkParser(HTMLParser):
    """Very small HTML link extractor for official newsroom pages.

    This is intentionally lightweight: no deep crawling, no JS rendering.
    It only extracts visible anchor text and href from the configured page.
    """

    def __init__(self) -> None:
        super().__init__()
        self.links: List[Dict[str, str]] = []
        self._current_href: Optional[str] = None
        self._text_parts: List[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag.lower() != "a":
            return

        href = ""
        for key, value in attrs:
            if key.lower() == "href" and value:
                href = value
                break

        if href:
            self._current_href = href
            self._text_parts = []

    def handle_data(self, data: str) -> None:
        if self._current_href:
            text = data.strip()
            if text:
                self._text_parts.append(text)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() != "a" or not self._current_href:
            return

        title = " ".join(self._text_parts)
        title = " ".join(title.split())

        if title:
            self.links.append(
                {
                    "title": title,
                    "link": self._current_href,
                }
            )

        self._current_href = None
        self._text_parts = []


def _build_source_url(source: Dict[str, Any]) -> str:
    if source.get("url"):
        return source["url"]

    query = source.get("query", "")
    if query:
        return GOOGLE_NEWS_RSS.format(
            query=quote_plus(query),
            hl=source.get("hl", "en-US"),
            gl=source.get("gl", "US"),
            ceid=source.get("ceid", "US:en"),
        )

    return ""


def _contains_any(text: str, keywords: List[str]) -> bool:
    text_lower = text.lower()
    return any(keyword.lower() in text_lower for keyword in keywords)


def _extract_date_from_text(text: str) -> Tuple[str, Optional[datetime]]:
    """Extract simple date patterns from official newsroom link text."""
    patterns = [
        (
            rf"\b({MONTHS_PATTERN})\s+\d{{1,2}},\s+\d{{4}}\b",
            ("%B %d, %Y", "%b %d, %Y"),
        ),
        (
            r"\b\d{4}[-/]\d{1,2}[-/]\d{1,2}\b",
            ("%Y-%m-%d", "%Y/%m/%d"),
        ),
        (
            r"\b\d{4}年\d{1,2}月\d{1,2}日\b",
            ("%Y年%m月%d日",),
        ),
    ]

    for pattern, formats in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if not match:
            continue

        date_text = match.group(0)
        for fmt in formats:
            try:
                return date_text, datetime.strptime(date_text, fmt)
            except ValueError:
                continue

        return date_text, None

    return "", None


def _parse_entry_time(entry: Dict[str, Any]) -> Optional[datetime]:
    published_dt = entry.get("published_dt")
    if isinstance(published_dt, datetime):
        return published_dt

    for key in ("published", "updated", "created"):
        value = entry.get(key, "")
        if not value:
            continue

        try:
            dt = parsedate_to_datetime(value)
            if dt.tzinfo:
                dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
            return dt
        except Exception:
            pass

        date_text, dt = _extract_date_from_text(value)
        if date_text and dt:
            return dt

    return None


def _is_recent(
    entry: Dict[str, Any],
    lookback_days: int,
    allow_undated_html: bool = False,
) -> bool:
    if lookback_days <= 0:
        return True

    entry_time = _parse_entry_time(entry)
    if not entry_time:
        # Many official newsroom pages render dates outside of the anchor text.
        # The lightweight HTML parser only sees the link text, so treat undated
        # official HTML cards as candidates and rely on source order + keyword
        # filtering to keep recent, relevant items.
        if entry.get("source_type") == "html":
            return allow_undated_html

        # RSS/Atom sources usually include dates; if a few entries are missing
        # them, keep the entries to avoid dropping an otherwise valid feed.
        return True

    cutoff = datetime.utcnow() - timedelta(days=lookback_days)
    return entry_time >= cutoff


def _is_matched(
    category: str,
    keyword_text: str,
    config: Dict[str, Any],
    brand_text: Optional[str] = None,
) -> bool:
    external_cfg = config.get("external", {})
    brand_text = brand_text or keyword_text

    if category == "oem":
        exclude_keywords = external_cfg.get("oem_exclude_keywords", [])
        if _contains_any(keyword_text, exclude_keywords):
            return False

        brands = external_cfg.get("oem_brands", [])
        keywords = external_cfg.get("oem_keywords", [])

        # 手机厂商趋势必须同时命中：
        # 1. 手机厂商品牌 / 上游厂商品牌：可以来自 source/publisher/title/summary
        # 2. 影像技术关键词：必须来自 title/summary，避免 Samsung 官网 TV/OLED 等非相机新闻误入
        return _contains_any(brand_text, brands) and _contains_any(keyword_text, keywords)

    exclude_keywords = external_cfg.get("tech_exclude_keywords", [])
    if _contains_any(keyword_text, exclude_keywords):
        return False

    keywords = external_cfg.get("tech_keywords", [])
    return _contains_any(keyword_text, keywords)


def _extract_publisher_from_rss_entry(entry: Dict[str, Any], title: str) -> str:
    source_detail = entry.get("source", {})
    publisher = ""

    if isinstance(source_detail, dict):
        publisher = source_detail.get("title", "") or source_detail.get("href", "")

    # Google News titles often end with " - Publisher".
    # Keep this as a lightweight fallback instead of crawling the article page.
    if not publisher and " - " in title:
        publisher = title.rsplit(" - ", 1)[-1].strip()

    return publisher


def _fetch_rss_entries(source: Dict[str, Any], source_url: str) -> List[Dict[str, Any]]:
    headers = {
        "User-Agent": "Mozilla/5.0 TechPulse/1.0",
    }

    try:
        response = requests.get(source_url, headers=headers, timeout=20)
    except SSLError:
        # Corporate HTTPS interception may break certificate verification.
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        response = requests.get(source_url, headers=headers, timeout=20, verify=False)

    response.raise_for_status()
    feed = feedparser.parse(response.content)
    entries: List[Dict[str, Any]] = []

    for entry in feed.entries:
        title = entry.get("title", "").strip()
        summary = entry.get("summary", "").strip()
        link = entry.get("link", "").strip()
        published = entry.get("published", "").strip()
        publisher = _extract_publisher_from_rss_entry(entry, title)

        entries.append(
            {
                "title": title,
                "summary": summary,
                "link": link,
                "published": published,
                "publisher": publisher,
                "raw_entry": entry,
            }
        )

    return entries


def _fetch_html_entries(source: Dict[str, Any], source_url: str) -> List[Dict[str, Any]]:
    headers = {
        "User-Agent": "Mozilla/5.0 TechPulse/1.0",
    }
    try:
        response = requests.get(source_url, headers=headers, timeout=20)
    except SSLError:
        # Some corporate Windows environments inject a self-signed HTTPS certificate.
        # For public newsroom pages, retry without certificate verification so the job can continue.
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        response = requests.get(source_url, headers=headers, timeout=20, verify=False)

    response.raise_for_status()

    parser = SimpleLinkParser()
    parser.feed(response.text)

    entries: List[Dict[str, Any]] = []
    seen = set()

    for link_info in parser.links:
        title = link_info.get("title", "").strip()
        href = link_info.get("link", "").strip()

        # Filter out navigation links, category pages, and very short labels.
        if len(title) < 12:
            continue
        if title.strip().lower() in GENERIC_HTML_TITLES:
            continue

        published, published_dt = _extract_date_from_text(title)
        raw_entry = {"source_type": "html"}
        if published:
            raw_entry["published"] = published
        if published_dt:
            raw_entry["published_dt"] = published_dt

        absolute_link = urljoin(source_url, href)
        key = (title.lower(), absolute_link)

        if key in seen:
            continue
        seen.add(key)

        entries.append(
            {
                "title": title,
                "summary": "",
                "link": absolute_link,
                "published": published,
                "publisher": source.get("name", ""),
                "raw_entry": raw_entry,
            }
        )

    return entries


def _fetch_source_entries(source: Dict[str, Any], source_url: str) -> List[Dict[str, Any]]:
    source_type = source.get("type", "rss")

    if source_type == "html":
        return _fetch_html_entries(source, source_url)

    return _fetch_rss_entries(source, source_url)


def _contains_chinese(text: str) -> bool:
    return any("\u4e00" <= char <= "\u9fff" for char in text)


def _item_source_group(item: Dict[str, Any]) -> str:
    source = item.get("source", "")
    category = item.get("category", "")
    combined_text = " ".join(
        [
            item.get("source", ""),
            item.get("publisher", ""),
            item.get("title", ""),
        ]
    )

    if source.startswith("Google News"):
        if category == "tech":
            return "tech_google"
        if "China" in source or _contains_chinese(combined_text):
            return "cn_google"
        return "global_google"

    if source == "arXiv CV":
        return "academic"

    if source in DOMESTIC_RSS_SOURCES:
        return "cn_rss"

    if any(hint in source for hint in OFFICIAL_SOURCE_HINTS):
        return "official"

    return "media"


def _build_source_queues(items: List[Dict[str, Any]]) -> OrderedDict:
    source_queues: OrderedDict = OrderedDict()
    for item in items:
        source = item.get("source", "unknown")
        if source not in source_queues:
            source_queues[source] = deque()
        source_queues[source].append(item)
    return source_queues


def _pop_from_source_queues(
    source_queues: OrderedDict,
    source_counts: Dict[str, int],
    source_cap: int,
) -> Optional[Dict[str, Any]]:
    for source in list(source_queues.keys()):
        queue = source_queues[source]
        if not queue:
            source_queues.pop(source, None)
            continue

        if source_cap and source_counts[source] >= source_cap:
            continue

        item = queue.popleft()
        source_counts[source] += 1

        if queue:
            source_queues.move_to_end(source)
        else:
            source_queues.pop(source, None)

        return item

    return None


def _diversify_items(
    items: List[Dict[str, Any]],
    max_items: int,
    category: str,
) -> List[Dict[str, Any]]:
    """Return a balanced list so no source group can starve the others.

    The fetcher still respects source order inside each group, but the final
    list is interleaved across Google News, domestic RSS, official sources, and
    media RSS. This prevents fixes like "move China Google News to the top" from
    hiding all other useful sources in the final report.
    """
    if max_items <= 0 or not items:
        return []

    if category == "oem":
        # 技术深度优先：官方厂商公告 > 英文Google News > 英文媒体RSS > 中文Google News > 中文RSS
        group_order = ["official", "global_google", "media", "cn_google", "cn_rss"]
        source_cap = 2
    else:
        group_order = ["academic", "tech_google", "cn_rss", "media", "official"]
        source_cap = 4

    grouped: OrderedDict = OrderedDict((group, []) for group in group_order)
    for item in items:
        group = _item_source_group(item)
        if group not in grouped:
            grouped[group] = []
        grouped[group].append(item)

    group_queues: OrderedDict = OrderedDict(
        (group, _build_source_queues(group_items))
        for group, group_items in grouped.items()
        if group_items
    )
    selected: List[Dict[str, Any]] = []
    source_counts: Dict[str, int] = defaultdict(int)

    def drain(cap: int) -> None:
        made_progress = True
        while len(selected) < max_items and made_progress:
            made_progress = False
            for group in list(group_queues.keys()):
                source_queues = group_queues.get(group)
                if not source_queues:
                    group_queues.pop(group, None)
                    continue

                item = _pop_from_source_queues(source_queues, source_counts, cap)
                if item:
                    selected.append(item)
                    made_progress = True

                if not source_queues:
                    group_queues.pop(group, None)

                if len(selected) >= max_items:
                    break

    drain(source_cap)

    if len(selected) < max_items:
        drain(0)

    return selected[:max_items]


def _is_fresh_oem_item(item: Dict[str, Any], config: Dict[str, Any]) -> bool:
    """Use Qwen web search to check if the main product in the article
    was first announced within freshness_check_days.

    Fails open (returns True) on missing API key or any error, so a broken
    API never empties the report.
    """
    api_key = os.environ.get("DASHSCOPE_API_KEY", "")
    if not api_key:
        return True

    external_cfg = config.get("external", {})
    freshness_days = int(external_cfg.get("freshness_check_days", 60))
    if freshness_days <= 0:
        return True

    model = external_cfg.get("freshness_model", "qwen-turbo")
    today = datetime.utcnow().strftime("%Y-%m-%d")
    title = item.get("title", "")

    prompt = (
        f"今天是 {today}。\n\n"
        f"文章标题：{title}\n\n"
        f"请联网搜索该标题中提到的主要产品或技术的首次公开发布/发布时间，"
        f"判断它是否在最近 {freshness_days} 天内首次发布或首次公开披露？\n"
        f"只回答'是'或'否'，不要解释。"
    )

    try:
        dashscope.api_key = api_key
        resp = Generation.call(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=10,
            temperature=0,
            result_format="message",
            enable_search=True,
        )
        if resp.status_code == 200:
            answer = resp.output.choices[0].message.content.strip()
            return answer.startswith("是")
        return True
    except Exception:
        return True


def fetch_external_trends(config: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
    """Fetch external tech trends and smartphone OEM imaging trends.

    Supported source types:
    - rss: RSS / Atom feed, including Google News RSS query.
    - html: lightweight one-page official newsroom link extraction.
    """
    external_cfg = config.get("external", {})
    sources = external_cfg.get("rss_sources", [])
    lookback_days = int(external_cfg.get("lookback_days", 30))
    max_items_per_source = int(external_cfg.get("max_items_per_source", 5))
    max_items_total = int(external_cfg.get("max_items_total", 20))
    allow_undated_html = bool(external_cfg.get("allow_undated_html", False))

    results: Dict[str, List[Dict[str, Any]]] = {
        "tech": [],
        "oem": [],
        "oem_archive": [],
        "errors": [],
    }
    seen_links = set()
    seen_titles = set()

    for source in sources:
        source_name = source.get("name", "unknown")
        category = source.get("category", "tech")
        source_url = _build_source_url(source)

        if not source_url:
            results["errors"].append(
                {
                    "source": source_name,
                    "error": "Missing url or query",
                }
            )
            continue

        try:
            entries = _fetch_source_entries(source, source_url)

            matched_count = 0
            for entry in entries:
                title = entry.get("title", "").strip()
                summary = entry.get("summary", "").strip()
                link = entry.get("link", "").strip()
                published = entry.get("published", "").strip()
                publisher = entry.get("publisher", "").strip()
                raw_entry = entry.get("raw_entry", {})

                keyword_text = f"{title} {summary}"
                brand_text = f"{source_name} {publisher} {title} {summary}"

                if not title:
                    continue

                if not _is_recent(
                    raw_entry,
                    lookback_days,
                    allow_undated_html=allow_undated_html,
                ):
                    continue

                if not _is_matched(category, keyword_text, config, brand_text=brand_text):
                    continue

                title_key = title.lower()
                if title_key in seen_titles:
                    continue

                if link and link in seen_links:
                    continue

                seen_titles.add(title_key)
                if link:
                    seen_links.add(link)

                item = {
                    "source": source_name,
                    "publisher": publisher,
                    "category": category,
                    "title": title,
                    "summary": summary[:300],
                    "link": link,
                    "published": published,
                }

                if category == "oem":
                    results["oem"].append(item)
                else:
                    results["tech"].append(item)

                matched_count += 1
                if matched_count >= max_items_per_source:
                    break

        except Exception as exc:
            results["errors"].append(
                {
                    "source": source_name,
                    "error": str(exc),
                }
            )

    freshness_days = int(external_cfg.get("freshness_check_days", 0))
    if freshness_days > 0:
        fresh, archive = [], []
        for item in results["oem"]:
            if _is_fresh_oem_item(item, config):
                fresh.append(item)
            else:
                archive.append(item)
        results["oem"] = fresh
        results["oem_archive"] = archive

    results["tech"] = _diversify_items(results["tech"], max_items_total, "tech")
    results["oem"] = _diversify_items(results["oem"], max_items_total, "oem")
    results["oem_archive"] = _diversify_items(results["oem_archive"], max_items_total, "oem")

    return results