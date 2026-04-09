"""
GeekNews(news.hada.io) 수집기
- 최신글을 수집하여 JSON에 누적 저장
- 읽기용 마크다운 자동 생성
- 30일 지난 글 자동 정리
"""

import requests
from bs4 import BeautifulSoup
import json
import os
import re
from datetime import datetime, timedelta
from pathlib import Path

# 설정
BASE_URL = "https://news.hada.io/"
MAX_PAGES = 5
DATA_DIR = Path(__file__).parent / "data"
JSON_FILE = DATA_DIR / "hada_news.json"
MD_TODAY = DATA_DIR / "today.md"
MD_WEEK = DATA_DIR / "week.md"
MD_TOP = DATA_DIR / "top.md"
MD_LATEST = DATA_DIR / "latest.md"
RETENTION_DAYS = 30
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}


def parse_relative_time(time_str: str) -> datetime:
    """'1일전', '3시간전', '42초전' 등을 datetime으로 변환"""
    now = datetime.now()
    time_str = time_str.strip()

    match = re.search(r"(\d+)\s*(초|분|시간|일|주|달|개월|년)", time_str)
    if not match:
        return now

    num = int(match.group(1))
    unit = match.group(2)

    if unit == "초":
        return now - timedelta(seconds=num)
    elif unit == "분":
        return now - timedelta(minutes=num)
    elif unit == "시간":
        return now - timedelta(hours=num)
    elif unit == "일":
        return now - timedelta(days=num)
    elif unit == "주":
        return now - timedelta(weeks=num)
    elif unit in ("달", "개월"):
        return now - timedelta(days=num * 30)
    elif unit == "년":
        return now - timedelta(days=num * 365)
    return now


def fetch_page(page: int) -> list[dict]:
    """한 페이지의 글 목록을 가져옴"""
    url = f"{BASE_URL}?page={page}"
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        r.raise_for_status()
    except requests.RequestException as e:
        print(f"  [오류] 페이지 {page} 가져오기 실패: {e}")
        return []

    soup = BeautifulSoup(r.text, "html.parser")
    rows = soup.select(".topic_row")
    articles = []

    for row in rows:
        try:
            # 제목 & URL
            title_tag = row.select_one(".topictitle a")
            title = title_tag.get_text(strip=True) if title_tag else ""
            href = title_tag.get("href", "") if title_tag else ""
            if href and not href.startswith("http"):
                href = BASE_URL + href

            # 토픽 ID
            vote_span = row.select_one(".vote span[id^='vote']")
            topic_id = ""
            if vote_span:
                topic_id = vote_span.get("id", "").replace("vote", "")

            # 출처 도메인
            url_span = row.select_one(".topicurl")
            source = url_span.get_text(strip=True).strip("()") if url_span else ""

            # 요약
            desc_tag = row.select_one(".topicdesc a")
            summary = desc_tag.get_text(strip=True) if desc_tag else ""

            # 포인트, 작성자, 시간, 댓글
            info = row.select_one(".topicinfo")
            points = 0
            author = ""
            time_str = ""
            comments = 0

            if info:
                points_span = info.select_one("span[id^='tp']")
                if points_span:
                    points = int(points_span.get_text(strip=True) or 0)

                author_tag = info.select_one("a[href^='/user']")
                if author_tag:
                    author = author_tag.get_text(strip=True)

                comment_tag = info.select_one("a.u")
                if comment_tag:
                    cm = re.search(r"(\d+)", comment_tag.get_text())
                    comments = int(cm.group(1)) if cm else 0

                info_text = info.get_text()
                time_match = re.search(
                    r"(\d+\s*(?:초|분|시간|일|주|달|개월|년)\s*전)", info_text
                )
                if time_match:
                    time_str = time_match.group(1)

            published = parse_relative_time(time_str) if time_str else datetime.now()

            articles.append(
                {
                    "id": topic_id,
                    "title": title,
                    "url": href,
                    "source": source,
                    "summary": summary,
                    "points": points,
                    "author": author,
                    "comments": comments,
                    "published": published.strftime("%Y-%m-%d %H:%M"),
                    "published_date": published.strftime("%Y-%m-%d"),
                    "collected_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
                }
            )
        except Exception as e:
            print(f"  [오류] 파싱 실패: {e}")
            continue

    return articles


