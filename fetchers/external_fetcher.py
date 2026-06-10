import re
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote_plus, urljoin

import feedparser
import requests
import urllib3
from requests.exceptions import SSLError


GOOGLE_NEWS_RSS = "https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"

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
        return GOOGLE_NEWS_RSS.format(query=quote_plus(query))

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
    allow_undated_html: bool = True,
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
    allow_undated_html = bool(external_cfg.get("allow_undated_html", True))

    results: Dict[str, List[Dict[str, Any]]] = {
        "tech": [],
        "oem": [],
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

            if len(results["tech"]) + len(results["oem"]) >= max_items_total:
                break

        except Exception as exc:
            results["errors"].append(
                {
                    "source": source_name,
                    "error": str(exc),
                }
            )

    results["tech"] = results["tech"][:max_items_total]
    results["oem"] = results["oem"][:max_items_total]

    return results