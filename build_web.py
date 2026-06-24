"""
build_web.py — Generate static website from TechPulse Markdown reports.

Run: python build_web.py
Output: docs/ directory ready for GitHub Pages deployment.
"""

import os
import re
import glob
import html
from datetime import datetime
from pathlib import Path

# 用于从要点文本里提取技术参数的正则
_SPEC_PATTERNS = [
    r"\d+/\d+\.\d+\s*英寸",           # 传感器尺寸：1/1.28英寸
    r"f/\d+\.\d+",                     # 光圈：f/1.8
    r"\d+\s*[Mm][Pp]|\d+\s*亿像素",   # 像素：5000万MP / 2亿像素
    r"\d+\s*[Xx][\s光]?学?变焦|\d+[xX]\s*[Oo]ptical\s*[Zz]oom|潜望[^，。、\s]{0,6}",  # 变焦
    r"\d+\s*[Dd][Bb]\s*(?:动态范围|HDR|[Dd]ynamic\s*[Rr]ange)?",  # 动态范围：100dB
    r"LOFIC|ISOCELL|LYTIA|OmniVision",  # 传感器品牌/技术
    r"Neural\s*ISP|AI\s*ISP|ISP\s*算法",  # ISP
    r"\d+\s*fps",                       # 帧率
    r"HDR\s*\d*\.?\d*\+?|HDR\s*视频",  # HDR
    r"PDAF|OIS|光学防抖|相位对焦",      # 对焦/防抖
]


def extract_spec_badges(report: dict, count: int = 5) -> list:
    """从报告的要点文本中提取真实技术参数词，返回去重后最多 count 个。"""
    seen = set()
    results = []
    for section in report.get("sections", []):
        for item in section.get("items", []):
            text = item.get("digest", "")
            for pattern in _SPEC_PATTERNS:
                for m in re.finditer(pattern, text, re.IGNORECASE):
                    badge = m.group(0).strip()
                    # 归一化空白
                    badge = re.sub(r"\s+", " ", badge)
                    key = badge.lower()
                    if key not in seen and len(badge) >= 2:
                        seen.add(key)
                        results.append(badge)
                        if len(results) >= count:
                            return results
    # 不足时用兜底词补全
    fallbacks = ["1/1.28\" Sensor", "100dB HDR", "LOFIC", "Neural ISP", "f/1.8"]
    for fb in fallbacks:
        if len(results) >= count:
            break
        if fb.lower() not in seen:
            results.append(fb)
            seen.add(fb.lower())
    return results[:count]

BASE_DIR = Path(__file__).parent
OUTPUT_DIR = BASE_DIR / "output"
DOCS_DIR = BASE_DIR / "docs"
REPORTS_DIR = DOCS_DIR / "reports"

REPORTS_DIR.mkdir(parents=True, exist_ok=True)

NAV_HTML = """
<div class="topbar"></div>
<nav class="nav">
  <a class="nav-brand" href="../index.html">
    <span class="nav-wordmark">Qualcomm<span>.</span></span>
    <div class="nav-divider"></div>
    <span class="nav-title">TechPulse</span>
  </a>
  <div class="nav-links">
    <a href="../index.html" id="nav-latest">最新报告</a>
    <a href="../archive.html" id="nav-archive">历史归档</a>
    <a href="../about.html" id="nav-about">关于</a>
  </div>
</nav>
""".strip()

NAV_ROOT_HTML = NAV_HTML.replace('href="../', 'href="').replace('href="reports/', 'href="reports/')

FOOTER_HTML = """
<footer class="footer">
  <div class="footer-left">
    <span class="footer-wordmark">Qualcomm<span>.</span></span>
    <span class="footer-dot"></span>
    <span>TechPulse Auto-Push</span>
  </div>
  <div>
    <a href="https://github.com/hahaha338/tech_pulse" target="_blank" rel="noopener">GitHub</a>
    &nbsp;&nbsp;
    由千问 AI 自动生成
  </div>
</footer>
""".strip()

PAGE_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title} — TechPulse</title>
  <link rel="stylesheet" href="{css_path}">
