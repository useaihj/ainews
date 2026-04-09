"""
generate_html.py - Generate a premium HTML dashboard from GeekNews article data.

Reads CSS from data/mockups/premium.html and produces data/index.html
with dynamic content derived from data/hada_news.json.
"""

import json
import re
import html
from datetime import datetime, timedelta
from pathlib import Path
from collections import defaultdict


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def _heat_level(points: int) -> int:
    """Return heat level 0-3 based on points."""
    if points >= 50:
        return 3
    if points >= 20:
        return 2
    if points >= 5:
        return 1
    return 0


def _topic_url(article: dict) -> str:
    """Return GeekNews topic page URL for the article."""
    aid = article.get("id", "")
    if aid:
        return f"https://news.hada.io/topic?id={aid}"
    return article.get("url", "#")


def _truncate(text: str, max_len: int) -> str:
    """Truncate text to max_len characters, adding ellipsis if needed."""
    if len(text) <= max_len:
        return text
    return text[: max_len - 1] + "\u2026"


def _parse_dt(article: dict) -> datetime:
    """Parse the published datetime string from an article."""
    raw = article.get("published", "")
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            continue
    return datetime.min


def _fmt_date(dt: datetime) -> str:
    """Format a datetime as MM.DD."""
    return f"{dt.month:02d}.{dt.day:02d}"


def _relative_day(dt: datetime, now: datetime) -> str:
    """Return 'today', '1d', '2d', etc."""
    days = (now.date() - dt.date()).days
    if days <= 0:
        return "today"
    return f"{days}d"


def _extract_css(premium_path: Path) -> str:
    """Extract the CSS between <style> and </style> in the premium HTML."""
    text = premium_path.read_text(encoding="utf-8")
    m = re.search(r"<style>(.*?)</style>", text, re.DOTALL)
    if m:
        return m.group(1)
    raise RuntimeError("Could not find <style>...</style> in premium.html")


# ---------------------------------------------------------------------------
# Section builders
# ---------------------------------------------------------------------------

def _build_header(articles: list[dict], now: datetime) -> str:
    count = len(articles)
    time_str = now.strftime("%H:%M")
    return f"""
<div class="ambient-glow glow-1"></div>
<div class="ambient-glow glow-2"></div>

<!-- ===== HEADER ===== -->
<header>
  <div class="logo">
    <div class="logo-icon">GN</div>
    <div class="logo-text">GeekNews <span>Reader</span></div>
  </div>
  <div class="nav-tabs">
    <a href="#feed" data-tab="feed" class="active">Feed</a>
    <a href="#latest" data-tab="latest">Latest</a>
    <a href="#top" data-tab="top">Top</a>
    <a href="#weekly" data-tab="weekly">Weekly</a>
  </div>
  <div class="header-right">
    <div class="sync-indicator">
      <span class="sync-dot"></span>
      <span class="mono" style="font-size:11px">{time_str}</span>
    </div>
    <div class="article-count"><span class="mono">{count}</span></div>
  </div>
</header>
"""


def _build_heatmap(articles: list[dict], now: datetime) -> str:
    """Activity heatmap for the last 7 days (+ today = 8 bars like the mockup)."""
    today = now.date()
    # Count articles per date
    date_counts: dict = defaultdict(int)
    for a in articles:
        d = a.get("published_date", "")
        if d:
            try:
                date_counts[d] += 1
            except Exception:
                pass

    # Build list of last 7 days + today (8 days total, matching the mockup)
    days = []
    for i in range(7, -1, -1):
        d = today - timedelta(days=i)
        days.append(d)

    max_count = max((date_counts.get(d.isoformat(), 0) for d in days), default=1) or 1

    bars = []
    for d in days:
        cnt = date_counts.get(d.isoformat(), 0)
        bar_height = max(4, int(cnt / max_count * 80)) if cnt > 0 else 4
        is_today = d == today

        # Color: today -> green, high count -> magenta, low -> cyan — all opaque enough to see
        if is_today:
            bg = "linear-gradient(180deg,rgba(16,185,129,0.7),rgba(16,185,129,0.2))"
            label_style = ' style="color:var(--accent-green)"'
        elif cnt / max_count > 0.6:
            bg = "linear-gradient(180deg,rgba(217,70,239,0.7),rgba(0,212,255,0.25))"
            label_style = ""
        else:
            bg = "linear-gradient(180deg,rgba(0,212,255,0.55),rgba(0,212,255,0.15))"
            label_style = ""

        bars.append(
            f'        <div class="heatmap-day">\n'
            f'          <div class="heatmap-bar" style="height:{bar_height}px;background:{bg};"></div>\n'
            f'          <div class="heatmap-label"{label_style}>{d.day:02d}</div>\n'
            f'          <div class="heatmap-count">{cnt}</div>\n'
            f'        </div>'
        )

    return (
        '    <div class="section-card">\n'
        '      <div class="panel-title">Activity <span class="badge">7 days</span></div>\n'
        '      <div class="heatmap">\n'
        + "\n".join(bars) + "\n"
        '      </div>\n'
        '    </div>'
    )


