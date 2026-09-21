"""시세 수집: 토스(선택) → 야후 → 스투크 순으로 시도한다.

어느 한 소스가 죽어도 전체가 멈추지 않도록, 실패는 예외 대신 기록으로 남긴다.
"""
from __future__ import annotations

import csv
import io
import time
from typing import Any

import requests

UA = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "application/json,text/csv,*/*",
}

YAHOO_HOSTS = [
    "https://query1.finance.yahoo.com",
    "https://query2.finance.yahoo.com",
]


class QuoteError(Exception):
    pass


def _get(url: str, timeout: int) -> requests.Response:
    r = requests.get(url, headers=UA, timeout=timeout)
    r.raise_for_status()
    return r


# ---------------------------------------------------------------- Yahoo
def fetch_yahoo(symbol: str, timeout: int = 20) -> dict[str, Any]:
    last_err = None
    for host in YAHOO_HOSTS:
        url = f"{host}/v8/finance/chart/{requests.utils.quote(symbol)}?range=5d&interval=1d"
        try:
            data = _get(url, timeout).json()
        except Exception as exc:  # 네트워크/파싱 실패 → 다음 호스트
            last_err = exc
            continue

        chart = (data or {}).get("chart") or {}
        if chart.get("error"):
            last_err = QuoteError(str(chart["error"]))
            continue
        results = chart.get("result") or []
        if not results:
            last_err = QuoteError("빈 응답")
            continue

        meta = results[0].get("meta") or {}
        price = meta.get("regularMarketPrice")
        prev = meta.get("chartPreviousClose") or meta.get("previousClose")

        # meta 에 값이 없으면 종가 배열에서 마지막 두 개를 쓴다
        if price is None or prev is None:
            closes = (
                ((results[0].get("indicators") or {}).get("quote") or [{}])[0].get("close")
                or []
            )
            closes = [c for c in closes if c is not None]
            if len(closes) >= 2:
                price = price if price is not None else closes[-1]
                prev = prev if prev is not None else closes[-2]

        if price is None or prev is None:
            last_err = QuoteError("가격 필드 없음")
            continue

        return {
            "price": float(price),
            "prev_close": float(prev),
            "currency": meta.get("currency"),
            "exchange": meta.get("exchangeName"),
            "asof_epoch": meta.get("regularMarketTime"),
            "source": "yahoo",
        }
    raise QuoteError(f"yahoo 실패: {last_err}")


# ---------------------------------------------------------------- Stooq
def fetch_stooq(symbol: str, timeout: int = 20) -> dict[str, Any]:
    """일별 종가 CSV의 마지막 두 줄로 등락을 계산한다."""
    if not symbol:
        raise QuoteError("stooq 심볼 미지정")
    url = f"https://stooq.com/q/d/l/?s={requests.utils.quote(symbol)}&i=d"
    text = _get(url, timeout).text
    rows = list(csv.DictReader(io.StringIO(text)))
    rows = [r for r in rows if (r.get("Close") or "").strip() not in ("", "N/D")]
    if len(rows) < 2:
        raise QuoteError("stooq 데이터 부족")
    last, prev = rows[-1], rows[-2]
    return {
        "price": float(last["Close"]),
        "prev_close": float(prev["Close"]),
        "currency": None,
        "exchange": "stooq",
        "asof_date": last.get("Date"),
        "source": "stooq",
    }


# ---------------------------------------------------------------- 통합
def get_quote(item: dict[str, Any], cfg: dict[str, Any], toss=None) -> dict[str, Any]:
    """설정에 따라 순서대로 시도하고, 성공한 첫 결과에 등락률을 붙여 돌려준다."""
    timeout = int(cfg.get("timeout_sec", 20))
    retry = int(cfg.get("retry", 2))
    symbol = item["symbol"]
    attempts: list[str] = []
    result: dict[str, Any] | None = None

    providers: list[tuple[str, Any]] = []
    if toss is not None:
        providers.append(("toss", lambda: toss.fetch_quote(symbol, timeout)))
    providers.append(("yahoo", lambda: fetch_yahoo(symbol, timeout)))
    if item.get("stooq"):
        providers.append(("stooq", lambda: fetch_stooq(item["stooq"], timeout)))

    for name, fn in providers:
        for n in range(retry):
            try:
                result = fn()
                break
            except Exception as exc:
                attempts.append(f"{name}#{n + 1}: {type(exc).__name__} {exc}")
                time.sleep(1.2 * (n + 1))
        if result:
            break

    out = {
        "name": item["name"],
        "symbol": symbol,
        "unit": item.get("unit", ""),
        "keywords": item.get("keywords", []),
        "ok": bool(result),
        "attempts": attempts,
    }
    if result:
        change = result["price"] - result["prev_close"]
        pct = (change / result["prev_close"] * 100) if result["prev_close"] else 0.0
        out.update(
            price=round(result["price"], 4),
            prev_close=round(result["prev_close"], 4),
            change=round(change, 4),
            change_pct=round(pct, 2),
            currency=result.get("currency"),
            source=result.get("source"),
            asof_epoch=result.get("asof_epoch"),
            asof_date=result.get("asof_date"),
        )
    return out