</head>
<body>
{nav}
{body}
{footer}
</body>
</html>"""


def parse_report(md_path: Path):
    """Parse a TechPulse Markdown report into structured data."""
    text = md_path.read_text(encoding="utf-8")
    date_str = re.search(r"techpulse_(\d{4}-\d{2}-\d{2})\.md", md_path.name)
    date = date_str.group(1) if date_str else "unknown"

    sections = []
    current_section = None
    current_item = None

    for line in text.splitlines():
        # Section header
        m = re.match(r"^## (\d+)\. (.+)", line)
        if m:
            if current_section:
                if current_item:
                    current_section["items"].append(current_item)
                    current_item = None
                sections.append(current_section)
            current_section = {"title": m.group(2).strip(), "items": []}
            continue

        if current_section is None:
            continue

        # News item title
        if line.startswith("- ") and not line.startswith("  "):
            if current_item:
                current_section["items"].append(current_item)
            current_item = {"title": line[2:].strip(), "meta": "", "digest": "", "link": ""}
            continue

        if current_item is None:
            continue

        # Source/time
        m = re.match(r"^\s+来源/时间：(.+)", line)
        if m:
            current_item["meta"] = m.group(1).strip()
            continue

        # Key points
        m = re.match(r"^\s+要点：(.+)", line)
        if m:
            current_item["digest"] = m.group(1).strip()
            continue

        # Link
        m = re.match(r"^\s+链接：(.+)", line)
        if m:
            current_item["link"] = m.group(1).strip()
            continue

    if current_section:
        if current_item:
            current_section["items"].append(current_item)
        sections.append(current_section)

    total_items = sum(len(s["items"]) for s in sections)
    return {"date": date, "sections": sections, "total_items": total_items}


def render_news_card(item: dict) -> str:
    title = html.escape(item["title"])
    meta_raw = item["meta"]
    digest = html.escape(item["digest"])
    link = item["link"]

    parts = [p.strip() for p in meta_raw.split("|")]
    source = html.escape(parts[0]) if len(parts) > 0 else ""
    publisher = html.escape(parts[1]) if len(parts) > 1 else ""
    time_str = html.escape(parts[-1]) if len(parts) > 2 else ""

    source_chip = f'<span class="news-meta-source">{source}</span>' if source else ""
    pub_chip = f'<span class="news-meta-pub">{publisher}</span>' if publisher and publisher != source else ""
    time_chip = f'<span class="news-meta-time">{time_str}</span>' if time_str else ""

    digest_html = ""
    if digest:
        digest_html = f"""
    <div class="news-digest">
      <div class="news-digest-label">技术要点</div>
      <div class="news-digest-text">{digest}</div>
    </div>"""

    link_html = ""
    if link:
        link_escaped = html.escape(link)
        link_html = f"""
    <div class="news-footer">
      <div class="news-link"><a href="{link_escaped}" target="_blank" rel="noopener">阅读原文</a></div>
    </div>"""

    return f"""<div class="news-card">
  <div class="news-title">{title}</div>
  <div class="news-meta">
    {source_chip}{pub_chip}{time_chip}
  </div>{digest_html}{link_html}
</div>"""


def render_section(section: dict, icon: str, num: str) -> str:
    items_html = "\n".join(render_news_card(item) for item in section["items"])
    badge = f'<span class="section-badge">{len(section["items"])} 条</span>'
    return f"""<div class="section-header">
  <span class="section-num">{num}</span>
  <h2>{html.escape(section["title"])}</h2>
  {badge}
</div>
<div class="news-grid">
{items_html}
</div>"""


def render_report_body(report: dict, is_root: bool = False) -> str:
    section_nums = ["01", "02", "03"]
    section_icons = ["🔬", "📱"]
    sections_html = []
    for i, section in enumerate(report["sections"]):
        icon = section_icons[i] if i < len(section_icons) else "📌"
        num = section_nums[i] if i < len(section_nums) else f"0{i+1}"
        sections_html.append(render_section(section, icon, num))

    # 动态提取技术参数标签
    badge_classes = ["sb1", "sb2", "sb3", "sb4", "sb5"]
    badges = extract_spec_badges(report, count=5)
    badges_html = "\n        ".join(
        f'<div class="spec-badge {badge_classes[i]}">{html.escape(b)}</div>'
        for i, b in enumerate(badges)
    )

    date_display = report["date"]
    try:
        dt = datetime.strptime(report["date"], "%Y-%m-%d")
        date_display = dt.strftime("%Y 年 %m 月 %d 日")
    except Exception:
        pass

    back = ""
    if not is_root:
        back = '<a class="hero-back" href="../archive.html">← 返回归档</a>'

    hero = f"""<div class="hero">
  <div class="hero-inner">
    <div class="hero-left">
      {back}
      <div class="hero-eyebrow">手机影像技术情报</div>
      <h1>Camera 技术<em>追踪</em></h1>
      <p class="hero-sub">聚合全球影像技术资讯，由千问 AI 从工程师视角提炼传感器规格、ISP 算法、计算摄影等专业技术要点</p>
      <div class="hero-stats">
        <div class="hero-stat">
          <div class="hero-stat-num">{date_display}</div>
          <div class="hero-stat-label">本期日期</div>
        </div>
        <div class="hero-stat">
          <div class="hero-stat-num">{report["total_items"]}</div>
          <div class="hero-stat-label">条资讯</div>
        </div>
        <div class="hero-stat">
          <div class="hero-stat-num">{len(report["sections"])}</div>
          <div class="hero-stat-label">个板块</div>
        </div>
      </div>
    </div>
    <div class="hero-visual">
      <div class="camera-viz">
        <div class="camera-ring r1"></div>
        <div class="camera-ring r2"></div>
        <div class="camera-sensor">
          <div class="camera-scan"></div>
          <div class="camera-aperture"></div>
        </div>
        {badges_html}      </div>
    </div>
  </div>