def _build_timeline(articles: list[dict], now: datetime) -> str:
    """Group articles by date, newest first. Max 5 days, 5 articles/day."""
    today = now.date()

    by_date: dict[str, list[dict]] = defaultdict(list)
    for a in articles:
        d = a.get("published_date", "")
        if d:
            by_date[d].append(a)

    # Sort dates descending
    sorted_dates = sorted(by_date.keys(), reverse=True)[:5]

    groups = []
    for date_str in sorted_dates:
        try:
            d = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            continue

        weekday = WEEKDAYS[d.weekday()]
        date_label = f"{d.month:02d}.{d.day:02d} {weekday}"
        today_badge = ' <span class="today">TODAY</span>' if d == today else ""
        header = f'        <div class="day-header">{date_label}{today_badge}<span style="flex:1"></span></div>'

        items_sorted = sorted(by_date[date_str], key=lambda x: x.get("points", 0), reverse=True)[:5]
        item_lines = []
        for a in items_sorted:
            pts = a.get("points", 0)
            heat = _heat_level(pts)
            title = html.escape(_truncate(a.get("title", ""), 30))
            url = html.escape(_topic_url(a))
            item_lines.append(
                f'        <div class="tl-item">'
                f'<div class="tl-pts" data-heat="{heat}">{pts}</div>'
                f'<a href="{url}" target="_blank" class="tl-text" style="color:inherit;text-decoration:none">{title}</a>'
                f'</div>'
            )

        groups.append(
            '      <div class="day-group">\n'
            + header + "\n"
            + "\n".join(item_lines) + "\n"
            + '      </div>'
        )

    return (
        '    <div class="section-card">\n'
        '      <div class="panel-title">Timeline</div>\n\n'
        + "\n\n".join(groups) + "\n"
        + '    </div>'
    )


def _build_hero(article: dict, now: datetime) -> str:
    """Build the hero card for the #1 article."""
    pts = article.get("points", 0)
    title = html.escape(article.get("title", ""))
    summary_raw = article.get("summary", "")
    summary = html.escape(_truncate(summary_raw, 100))
    source = html.escape(article.get("source", ""))
    author = html.escape(article.get("author", ""))
    comments = article.get("comments", 0)
    dt = _parse_dt(article)
    date_str = _fmt_date(dt)

    return f"""    <div class="hero-card">
      <div class="hero-top">
        <div class="hero-rank mono">WEEK #1</div>
        <div class="hero-pts-container">
          <div class="hero-pts">{pts}</div>
          <div class="hero-pts-label mono">points</div>
        </div>
      </div>
      <h2 class="hero-title"><a href="{html.escape(_topic_url(article))}" target="_blank" style="color:inherit;text-decoration:none">{title}</a></h2>
      <p class="hero-desc">{summary}</p>
      <div class="hero-meta">
        <a href="{html.escape(_topic_url(article))}">{source}</a>
        <span class="sep">\u00b7</span>
        <span>{date_str}</span>
        <span class="sep">\u00b7</span>
        <span>\ub313\uae00 {comments}\uac1c</span>
        <span class="sep">\u00b7</span>
        <span>by {author}</span>
      </div>
      <div class="heat-bar" style="margin-top:20px">
        <div class="heat-bar-fill hot" style="width:100%"></div>
      </div>
    </div>"""


