"""하루치 데이터를 모아 data/YYYY-MM-DD.json 으로 저장한다.

사용법:
  python scripts/collect.py           # 오늘치 수집
  python scripts/collect.py --check   # 소스 생존 점검만 (파일 저장 안 함)
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
import news as news_mod  # noqa: E402
import quotes as quotes_mod  # noqa: E402
import toss as toss_mod  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
KST = dt.timezone(dt.timedelta(hours=9))


def load_config() -> dict:
    with open(ROOT / "config.yaml", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def build_payload(cfg: dict) -> dict:
    now = dt.datetime.now(KST)
    qcfg = cfg.get("quotes", {})
    errors: list[dict] = []

    toss_client = None
    if qcfg.get("use_toss"):
        toss_client = toss_mod.from_env(qcfg.get("toss_quote_path", ""))
        if toss_client is None:
            errors.append({"stage": "toss", "target": "auth",
                           "message": "use_toss=true 인데 TOSS_CLIENT_ID/SECRET 시크릿이 없음 → 야후로 진행"})

    indices, watchlist = [], []
    for item in cfg.get("indices", []):
        q = quotes_mod.get_quote(item, qcfg, toss_client)
        indices.append(q)
        if not q["ok"]:
            errors.append({"stage": "quote", "target": item["name"],
                           "message": " / ".join(q["attempts"][-2:]) or "실패"})

    for item in cfg.get("watchlist", []):
        q = quotes_mod.get_quote(item, qcfg, toss_client)
        watchlist.append(q)
        if not q["ok"]:
            errors.append({"stage": "quote", "target": item["name"],
                           "message": " / ".join(q["attempts"][-2:]) or "실패"})

    items, news_errors = news_mod.collect(cfg.get("news", {}))
    errors.extend(news_errors)
    news_mod.match_watchlist(items, watchlist)

    groups: dict[str, list] = {}
    for it in items:
        groups.setdefault(it["group"], []).append(it)

    return {
        "date": now.strftime("%Y-%m-%d"),
        "generated_at": now.strftime("%Y-%m-%d %H:%M"),
        "weekday": "월화수목금토일"[now.weekday()],
        "site": cfg.get("site", {}),
        "indices": indices,
        "watchlist": watchlist,
        "news": items,
        "news_groups": groups,
        "counts": {
            "indices_ok": sum(1 for x in indices if x["ok"]),
            "indices_total": len(indices),
            "stocks_ok": sum(1 for x in watchlist if x["ok"]),
            "stocks_total": len(watchlist),
            "news": len(items),
        },
        "errors": errors,
    }


def check(cfg: dict) -> int:
    """모든 소스를 한 번씩 찔러보고 살아있는지 표로 출력한다."""
    print("=" * 62)
    print(" 소스 생존 점검")
    print("=" * 62)
    bad = 0

    print("\n[시세]")
    for item in list(cfg.get("indices", [])) + list(cfg.get("watchlist", [])):
        q = quotes_mod.get_quote(item, cfg.get("quotes", {}), None)
        if q["ok"]:
            print(f"  OK   {item['name']:<14} {q['price']:>12,.2f}  ({q['change_pct']:+.2f}%)  via {q['source']}")
        else:
            bad += 1
            print(f"  FAIL {item['name']:<14} {q['attempts'][-1] if q['attempts'] else ''}")

    print("\n[뉴스]")
    ncfg = cfg.get("news", {})
    for feed in ncfg.get("feeds", []):
        items, err = news_mod.fetch_feed(feed, ncfg)
        if err:
            bad += 1
            print(f"  FAIL {feed['name']:<22} {err[:70]}")
        else:
            print(f"  OK   {feed['name']:<22} {len(items)}건  예: {items[0]['title'][:38] if items else ''}")

    print("\n" + ("문제 없음" if bad == 0 else f"실패 {bad}건 → config.yaml 에서 해당 줄을 지우거나 고치세요"))
    return 0 if bad == 0 else 1


def main() -> int:
    cfg = load_config()
    if "--check" in sys.argv:
        return check(cfg)

    payload = build_payload(cfg)
    out_dir = ROOT / "data"
    out_dir.mkdir(exist_ok=True)
    path = out_dir / f"{payload['date']}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")

    c = payload["counts"]
    print(f"저장: {path.relative_to(ROOT)}")
    print(f"  지수 {c['indices_ok']}/{c['indices_total']} · "
          f"종목 {c['stocks_ok']}/{c['stocks_total']} · 뉴스 {c['news']}건 · "
          f"오류 {len(payload['errors'])}건")
    for e in payload["errors"]:
        print(f"  - [{e['stage']}] {e['target']}: {e['message'][:90]}")

    # 데이터가 통째로 비면 실패로 처리해 빈 페이지가 올라가는 것을 막는다
    if c["indices_ok"] == 0 and c["news"] == 0:
        print("수집 결과가 완전히 비어 있음 → 페이지를 갱신하지 않음", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