</div>"""

    return f"{hero}\n<div class=\"container\">\n{''.join(sections_html)}\n</div>"


def build_report_page(report: dict, md_path: Path):
    body = render_report_body(report)
    page = PAGE_TEMPLATE.format(
        title=f"报告 {report['date']}",
        css_path="../assets/style.css",
        nav=NAV_HTML,
        body=body,
        footer=FOOTER_HTML,
    )
    out_path = REPORTS_DIR / f"{report['date']}.html"
    out_path.write_text(page, encoding="utf-8")
    print(f"  + reports/{report['date']}.html")


def build_index(latest_report: dict):
    body = render_report_body(latest_report, is_root=True)
    # Fix relative links for root-level page
    body = body.replace('href="../archive.html"', 'href="archive.html"')
    nav = NAV_ROOT_HTML
    # Mark active
    nav = nav.replace('id="nav-latest"', 'id="nav-latest" class="active"')
    page = PAGE_TEMPLATE.format(
        title="最新报告",
        css_path="assets/style.css",
        nav=nav,
        body=body,
        footer=FOOTER_HTML.replace('href="reports/', 'href="reports/'),
    )
    (DOCS_DIR / "index.html").write_text(page, encoding="utf-8")
    print("  + index.html")


def build_archive(reports: list):
    from collections import defaultdict
    by_month = defaultdict(list)
    for r in reports:
        try:
            dt = datetime.strptime(r["date"], "%Y-%m-%d")
            key = dt.strftime("%Y 年 %m 月")
            day = dt.strftime("%d")
        except Exception:
            key = "其他"
            day = r["date"]
        by_month[key].append((day, r))

    groups_html = []
    for month in sorted(by_month.keys(), reverse=True):
        items = sorted(by_month[month], key=lambda x: x[1]["date"], reverse=True)
        items_html = ""
        for day, r in items:
            items_html += f"""
<a class="archive-item" href="reports/{r['date']}.html">
  <div class="archive-date-box">
    <div class="archive-date-day">{day}</div>
    <div class="archive-date-mon">{month[:4]}</div>
  </div>
  <div class="archive-info">
    <div class="archive-info-title">TechPulse 技术追踪 · {r['date']}</div>
    <div class="archive-info-sub">📊 共 {r['total_items']} 条资讯</div>
  </div>
  <div class="archive-arrow">›</div>
</a>"""
        groups_html.append(f"""
<div class="archive-group">
  <div class="archive-group-title">{month}</div>
  {items_html}
</div>""")

    nav = NAV_ROOT_HTML.replace('id="nav-archive"', 'id="nav-archive" class="active"')
    body = f"""<div class="hero">
  <div class="hero-inner">
    <div class="hero-left">
      <div class="hero-eyebrow">全部期次</div>
      <h1>历史<em>归档</em></h1>
      <p class="hero-sub">共 {len(reports)} 期报告，每周一自动更新</p>
    </div>
  </div>
</div>
<div class="container">
{"".join(groups_html)}
</div>"""

    page = PAGE_TEMPLATE.format(
        title="历史归档",
        css_path="assets/style.css",
        nav=nav,
        body=body,
        footer=FOOTER_HTML,
    )
    (DOCS_DIR / "archive.html").write_text(page, encoding="utf-8")
    print("  + archive.html")


def main():
    print("Building TechPulse website...")
    md_files = sorted(glob.glob(str(OUTPUT_DIR / "techpulse_*.md")))
    if not md_files:
        print("  ✗ No reports found in output/")
        return

    reports = []
    for md_path in md_files:
        report = parse_report(Path(md_path))
        build_report_page(report, Path(md_path))
        reports.append(report)

    reports_sorted = sorted(reports, key=lambda r: r["date"], reverse=True)
    build_index(reports_sorted[0])
    build_archive(reports_sorted)

    print(f"\nDone -- {len(reports)} reports built -> docs/")
    print(f"   Open: docs/index.html")


if __name__ == "__main__":
    main()