def _build_top_row(articles_2_4: list[dict], max_points: int) -> str:
    """Build the top 2-4 mini cards."""
    cards = []
    for idx, a in enumerate(articles_2_4):
        rank = idx + 2  # 2, 3, 4
        pts = a.get("points", 0)
        title = html.escape(a.get("title", ""))
        source = html.escape(a.get("source", ""))
        dt = _parse_dt(a)
        date_str = _fmt_date(dt)
        comments = a.get("comments", 0)

        pct = int(pts / max_points * 100) if max_points else 0
        if pct > 60:
            heat_class = "hot"
        elif pct > 30:
            heat_class = "warm"
        else:
            heat_class = "mild"

        data_r = f' data-r="{rank}"' if rank <= 3 else ""
        cards.append(
            f'      <div class="top-mini">\n'
            f'        <div class="top-mini-header">\n'
            f'          <span class="top-mini-rank mono"{data_r}>#{rank:02d}</span>\n'
            f'          <span class="top-mini-pts mono">{pts}</span>\n'
            f'        </div>\n'
            f'        <h4><a href="{html.escape(_topic_url(a))}" target="_blank" style="color:inherit;text-decoration:none">{title}</a></h4>\n'
            f'        <div class="tm-meta">{source} \u00b7 {date_str} \u00b7 \ub313\uae00 {comments}</div>\n'
            f'        <div class="heat-bar"><div class="heat-bar-fill {heat_class}" style="width:{pct}%"></div></div>\n'
            f'      </div>'
        )
    return '    <div class="top-row">\n' + "\n".join(cards) + "\n    </div>"


def _build_feed(articles: list[dict], exclude_ids: set, now: datetime) -> str:
    """Build the latest feed section. Max 15 items, skip already-shown articles."""
    today = now.date()

    # Sort by published datetime, newest first
    feed = [a for a in articles if a.get("id") not in exclude_ids]
    feed.sort(key=lambda x: _parse_dt(x), reverse=True)
    feed = feed[:15]

    lines = [
        '    <div class="section-divider">',
        '      <span class="section-label">Latest</span>',
        '      <span class="section-line"></span>',
        '    </div>',
        '',
    ]

    for a in feed:
        pts = a.get("points", 0)
        heat = _heat_level(pts)
        title = html.escape(a.get("title", ""))
        summary_raw = a.get("summary", "")
        source = html.escape(a.get("source", ""))
        author = html.escape(a.get("author", ""))
        comments = a.get("comments", 0)
        dt = _parse_dt(a)
        is_today = dt.date() == today
        rel = _relative_day(dt, now)

        # Summary line (optional)
        summary_html = ""
        if summary_raw:
            summary_html = f'\n        <div class="feed-desc">{html.escape(_truncate(summary_raw, 80))}</div>'

        # Author span
        author_html = f"<span>by {author}</span>" if author else ""

        # NEW badge
        new_badge = '<span class="new-badge">NEW</span>\n        ' if is_today else ""

        # Heat dot attribute
        heat_dot_attr = f' data-heat="{heat}"' if heat > 0 else ""

        lines.append(
            f'    <div class="feed-item">\n'
            f'      <div class="feed-pts-box">\n'
            f'        <div class="feed-pts-num" data-heat="{heat}">{pts}</div>\n'
            f'        <div class="feed-heat-dot"{heat_dot_attr}></div>\n'
            f'      </div>\n'
            f'      <div class="feed-body">\n'
            f'        <div class="feed-title"><a href="{html.escape(_topic_url(a))}" target="_blank" style="color:inherit;text-decoration:none">{title}</a></div>{summary_html}\n'
            f'        <div class="feed-meta"><span class="source">{source}</span>{author_html}</div>\n'
            f'      </div>\n'
            f'      <div class="feed-right">\n'
            f'        {new_badge}<span class="feed-time mono">{rel}</span>\n'
            f'        <span class="feed-comments mono">c:{comments}</span>\n'
            f'      </div>\n'
            f'    </div>'
        )

    return "\n\n".join(lines)


