"""토스증권 Open API 어댑터.

확인된 사실 (2026-09 기준 공개 문서):
  - REST 베이스 URL : https://openapi.tossinvest.com
  - 토큰 발급       : POST /oauth2/token  (OAuth2 client_credentials)
  - 인증 헤더       : Authorization: Bearer {access_token}
  - 계좌/주문 계열  : X-Tossinvest-Account 헤더 추가 필요
  - 시세 계열       : 현재가 · 호가 · 체결 · 캔들 (국내 KRX / 미국 주식)

확인하지 못한 것:
  - 시세 조회 엔드포인트의 "정확한 경로"와 응답 필드 이름.
    → 키를 발급받은 뒤 `python scripts/toss.py discover` 를 실행하면
      실제 openapi.json 에서 시세 관련 경로 후보를 뽑아 출력합니다.
      그 값을 config 의 quotes.toss_quote_path 에 넣으면 연동이 끝납니다.
  이 파일은 경로를 지어내지 않고, 설정으로 주입받도록 만들어져 있습니다.
"""
from __future__ import annotations

import json
import os
import sys
import time
from typing import Any

import requests

BASE = os.environ.get("TOSS_API_BASE", "https://openapi.tossinvest.com")
TOKEN_PATH = "/oauth2/token"

# 응답에서 현재가 / 전일종가를 찾을 때 훑어볼 키 이름 후보
PRICE_KEYS = ["price", "currentPrice", "closePrice", "last", "tradePrice", "lastPrice"]
PREV_KEYS = ["prevClosePrice", "previousClose", "basePrice", "prevPrice", "prevClose"]


class TossError(Exception):
    pass


class TossClient:
    def __init__(self, client_id: str, client_secret: str, quote_path: str = ""):
        self.client_id = client_id
        self.client_secret = client_secret
        self.quote_path = quote_path
        self._token = None
        self._token_exp = 0.0

    # ------------------------------------------------------------ 인증
    def token(self, timeout: int = 20) -> str:
        if self._token and time.time() < self._token_exp - 60:
            return self._token
        r = requests.post(
            BASE + TOKEN_PATH,
            data={
                "grant_type": "client_credentials",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=timeout,
        )
        if r.status_code >= 400:
            raise TossError(f"토큰 발급 실패 {r.status_code}: {r.text[:200]}")
        body = r.json()
        self._token = body.get("access_token")
        if not self._token:
            raise TossError(f"access_token 없음: {str(body)[:200]}")
        self._token_exp = time.time() + float(body.get("expires_in", 1800))
        return self._token

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token()}", "Accept": "application/json"}

    # ------------------------------------------------------------ 시세
    def fetch_quote(self, symbol: str, timeout: int = 20) -> dict[str, Any]:
        if not self.quote_path:
            raise TossError("quote_path 미설정 (discover 로 경로 확인 필요)")
        # 예: "/api/v1/quotes/{symbol}/price"  또는 "/api/v1/quotes/price?code={symbol}"
        path = self.quote_path.replace("{symbol}", symbol).replace("{code}", symbol)
        r = requests.get(BASE + path, headers=self._headers(), timeout=timeout)
        if r.status_code >= 400:
            raise TossError(f"시세 조회 실패 {r.status_code}: {r.text[:200]}")
        data = r.json()
        price = _dig(data, PRICE_KEYS)
        prev = _dig(data, PREV_KEYS)
        if price is None or prev is None:
            raise TossError(f"가격 필드 못 찾음. 응답 예시: {str(data)[:300]}")
        return {
            "price": float(price),
            "prev_close": float(prev),
            "currency": None,
            "exchange": "toss",
            "source": "toss",
        }

    # ------------------------------------------------------- 경로 찾기
    def discover(self, timeout: int = 30) -> list[str]:
        r = requests.get(BASE + "/openapi.json", headers=self._headers(), timeout=timeout)
        r.raise_for_status()
        spec = r.json()
        hits = []
        for path, ops in (spec.get("paths") or {}).items():
            low = path.lower()
            if any(k in low for k in ("price", "quote", "ticker", "candle", "trade")):
                methods = ",".join(m.upper() for m in ops if m in ("get", "post"))
                summary = ""
                for m in ops.values():
                    if isinstance(m, dict) and m.get("summary"):
                        summary = m["summary"]
                        break
                hits.append(f"{methods:<6} {path}   {summary}")
        return sorted(hits)


def _dig(obj: Any, keys: list[str]) -> Any:
    """중첩된 응답 어디에 있든 후보 키를 찾아 숫자를 돌려준다."""
    if isinstance(obj, dict):
        for k in keys:
            if k in obj and isinstance(obj[k], (int, float, str)):
                try:
                    return float(obj[k])
                except (TypeError, ValueError):
                    pass
        for v in obj.values():
            got = _dig(v, keys)
            if got is not None:
                return got
    elif isinstance(obj, list):
        for v in obj:
            got = _dig(v, keys)
            if got is not None:
                return got
    return None


def from_env(quote_path: str = "") -> "TossClient | None":
    cid, sec = os.environ.get("TOSS_CLIENT_ID"), os.environ.get("TOSS_CLIENT_SECRET")
    if not cid or not sec:
        return None
    return TossClient(cid, sec, quote_path or os.environ.get("TOSS_QUOTE_PATH", ""))


if __name__ == "__main__":
    client = from_env()
    if not client:
        sys.exit("환경변수 TOSS_CLIENT_ID / TOSS_CLIENT_SECRET 가 없습니다.")
    if len(sys.argv) > 1 and sys.argv[1] == "discover":
        print(f"베이스: {BASE}")
        for line in client.discover():
            print(" ", line)
    else:
        sym = sys.argv[1] if len(sys.argv) > 1 else "005930"
        print(json.dumps(client.fetch_quote(sym), ensure_ascii=False, indent=2))
