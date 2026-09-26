"""data/*.json → docs/ 정적 페이지 생성.

  docs/index.html          가장 최근 날짜 (첫 화면)
  docs/posts/YYYY-MM-DD.html  날짜별 글
  docs/archive.html        날짜 목록
  docs/important.html      날짜별 핵심 뉴스 모음 (analysis.important=true 인 기사)
"""
from __future__ import annotations

import json
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
DOCS = ROOT / "docs"
TPL = ROOT / "templates"


# ── 템플릿에서 쓰는 표시 헬퍼 ────────────────────────────────
def fmt(v) -> str:
    if v is None:
        return "—"
    v = float(v)
    if abs(v) >= 1000:
        return f"{v:,.0f}"
    if abs(v) >= 100:
        return f"{v:,.1f}"
    return f"{v:,.2f}"


def sgn(v) -> str:
    if v is None:
        return "—"
    v = float(v)
    body = fmt(abs(v))
    return f"+{body}" if v > 0 else (f"−{body}" if v < 0 else body)


def cls(pct) -> str:
    """한국 증시 관례: 상승 빨강 · 하락 파랑. 화살표와 부호를 함께 쓴다."""
    if pct is None:
        return "flat"
    return "up" if pct > 0 else ("down" if pct < 0 else "flat")


def arrow(pct) -> str:
    if pct is None:
        return ""
    return "▲" if pct > 0 else ("▼" if pct < 0 else "―")


def used_sources(d: dict) -> str:
    names = {x.get("source") for x in d.get("indices", []) + d.get("watchlist", []) if x.get("ok")}
    label = {"yahoo": "Yahoo Finance", "stooq": "Stooq", "toss": "토스증권 Open API"}
    return ", ".join(label.get(n, n) for n in sorted(n for n in names if n)) or "없음"


def main() -> int:
    DOCS.mkdir(exist_ok=True)
    (DOCS / "posts").mkdir(exist_ok=True)
    (DOCS / ".nojekyll").write_text("", encoding="utf-8")

    env = Environment(
        loader=FileSystemLoader(str(TPL)),
        autoescape=select_autoescape(["html", "j2"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    css = (TPL / "base.css").read_text(encoding="utf-8")
    post_tpl = env.get_template("post.html.j2")
    arch_tpl = env.get_template("archive.html.j2")
    imp_tpl = env.get_template("important.html.j2")

    files = sorted(DATA.glob("*.json"), reverse=True)
    if not files:
        print("data/*.json 이 없습니다. 먼저 collect.py 를 실행하세요.")
        return 1

    summaries = []
    key_days = []
    for path in files:
        d = json.loads(path.read_text(encoding="utf-8"))
        # news_groups는 news 목록에서 매번 다시 계산한다 (편집 후 재생성 시 불일치 방지)
        groups: dict[str, list] = {}
        for it in d.get("news", []):
            groups.setdefault(it["group"], []).append(it)
        d["news_groups"] = groups
        d["top_news"] = [it for it in d.get("news", [])
                         if (it.get("analysis") or {}).get("important")]
        if d["top_news"]:
            key_days.append({"date": d["date"], "weekday": d.get("weekday", ""),
                             "news": d["top_news"]})
        helpers = dict(css=css, fmt=fmt, sgn=sgn, cls=cls, arrow=arrow,
                       sources=used_sources(d))
        (DOCS / "posts" / f"{d['date']}.html").write_text(
            post_tpl.render(d=d, root="../", **helpers), encoding="utf-8")
        summaries.append({"date": d["date"], "weekday": d.get("weekday", ""),
                          "counts": d.get("counts", {}), "top": len(d["top_news"])})
        if path == files[0]:  # 최신 글은 첫 화면으로도 복사
            (DOCS / "index.html").write_text(
                post_tpl.render(d=d, root="", **helpers), encoding="utf-8")

    site = json.loads(files[0].read_text(encoding="utf-8")).get("site", {})
    (DOCS / "archive.html").write_text(
        arch_tpl.render(posts=summaries, site=site, css=css), encoding="utf-8")
    (DOCS / "important.html").write_text(
        imp_tpl.render(days=key_days, total=sum(len(x["news"]) for x in key_days),
                       site=site, css=css), encoding="utf-8")

    print(f"생성: docs/index.html, docs/archive.html, docs/important.html, 글 {len(summaries)}개")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