def _build_points_ranking(articles: list[dict]) -> str:
    """Top 5 articles by points for the right panel."""
    top5 = sorted(articles, key=lambda x: x.get("points", 0), reverse=True)[:5]
    max_pts = top5[0].get("points", 1) if top5 else 1

    rows = []
    for i, a in enumerate(top5):
        rank = i + 1
        pts = a.get("points", 0)
        title = html.escape(_truncate(a.get("title", ""), 25))
        dt = _parse_dt(a)
        date_str = _fmt_date(dt)
        comments = a.get("comments", 0)
        bar_w = int(pts / max_pts * 100) if max_pts else 0

        data_rank = f' data-rank="{rank}"' if rank <= 3 else ""

        rows.append(
            f'        <div class="rank-row">\n'
            f'          <div class="rank-pos mono"{data_rank}>{rank}</div>\n'
            f'          <div class="rank-info">\n'
            f'            <div class="rank-title"><a href="{html.escape(_topic_url(a))}" target="_blank" style="color:inherit;text-decoration:none">{title}</a></div>\n'
            f'            <div class="rank-meta mono">{date_str} \u00b7 c:{comments}</div>\n'
            f'          </div>\n'
            f'          <div class="rank-score">\n'
            f'            <div class="rank-score-num mono">{pts}</div>\n'
            f'            <div class="rank-bar"><div class="rank-bar-fill" style="width:{bar_w}%"></div></div>\n'
            f'          </div>\n'
            f'        </div>'
        )

    return (
        '    <div class="section-card">\n'
        '      <div class="panel-title">Points Ranking</div>\n'
        '      <div class="rank-list" style="margin-top:var(--sp-2)">\n'
        + "\n".join(rows) + "\n"
        + '      </div>\n'
        '      <a href="#top" class="more-link" onclick="document.querySelector(\'[data-tab=top]\').click();return false;">Top 탭에서 더 보기 →</a>\n'
        '    </div>'
    )


def _build_most_discussed(articles: list[dict]) -> str:
    """Top 5 articles by comments for the right panel."""
    top5 = sorted(articles, key=lambda x: x.get("comments", 0), reverse=True)[:5]

    rows = []
    for i, a in enumerate(top5):
        rank = i + 1
        pts = a.get("points", 0)
        title = html.escape(_truncate(a.get("title", ""), 25))
        dt = _parse_dt(a)
        date_str = _fmt_date(dt)
        comments = a.get("comments", 0)

        data_rank = f' data-rank="{rank}"' if rank <= 3 else ""

        rows.append(
            f'        <div class="rank-row">\n'
            f'          <div class="rank-pos mono"{data_rank}>{rank}</div>\n'
            f'          <div class="rank-info">\n'
            f'            <div class="rank-title"><a href="{html.escape(_topic_url(a))}" target="_blank" style="color:inherit;text-decoration:none">{title}</a></div>\n'
            f'            <div class="rank-meta mono">{date_str} \u00b7 {pts}pts</div>\n'
            f'          </div>\n'
            f'          <div class="rank-score">\n'
            f'            <div class="disc-count mono">{comments}</div>\n'
            f'          </div>\n'
            f'        </div>'
        )

    return (
        '    <div class="section-card">\n'
        '      <div class="panel-title">Most Discussed</div>\n'
        '      <div class="rank-list" style="margin-top:var(--sp-2)">\n'
        + "\n".join(rows) + "\n"
        + '      </div>\n'
        '      <a href="#top" class="more-link" onclick="document.querySelector(\'[data-tab=top]\').click();return false;">Top 탭에서 더 보기 →</a>\n'
        '    </div>'
    )


# ---------------------------------------------------------------------------
# Tab view builders
# ---------------------------------------------------------------------------