def load_existing() -> list[dict]:
    """기존 JSON 데이터 로드"""
    if JSON_FILE.exists():
        with open(JSON_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def save_data(articles: list[dict]):
    """JSON 저장"""
    DATA_DIR.mkdir(exist_ok=True)
    with open(JSON_FILE, "w", encoding="utf-8") as f:
        json.dump(articles, f, ensure_ascii=False, indent=2)


def merge_articles(existing: list[dict], new_articles: list[dict]) -> tuple[list[dict], int]:
    """기존 데이터에 새 글 병합 (중복 제거, 포인트/댓글 업데이트)"""
    by_id = {a["id"]: a for a in existing if a.get("id")}
    new_count = 0

    for article in new_articles:
        aid = article["id"]
        if aid in by_id:
            # 기존 글이면 포인트/댓글만 업데이트
            by_id[aid]["points"] = article["points"]
            by_id[aid]["comments"] = article["comments"]
        else:
            by_id[aid] = article
            new_count += 1

    return list(by_id.values()), new_count


def cleanup_old(articles: list[dict]) -> list[dict]:
    """보관 기간 지난 글 삭제"""
    cutoff = (datetime.now() - timedelta(days=RETENTION_DAYS)).strftime("%Y-%m-%d")
    before = len(articles)
    articles = [a for a in articles if a.get("published_date", "") >= cutoff]
    removed = before - len(articles)
    if removed > 0:
        print(f"  {removed}개 오래된 글 정리됨 ({RETENTION_DAYS}일 초과)")
    return articles


def generate_today_md(articles: list[dict]):
    """오늘의 글 마크다운 생성"""
    today = datetime.now().strftime("%Y-%m-%d")
    today_articles = [a for a in articles if a.get("published_date") == today]
    today_articles.sort(key=lambda x: x.get("points", 0), reverse=True)

    lines = [
        f"# GeekNews 오늘의 글 ({today})",
        f"",
        f"> 마지막 수집: {datetime.now().strftime('%Y-%m-%d %H:%M')} | 오늘 {len(today_articles)}개",
        "",
    ]

    if not today_articles:
        lines.append("아직 오늘 수집된 글이 없습니다.")
    else:
        for i, a in enumerate(today_articles, 1):
            lines.append(f"### {i}. {a['title']}")
            lines.append(f"- 링크: {a['url']}")
            if a.get("source"):
                lines.append(f"- 출처: {a['source']}")
            lines.append(f"- {a['points']}점 | 댓글 {a['comments']}개 | by {a['author']}")
            if a.get("summary"):
                lines.append(f"- {a['summary'][:100]}")
            lines.append("")

    DATA_DIR.mkdir(exist_ok=True)
    with open(MD_TODAY, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def generate_week_md(articles: list[dict]):
    """이번 주 글 마크다운 생성 (일별 그룹)"""
    cutoff = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
    week_articles = [a for a in articles if a.get("published_date", "") >= cutoff]

    # 날짜별 그룹
    by_date: dict[str, list[dict]] = {}
    for a in week_articles:
        d = a.get("published_date", "unknown")
        by_date.setdefault(d, []).append(a)

    lines = [
        f"# GeekNews 이번 주 ({cutoff} ~ {datetime.now().strftime('%Y-%m-%d')})",
        f"",
        f"> 마지막 수집: {datetime.now().strftime('%Y-%m-%d %H:%M')} | 총 {len(week_articles)}개",
        "",
    ]

    for date in sorted(by_date.keys(), reverse=True):
        day_articles = sorted(by_date[date], key=lambda x: x.get("points", 0), reverse=True)
        weekday = ["월", "화", "수", "목", "금", "토", "일"]
        try:
            wd = weekday[datetime.strptime(date, "%Y-%m-%d").weekday()]
        except ValueError:
            wd = ""

        lines.append(f"## {date} ({wd}) - {len(day_articles)}개")
        lines.append("")

        for a in day_articles:
            points_bar = "🔥" if a["points"] >= 50 else "⭐" if a["points"] >= 20 else "·"
            lines.append(
                f"- {points_bar} **[{a['title']}]({a['url']})** ({a['points']}점, 댓글 {a['comments']}개)"
            )

        lines.append("")

    DATA_DIR.mkdir(exist_ok=True)
    with open(MD_WEEK, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def generate_top_md(articles: list[dict]):
    """포인트 TOP 랭킹 마크다운 (이번 주 + 이번 달)"""
    now = datetime.now()
    week_cutoff = (now - timedelta(days=7)).strftime("%Y-%m-%d")
    month_cutoff = (now - timedelta(days=30)).strftime("%Y-%m-%d")

    week_articles = [a for a in articles if a.get("published_date", "") >= week_cutoff]
    month_articles = [a for a in articles if a.get("published_date", "") >= month_cutoff]

    week_top = sorted(week_articles, key=lambda x: x.get("points", 0), reverse=True)
    month_top = sorted(month_articles, key=lambda x: x.get("points", 0), reverse=True)

    lines = [
        f"# GeekNews 인기글 (포인트순)",
        "",
        f"> 마지막 수집: {now.strftime('%Y-%m-%d %H:%M')}",
        "",
        f"## 이번 주 TOP ({week_cutoff} ~) - {len(week_top)}개",
        "",
    ]

    for i, a in enumerate(week_top[:30], 1):
        icon = "🔥" if a["points"] >= 50 else "⭐" if a["points"] >= 20 else f"{i:2d}."
        lines.append(
            f"- {icon} **[{a['title']}]({a['url']})** — {a['points']}점, 댓글 {a['comments']}개 ({a['published_date']})"
        )

    lines += [
        "",
        f"## 이번 달 TOP ({month_cutoff} ~) - {len(month_top)}개",
        "",
    ]

    for i, a in enumerate(month_top[:50], 1):
        icon = "🔥" if a["points"] >= 50 else "⭐" if a["points"] >= 20 else f"{i:2d}."
        lines.append(
            f"- {icon} **[{a['title']}]({a['url']})** — {a['points']}점, 댓글 {a['comments']}개 ({a['published_date']})"
        )

    DATA_DIR.mkdir(exist_ok=True)
    with open(MD_TOP, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def generate_latest_md(articles: list[dict]):
    """최신글순 마크다운"""
    now = datetime.now()
    sorted_articles = sorted(articles, key=lambda x: x.get("published", ""), reverse=True)

    lines = [
        f"# GeekNews 최신글",
        "",
        f"> 마지막 수집: {now.strftime('%Y-%m-%d %H:%M')} | 총 {len(sorted_articles)}개",
        "",
    ]

    current_date = ""
    for a in sorted_articles[:100]:
        d = a.get("published_date", "")
        if d != current_date:
            current_date = d
            weekday = ["월", "화", "수", "목", "금", "토", "일"]
            try:
                wd = weekday[datetime.strptime(d, "%Y-%m-%d").weekday()]
            except ValueError:
                wd = ""
            lines.append(f"\n## {d} ({wd})")
            lines.append("")

        points_bar = "🔥" if a["points"] >= 50 else "⭐" if a["points"] >= 20 else "·"
        lines.append(
            f"- {points_bar} **[{a['title']}]({a['url']})** ({a['points']}점, 댓글 {a['comments']}개)"
        )

    DATA_DIR.mkdir(exist_ok=True)
    with open(MD_LATEST, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def main():
    print(f"[GeekNews 수집기] {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  데이터 경로: {DATA_DIR}")

    # 1. 기존 데이터 로드
    existing = load_existing()
    print(f"  기존 저장된 글: {len(existing)}개")

    # 2. 새 글 수집
    all_new = []
    for page in range(1, MAX_PAGES + 1):
        articles = fetch_page(page)
        all_new.extend(articles)
        print(f"  페이지 {page}: {len(articles)}개 수집")

    # 3. 병합
    merged, new_count = merge_articles(existing, all_new)
    print(f"  새로 추가된 글: {new_count}개")

    # 4. 오래된 글 정리
    merged = cleanup_old(merged)

    # 5. 저장
    save_data(merged)
    print(f"  총 저장된 글: {len(merged)}개")

    # 6. 마크다운 생성
    generate_today_md(merged)
    generate_week_md(merged)
    generate_top_md(merged)
    generate_latest_md(merged)
    print(f"  마크다운 생성 완료")

    # 7. HTML 대시보드 생성
    try:
        from generate_html import generate_premium_html
        generate_premium_html(merged)
        print(f"  HTML 대시보드 생성: {DATA_DIR / 'index.html'}")
    except Exception as e:
        print(f"  [경고] HTML 생성 실패: {e}")

    # 8. GitHub Pages 배포 (자동 push)
    try:
        import subprocess
        git_dir = str(DATA_DIR)
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
        subprocess.run(["git", "add", "index.html"], cwd=git_dir, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", f"Update: {now_str} ({len(merged)} articles)"],
            cwd=git_dir, capture_output=True,
        )
        result = subprocess.run(
            ["git", "push"], cwd=git_dir, capture_output=True, text=True,
        )
        if result.returncode == 0:
            print(f"  GitHub Pages 배포 완료")
        else:
            print(f"  [경고] push 실패: {result.stderr[:100]}")
    except Exception as e:
        print(f"  [경고] 배포 실패: {e}")

    print(f"[완료]")


if __name__ == "__main__":
    main()
