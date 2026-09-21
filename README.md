# 오늘의 경제 한 장

매일 정해진 시각에 **지수·환율·관심종목 등락 + 공신력 있는 기관/언론 RSS 경제뉴스**를
한 페이지로 자동 생성해 GitHub Pages에 올립니다. 서버도, PC를 켜 둘 필요도 없습니다.
(GitHub Actions가 대신 돌려 줍니다 → 사지방에서 브라우저만 있으면 운영 가능)

```
collect.py  시세 + 뉴스 수집 → data/YYYY-MM-DD.json
build.py    JSON → docs/index.html · docs/posts/날짜.html · docs/archive.html
daily.yml   매일 자동 실행 → 결과를 저장소에 커밋
```

---

## 1. 설치 (10분, 브라우저만 사용)

1. GitHub에서 새 저장소 생성 — 이름 예: `econ-daily`, **Public**, "Add a README" 체크 해제
2. 저장소 첫 화면 → **uploading an existing file** 클릭
3. 이 폴더의 파일을 **폴더 구조 그대로** 끌어다 놓고 `Commit changes`
   (`.github/workflows/daily.yml` 경로가 반드시 유지돼야 합니다. 압축을 푼 뒤
   폴더째로 드래그하면 구조가 유지됩니다.)
   - 만약 `.github` 폴더가 숨김 처리돼 업로드되지 않으면:
     저장소 → **Add file → Create new file** → 파일명 칸에
     `.github/workflows/daily.yml` 을 그대로 입력하면 폴더가 자동 생성됩니다.
     거기에 `daily.yml` 내용을 붙여넣고 커밋하세요.
4. 저장소 **Settings → Pages** → Source: `Deploy from a branch`,
   Branch: `main` / 폴더: `/docs` → Save
5. 저장소 **Settings → Actions → General** →
   *Workflow permissions* 를 **Read and write permissions** 로 변경 → Save
   (이걸 안 하면 자동 커밋이 권한 오류로 실패합니다)

## 2. 첫 실행 — 먼저 소스 점검부터

저장소 **Actions 탭 → "매일 경제 브리핑" → Run workflow** →
`check_only` 를 **true** 로 두고 실행하세요.

로그에 소스별로 `OK` / `FAIL` 이 찍힙니다.

- `FAIL` 난 뉴스 피드는 `config.yaml` 에서 그 줄을 지우세요.
- 시세가 전부 `FAIL` 이면 `config.yaml` 의 `quotes.primary` 를 `stooq` 로 바꿔 다시 점검하세요.

점검이 끝나면 `check_only` 를 **false** 로 두고 다시 Run workflow →
`docs/index.html` 이 만들어지고 `https://아이디.github.io/econ-daily/` 에서 보입니다.
(Pages 최초 반영까지 1~2분 걸립니다)

## 3. 매일 자동 실행 시각

| 실행 | KST | 목적 |
|---|---|---|
| `10 22 * * *` | 07:10 | 미국장 마감 직후 아침 브리핑 |
| `10 7 * * 1-5` | 16:10 | 국내장 마감 반영 (평일) |

같은 날짜 페이지는 덮어쓰기됩니다. 시간을 바꾸려면 `.github/workflows/daily.yml` 의
cron 값을 고치세요 — **UTC 기준**이라 원하는 KST 시각에서 9시간을 빼면 됩니다.

## 4. 내용 바꾸기 — `config.yaml` 만 고치면 됩니다

- `watchlist` : 관심종목 추가/삭제.
  `symbol` 은 Yahoo 기준 (국내는 `종목코드.KS`, 코스닥은 `.KQ`, 미국은 티커 그대로)
- `keywords` : 뉴스 제목에 이 단어가 있으면 해당 종목 카드에 기사가 붙습니다
- `news.feeds` : 뉴스 소스 추가/삭제
- `indices` : 상단 타일

## 5. 토스증권 Open API 연동 (계좌 만든 뒤)

지금은 API 키 없이 Yahoo Finance(예비: Stooq)로 시세를 가져옵니다.
토스 키가 생기면 아래 3단계로 갈아끼울 수 있습니다.

1. 토스증권 PC웹(WTS) → 설정 → Open API 에서 `client_id` / `client_secret` 발급
2. 저장소 **Settings → Secrets and variables → Actions** 에
   `TOSS_CLIENT_ID`, `TOSS_CLIENT_SECRET` 등록
3. 로컬(또는 Actions 로그)에서 `python scripts/toss.py discover` 실행 →
   출력된 시세 엔드포인트 경로를 `config.yaml` 에 적고 `use_toss: true` 로 변경

```yaml
quotes:
  use_toss: true
  toss_quote_path: "/여기에/discover로/확인한/경로/{symbol}"
```

> **솔직한 한계**: 토스 Open API의 베이스 URL·OAuth 방식·시세 제공 범위는 공개 문서로
> 확인했지만, **시세 엔드포인트의 정확한 경로와 응답 필드 이름은 확인하지 못했습니다**
> (인증된 사용자만 스펙 문서 접근 가능). 그래서 경로를 지어내지 않고 `discover`
> 명령으로 직접 확인해 넣도록 만들어 두었습니다.

## 6. 로컬에서 돌려보기 (선택)

```bash
pip install -r requirements.txt
python scripts/collect.py --check   # 소스 점검
python scripts/collect.py           # 수집
python scripts/build.py             # 페이지 생성 → docs/ 열어보기
```

---

## 알아둘 점

- **뉴스는 제목·출처·시각·원문 링크만** 저장합니다. 본문은 가져오지 않습니다
  (저작권). 요약·해석도 하지 않습니다.
- 시세 소스(Yahoo/Stooq)는 **비공식 공개 엔드포인트**라 예고 없이 막힐 수 있습니다.
  그래서 2단 폴백과 `--check` 점검 모드를 넣었습니다. 한쪽이 막히면 페이지에
  "수집 실패" 로 표시되고 나머지는 정상 생성됩니다.
- GitHub Actions의 cron은 **정확한 시각을 보장하지 않습니다** (혼잡 시 수 분~수십 분 지연).
- 공개 저장소의 예약 워크플로는 저장소가 오래 방치되면 자동 비활성화될 수 있습니다.
  이 워크플로는 매일 커밋을 남기므로 정상 동작 중에는 해당되지 않습니다.
- 상승 = 빨강 / 하락 = 파랑 (국내 증시 관례). 색만으로 구분하지 않도록 ▲▼ 기호와
  부호를 함께 표시합니다.