def _build_latest_view(articles: list[dict], now: datetime) -> str:
    """Latest tab: pure chronological, all articles newest first."""
    today = now.date()
    sorted_all = sorted(articles, key=lambda x: _parse_dt(x), reverse=True)

    lines = []
    current_date = ""

    for a in sorted_all:
        pts = a.get("points", 0)
        heat = _heat_level(pts)
        title = html.escape(a.get("title", ""))
        url = html.escape(_topic_url(a))
        source = html.escape(a.get("source", ""))
        comments = a.get("comments", 0)
        dt = _parse_dt(a)
        d = a.get("published_date", "")
        is_today = dt.date() == today
        rel = _relative_day(dt, now)

        # Date group header
        if d != current_date:
            current_date = d
            try:
                wd = WEEKDAYS[datetime.strptime(d, "%Y-%m-%d").weekday()]
            except ValueError:
                wd = ""
            day_count = sum(1 for x in sorted_all if x.get("published_date") == d)
            today_badge = ' <span class="today">TODAY</span>' if d == now.strftime("%Y-%m-%d") else ""
            lines.append(
                f'    <div class="latest-date-header">'
                f'{d} ({wd}){today_badge}'
                f'<span class="latest-date-count">{day_count}articles</span>'
                f'</div>'
            )

        new_badge = '<span class="new-badge">NEW</span> ' if is_today else ""
        heat_dot_attr = f' data-heat="{heat}"' if heat > 0 else ""

        lines.append(
            f'    <div class="feed-item">\n'
            f'      <div class="feed-pts-box">\n'
            f'        <div class="feed-pts-num" data-heat="{heat}">{pts}</div>\n'
            f'        <div class="feed-heat-dot"{heat_dot_attr}></div>\n'
            f'      </div>\n'
            f'      <div class="feed-body">\n'
            f'        <div class="feed-title"><a href="{url}" target="_blank" style="color:inherit;text-decoration:none">{title}</a></div>\n'
            f'        <div class="feed-meta"><span class="source">{source}</span></div>\n'
            f'      </div>\n'
            f'      <div class="feed-right">\n'
            f'        {new_badge}<span class="feed-time mono">{rel}</span>\n'
            f'        <span class="feed-comments mono">c:{comments}</span>\n'
            f'      </div>\n'
            f'    </div>'
        )

    return "\n".join(lines)


def _build_top_view(articles: list[dict], now: datetime) -> str:
    """Top tab: ranked by points with time-range sub-filters."""
    today = now.date()
    today_str = today.isoformat()
    week_cutoff = (today - timedelta(days=7)).isoformat()
    month_cutoff = (today - timedelta(days=30)).isoformat()

    def _make_list(filtered: list[dict], max_pts: int) -> str:
        rows = []
        for i, a in enumerate(filtered):
            rank = i + 1
            pts = a.get("points", 0)
            heat = _heat_level(pts)
            title = html.escape(a.get("title", ""))
            url = html.escape(_topic_url(a))
            source = html.escape(a.get("source", ""))
            comments = a.get("comments", 0)
            dt = _parse_dt(a)
            date_str = _fmt_date(dt)
            bar_w = int(pts / max_pts * 100) if max_pts else 0

            data_rank = f' data-rank="{rank}"' if rank <= 3 else ""
            rows.append(
                f'      <div class="top-list-item">\n'
                f'        <div class="top-list-rank mono"{data_rank}>{rank}</div>\n'
                f'        <div class="top-list-body">\n'
                f'          <div class="feed-title"><a href="{url}" target="_blank" style="color:inherit;text-decoration:none">{title}</a></div>\n'
                f'          <div class="feed-meta"><span class="source">{source}</span><span>{date_str}</span><span>c:{comments}</span></div>\n'
                f'        </div>\n'
                f'        <div class="top-list-score">\n'
                f'          <div class="rank-score-num mono">{pts}</div>\n'
                f'          <div class="rank-bar"><div class="rank-bar-fill" style="width:{bar_w}%"></div></div>\n'
                f'        </div>\n'
                f'      </div>'
            )
        return "\n".join(rows)

    # Pre-build all 3 time ranges
    all_sorted = sorted(articles, key=lambda x: x.get("points", 0), reverse=True)

    today_articles = [a for a in all_sorted if a.get("published_date", "") == today_str]
    week_articles = [a for a in all_sorted if a.get("published_date", "") >= week_cutoff]
    month_articles = [a for a in all_sorted if a.get("published_date", "") >= month_cutoff]

    today_max = today_articles[0].get("points", 1) if today_articles else 1
    week_max = week_articles[0].get("points", 1) if week_articles else 1
    month_max = month_articles[0].get("points", 1) if month_articles else 1

    today_html = _make_list(today_articles[:20], today_max)
    week_html = _make_list(week_articles[:30], week_max)
    month_html = _make_list(month_articles[:30], month_max)

    return (
        '    <div class="top-filters">\n'
        '      <button class="top-pill active" data-range="today">Today</button>\n'
        '      <button class="top-pill" data-range="week">This Week</button>\n'
        '      <button class="top-pill" data-range="month">This Month</button>\n'
        '    </div>\n'
        f'    <div class="top-range-content" data-range="today">\n{today_html}\n    </div>\n'
        f'    <div class="top-range-content" data-range="week" style="display:none">\n{week_html}\n    </div>\n'
        f'    <div class="top-range-content" data-range="month" style="display:none">\n{month_html}\n    </div>'
    )


