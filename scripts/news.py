"""RSS 뉴스 수집 + 관심종목 매칭.

- 요약(AI)은 하지 않는다. 제목 · 출처 · 시각 · 원문 링크만 모은다.
- 제목에 관심종목 키워드가 들어 있으면 해당 종목에 뉴스를 연결한다.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import re
from typing import Any

import feedparser
import requests

KST = dt.timezone(dt.timedelta(hours=9))
UA = {"User-Agent": "Mozilla/5.0 (compatible; econ-daily/1.0; +https://github.com)"}


def _to_kst(entry: Any) -> dt.datetime | None:
    for key in ("published_parsed", "updated_parsed"):
        tm = entry.get(key) if hasattr(entry, "get") else getattr(entry, key, None)
        if tm:
            try:
                return dt.datetime(*tm[:6], tzinfo=dt.timezone.utc).astimezone(KST)
            except Exception:
                pass
    return None


def _clean(text: str) -> str:
    text = re.sub(r"<[^>]+>", "", text or "")
    return re.sub(r"\s+", " ", text).strip()


def fetch_feed(feed: dict[str, Any], cfg: dict[str, Any]) -> tuple[list[dict], str | None]:
    """한 피드를 읽어 (기사목록, 오류메시지) 를 돌려준다."""
    try:
        resp = requests.get(feed["url"], headers=UA, timeout=cfg.get("timeout_sec", 20))
        resp.raise_for_status()
        parsed = feedparser.parse(resp.content)
    except Exception as exc:
        return [], f"{type(exc).__name__}: {exc}"

    if not parsed.entries:
        return [], "기사 0건 (주소가 RSS가 아니거나 차단됨)"

    now = dt.datetime.now(KST)
    max_age = dt.timedelta(hours=int(cfg.get("max_age_hours", 48)))
    items: list[dict] = []

    for entry in parsed.entries[: int(cfg.get("max_items_per_feed", 8))]:
        title = _clean(getattr(entry, "title", ""))
        link = getattr(entry, "link", "") or ""
        if not title or not link:
            continue
        when = _to_kst(entry)
        if when and now - when > max_age:
            continue
        # 언론사가 RSS로 직접 배포하는 짧은 요약문(있으면). 본문 스크래핑이 아니라
        # 피드 발행자가 공개적으로 제공하는 필드만 사용한다.
        excerpt = _clean(getattr(entry, "summary", "") or getattr(entry, "description", ""))
        if excerpt and excerpt.strip(" .") == title.strip(" ."):
            excerpt = ""  # 요약이 제목과 동일하면 의미 없으니 버림
        excerpt = excerpt[:300]
        items.append(
            {
                "id": hashlib.sha1(link.encode("utf-8")).hexdigest()[:10],
                "title": title,
                "url": link,
                "source": feed["name"],
                "group": feed.get("group", "기타"),
                "lang": feed.get("lang", "en"),
                "published_kst": when.strftime("%m/%d %H:%M") if when else "",
                "published_iso": when.isoformat() if when else "",
                "sort_key": when.timestamp() if when else 0.0,
                "excerpt": excerpt,
                "matched": [],
            }
        )
    return items, None


def collect(cfg: dict[str, Any]) -> tuple[list[dict], list[dict]]:
    all_items: list[dict] = []
    errors: list[dict] = []
    seen_urls: set[str] = set()
    seen_titles: set[str] = set()

    for feed in cfg.get("feeds", []):
        items, err = fetch_feed(feed, cfg)
        if err:
            errors.append({"stage": "news", "target": feed["name"], "message": err})
            continue
        for it in items:
            tkey = re.sub(r"[^0-9a-z가-힣]", "", it["title"].lower())[:60]
            if it["url"] in seen_urls or tkey in seen_titles:
                continue
            seen_urls.add(it["url"])
            seen_titles.add(tkey)
            all_items.append(it)

    all_items.sort(key=lambda x: x["sort_key"], reverse=True)
    return all_items[: int(cfg.get("max_total_items", 60))], errors


def match_watchlist(items: list[dict], watchlist: list[dict]) -> None:
    """뉴스 제목 ↔ 종목 키워드를 연결한다 (양쪽 모두에 기록)."""
    for stock in watchlist:
        stock.setdefault("news", [])
        for kw in stock.get("keywords", []):
            needle = kw.lower()
            for it in items:
                if needle in it["title"].lower():
                    if stock["symbol"] not in it["matched"]:
                        it["matched"].append(stock["symbol"])
                    if it["id"] not in [n["id"] for n in stock["news"]]:
                        stock["news"].append(
                            {"id": it["id"], "title": it["title"], "url": it["url"],
                             "source": it["source"], "published_kst": it["published_kst"]}
                        )