def _build_weekly_view(articles: list[dict], now: datetime) -> str:
    """Weekly tab: articles grouped by date like a newspaper."""
    by_date: dict[str, list[dict]] = defaultdict(list)
    for a in articles:
        d = a.get("published_date", "")
        if d:
            by_date[d].append(a)

    sorted_dates = sorted(by_date.keys(), reverse=True)
    sections = []

    for date_str in sorted_dates:
        try:
            d = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            continue

        weekday = WEEKDAYS[d.weekday()]
        is_today = d == now.date()
        today_tag = ' <span class="today">TODAY</span>' if is_today else ""
        day_articles = sorted(by_date[date_str], key=lambda x: x.get("points", 0), reverse=True)

        items = []
        for a in day_articles:
            pts = a.get("points", 0)
            heat = _heat_level(pts)
            title = html.escape(a.get("title", ""))
            url = html.escape(_topic_url(a))
            source = html.escape(a.get("source", ""))
            comments = a.get("comments", 0)
            heat_dot_attr = f' data-heat="{heat}"' if heat > 0 else ""

            items.append(
                f'      <div class="feed-item">\n'
                f'        <div class="feed-pts-box">\n'
                f'          <div class="feed-pts-num" data-heat="{heat}">{pts}</div>\n'
                f'          <div class="feed-heat-dot"{heat_dot_attr}></div>\n'
                f'        </div>\n'
                f'        <div class="feed-body">\n'
                f'          <div class="feed-title"><a href="{url}" target="_blank" style="color:inherit;text-decoration:none">{title}</a></div>\n'
                f'          <div class="feed-meta"><span class="source">{source}</span><span>c:{comments}</span></div>\n'
                f'        </div>\n'
                f'      </div>'
            )

        sections.append(
            f'    <div class="weekly-day-section">\n'
            f'      <div class="weekly-day-header">\n'
            f'        <span class="weekly-date">{date_str} ({weekday}){today_tag}</span>\n'
            f'        <span class="weekly-count">{len(day_articles)}articles</span>\n'
            f'        <span class="section-line"></span>\n'
            f'      </div>\n'
            + "\n".join(items) + "\n"
            f'    </div>'
        )

    return "\n\n".join(sections)


def _build_tab_js() -> str:
    """JavaScript for tab switching and top-view pill filters."""
    return """
<script>
document.addEventListener('DOMContentLoaded', function() {
  const tabs = document.querySelectorAll('.nav-tabs a');
  const views = document.querySelectorAll('.tab-view');

  function switchTab(tabName) {
    tabs.forEach(t => t.classList.toggle('active', t.dataset.tab === tabName));
    views.forEach(v => {
      if (v.dataset.tab === tabName) {
        v.style.display = '';
        v.style.animation = 'fadeIn 200ms ease-out';
      } else {
        v.style.display = 'none';
      }
    });
    history.replaceState(null, '', '#' + tabName);
  }

  tabs.forEach(tab => {
    tab.addEventListener('click', function(e) {
      e.preventDefault();
      switchTab(this.dataset.tab);
    });
  });

  // Top view pill filters
  document.querySelectorAll('.top-pill').forEach(pill => {
    pill.addEventListener('click', function() {
      const range = this.dataset.range;
      document.querySelectorAll('.top-pill').forEach(p => p.classList.remove('active'));
      this.classList.add('active');
      document.querySelectorAll('.top-range-content').forEach(c => {
        c.style.display = c.dataset.range === range ? '' : 'none';
      });
    });
  });

  // Handle URL hash on load
  const hash = location.hash.replace('#', '') || 'feed';
  if (['feed','latest','top','weekly'].includes(hash)) {
    switchTab(hash);
  }
});
</script>"""


# ---------------------------------------------------------------------------
# Main generator
# ---------------------------------------------------------------------------

def generate_premium_html(articles: list[dict]) -> str:
    """
    Generate a complete premium HTML dashboard from article data.

    Parameters
    ----------
    articles : list[dict]
        Each dict has keys: id, title, url, source, summary, points,
        author, comments, published, published_date, collected_at.

    Returns
    -------
    str
        Full HTML document string.
    """
    now = datetime.now()

    # --- Extract CSS from the premium mockup ---
    css_path = Path(__file__).parent / "data" / "mockups" / "premium.html"
    css = _extract_css(css_path)

    # --- Rank articles by points (descending) for hero / top cards ---
    by_points = sorted(articles, key=lambda x: x.get("points", 0), reverse=True)

    hero_article = by_points[0] if by_points else None
    top_2_4 = by_points[1:4]
    max_points = hero_article.get("points", 1) if hero_article else 1

    # IDs already shown in hero + top cards (to exclude from feed)
    shown_ids: set[str] = set()
    if hero_article:
        shown_ids.add(hero_article.get("id", ""))
    for a in top_2_4:
        shown_ids.add(a.get("id", ""))

    # --- Build all sections ---
    header_html = _build_header(articles, now)
    heatmap_html = _build_heatmap(articles, now)
    timeline_html = _build_timeline(articles, now)
    hero_html = _build_hero(hero_article, now) if hero_article else ""
    top_row_html = _build_top_row(top_2_4, max_points)
    feed_html = _build_feed(articles, shown_ids, now)
    ranking_html = _build_points_ranking(articles)
    discussed_html = _build_most_discussed(articles)

    # Tab views
    latest_view_html = _build_latest_view(articles, now)
    top_view_html = _build_top_view(articles, now)
    weekly_view_html = _build_weekly_view(articles, now)
    tab_js = _build_tab_js()

    # --- Assemble body ---
    body = (
        header_html
        + "\n"
        + "<!-- ===== LAYOUT ===== -->\n"
        + '<div class="layout">\n\n'
        + "  <!-- LEFT PANEL -->\n"
        + '  <div class="panel-left">\n'
        + heatmap_html + "\n\n"
        + timeline_html + "\n"
        + "  </div>\n\n"
        + "  <!-- MAIN PANEL -->\n"
        + '  <div class="panel-main">\n\n'
        # Feed tab (default)
        + '  <div class="tab-view" data-tab="feed">\n'
        + hero_html + "\n\n"
        + top_row_html + "\n\n"
        + feed_html + "\n"
        + '  </div>\n\n'
        # Latest tab
        + '  <div class="tab-view" data-tab="latest" style="display:none">\n'
        + latest_view_html + "\n"
        + '  </div>\n\n'
        # Top tab
        + '  <div class="tab-view" data-tab="top" style="display:none">\n'
        + top_view_html + "\n"
        + '  </div>\n\n'
        # Weekly tab
        + '  <div class="tab-view" data-tab="weekly" style="display:none">\n'
        + weekly_view_html + "\n"
        + '  </div>\n\n'
        + "  </div>\n\n"
        + "  <!-- RIGHT PANEL -->\n"
        + '  <div class="panel-right">\n\n'
        + ranking_html + "\n\n"
        + '    <div class="separator"></div>\n\n'
        + discussed_html + "\n\n"
        + "  </div>\n"
        + "</div>\n"
        + tab_js + "\n"
    )

    # --- Full document ---
    doc = (
        "<!DOCTYPE html>\n"
        '<html lang="ko">\n'
        "<head>\n"
        '<meta charset="UTF-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1.0">\n'
        "<title>GeekNews AI Reader</title>\n"
        "<style>\n"
        + css + "\n"
        + "</style>\n"
        + "</head>\n"
        + "<body>\n"
        + body
        + "\n</body>\n"
        + "</html>\n"
    )

    return doc


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    base = Path(__file__).parent
    json_path = base / "data" / "hada_news.json"
    out_path = base / "data" / "index.html"

    with open(json_path, "r", encoding="utf-8") as f:
        articles = json.load(f)

    html_content = generate_premium_html(articles)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html_content)

    print(f"Generated {out_path}  ({len(articles)} articles)")
