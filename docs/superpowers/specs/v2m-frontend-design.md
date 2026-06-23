# V2M 프론트엔드 — 설계 문서

- 상태: 디자인 확정됨(superdesign 드래프트 2종 승인). 구현 대기.
- 상위 설계: [v2m-voice-to-minutes-design.md](v2m-voice-to-minutes-design.md)
- 디자인 시스템: [.superdesign/design-system.md](../../../.superdesign/design-system.md)
- 확정 드래프트:
  - 홈: https://p.superdesign.dev/draft/beaec8ee-36d8-476d-a7f4-b1607a0e96f2
  - 상세: https://p.superdesign.dev/draft/9c73030f-8130-42da-b8a4-8df9bbbdb685

## 1. 목표

확정된 다크 모던(Linear/Vercel 풍) 디자인을 그대로 구현한 **Vite + React + TypeScript** 단일 페이지 앱.
브라우저에서 회의를 녹음 → 로컬 백엔드에 업로드 → 화자별·타임스탬프 전사본 표시 →
회의 정보 + 전사본 + 지시문을 한 번에 **복사**해 claude.ai 데스크탑 앱에 붙여넣는다(자동 열기 없음). md/txt 내보내기 제공.

## 2. 핵심 결정

| 항목 | 결정 | 근거 |
|---|---|---|
| 회의 메타정보 | **백엔드 확장** — `Recording.meta`(JSON) 추가, POST/PATCH 수용, 프롬프트 빌더가 meta 포함 | 확정 디자인의 회의정보 폼(일자·시간·장소·참석자·안건)을 충실히 지원하고, claude.ai가 그 컨텍스트까지 반영한 회의록을 생성 |
| 스택 | Vite 5 · React 18 · TS5(strict) · Vitest + Testing Library(jsdom) | 라우터·상태관리 라이브러리 없음(YAGNI). 뷰 상태 = `view: 'home' | {detail: id}` |
| 스타일 | 디자인 시스템 토큰을 `web/src/styles.css`의 CSS 변수로 1:1 이식. 단일 폰트(Pretendard 스택), 모노스페이스 금지 | 드래프트 충실도 |
| API 호출 | 상대경로 `/api`·`/health`. dev는 Vite 프록시→`127.0.0.1:<port>`, prod는 동일 출처(`web/dist` 마운트) | 데스크탑 래핑 가드레일 유지 |
| 카피 | 전부 한국어 | 단일 사용자 한국어 UI |

### 비목표(YAGNI)
- 앱 내 LLM 호출/회의록 저장(상위 설계 §2 준수 — 복붙까지만)
- 라우터/전역 상태 라이브러리, 다크/라이트 토글(다크 고정)
- 인증·다중 사용자·외부 접속

## 3. 백엔드 확장 (meta)

현재 백엔드(`server/`)는 `title`만 저장한다. 다음을 TDD로 추가한다. **기존 `/api` 계약·테스트는 깨지 않는다**(meta는 전부 선택적).

### 3.1 데이터 모델 — `app/store/models.py`
`Recording`에 선택적 JSON 컬럼 추가:
```python
meta: Optional[dict] = Field(default=None, sa_column=Column(JSON))
```
`meta` 구조(모든 필드 선택적 문자열):
```json
{ "date": "2026-06-23", "time": "14:00", "location": "회의실 A",
  "attendees": "홍길동, 김철수", "agenda": "Q3 로드맵 검토" }
```

### 3.2 API
- `POST /api/recordings` — 기존 `title` 외에 폼 필드 `meta`(JSON 문자열, 선택)를 받아 파싱·저장. 미전송 시 `null`.
- `PATCH /api/recordings/{id}` — `{title?, meta?}` 본문으로 부분 수정. 상세 화면의 "저장"이 호출. 404 처리. 응답은 갱신된 상세.
- `GET /api/recordings/{id}` — 응답에 `meta` 포함.
- `GET /api/recordings` — 목록 항목에 `meta` 포함(상태 행 서브텍스트용; 없으면 생략 가능).
- 나머지(`/status`, `/prompt`, `/export`, `/retry`, `DELETE`)는 변경 없음.

### 3.3 프롬프트 빌더 — `app/prompt/builder.py`
`build_prompt(transcript, meta=None, ...)`로 확장. `meta`가 있으면 지시문과 전사본 사이에 한국어 `[회의 정보]` 블록을 주입:
```
… 지시문 …

=== 회의 정보 ===
- 일자: 2026-06-23 14:00
- 장소: 회의실 A
- 참석자: 홍길동, 김철수
- 안건: Q3 로드맵 검토

=== 전사본 ===
[00:00] SPEAKER_00:
  …
```
빈/누락 필드는 줄 생략. `char_count`·`too_long`은 meta 포함 후 계산. `format_transcript`는 그대로 재사용. `to_markdown`/`to_txt`도 meta 블록을 포함하도록 동일 헬퍼 경유.

### 3.4 마이그레이션
SQLite + SQLModel. 신규 nullable 컬럼이라 기존 행은 `meta=NULL`. 개발 DB는 `create_all`로 신규 컬럼 생성(기존 테이블에 컬럼이 없으면 단순 재생성 또는 가벼운 `ALTER TABLE ADD COLUMN`). 단일 사용자·로컬이라 정식 마이그레이션 도구 불필요.

## 4. 화면 (확정 디자인)

공통: sticky 상단바(blur, V 그라데이션 로고 + 워드마크 V2M), 단일 컬럼 max-width 840px, 앰비언트 글로우, 디자인 시스템 토큰만.

### 4.1 홈
1. **새 회의 카드** — 회의 정보 폼(제목·일자·시간·장소 2열 그리드 + 참석자·안건 전체너비) + **녹음 바**(펄스 점·타이머·시작/정지). 정지 시 폼의 meta와 함께 오디오 업로드 → 목록 갱신.
2. **회의 목록** — 행: 제목 · 서브(일자 · 참석 N명) · 상태 뱃지(대기/전사중/완료/실패) · 삭제. 빈 상태 문구. 활성 항목(recorded/transcribing) 있으면 폴링(3s), 없으면 12s.

### 4.2 상세
1. **회의 정보 카드** — 편집 가능 폼(홈과 동일 필드) + 상태 뱃지 + 저장(secondary, `PATCH` 호출).
2. **회의록 만들기 카드** — primary `전사본+프롬프트 복사`(클립보드 기록 → "복사되었습니다 (N자) — claude.ai 데스크탑 앱에 붙여넣으세요" 토스트, **자동 열기 없음**) + secondary `Markdown 내보내기`·`TXT 내보내기`(백엔드 export 링크). `too_long`이면 분할 안내.
3. **전사본 카드** — 화자별·타임스탬프 세그먼트(연속 동일 화자 그룹화, `[mm:ss] SPEAKER_xx`), 어두운 안쪽 패널 스크롤.
4. 상태별: failed → 오류 + `다시 시도`(retry 후 reload), recorded/transcribing → 대기 안내.

## 5. 프론트 아키텍처

```
web/
  vite.config.ts            # plugin-react, /api+/health 프록시, vitest(jsdom)
  index.html                # lang=ko
  src/
    main.tsx, App.tsx        # 뷰 전환(home ↔ detail)
    styles.css               # 디자인 시스템 CSS 변수 + 컴포넌트 클래스
    lib/
      types.ts               # RecordingStatus, MeetingMeta, Summary, Detail, Transcript, PromptBundle
      api.ts                 # 타입드 fetch 래퍼(meta 포함 upload/patch)
      format.ts              # msToMmss, statusLabel(ko)
    hooks/
      useRecorder.ts         # MediaRecorder(webm/opus, 1s timeslice)
      useRecordings.ts       # 목록 + 적응형 폴링
    features/
      meeting/MeetingForm.tsx       # 회의 정보 폼(홈·상세 공용)
      recorder/RecorderPanel.tsx    # 녹음 바 + 업로드(meta 동반)
      recordings/StatusBadge.tsx
      recordings/RecordingList.tsx
      recordings/RecordingDetail.tsx
      recordings/CopyForClaude.tsx  # 복사 + 토스트(자동 열기 없음)
```

### 타입(추가/변경분)
```ts
export interface MeetingMeta {
  date?: string; time?: string; location?: string; attendees?: string; agenda?: string;
}
// Summary/Detail 에 meta?: MeetingMeta | null 추가
```

## 6. 테스트

- 백엔드: 기존 39개 유지 + meta 신규(모델 라운드트립, POST meta 파싱, PATCH 부분수정/404, 프롬프트·export의 meta 블록, meta 없을 때 회귀). torch 없이 fake로.
- 프론트: 컴포넌트/훅 단위(Vitest + Testing Library) — 녹음·업로드(meta 동반), 목록·폴링, MeetingForm 입력/저장, 전사본 그룹화 렌더, retry, 복사+토스트(자동 열기 호출 안 함 검증), 내보내기 링크.

### 의도적 보류(비차단)
- Playwright E2E(상위 설계 §11): ffmpeg+WhisperX 실서버 필요로 환경 무거움 — 후속 하드닝.
- 첫 실행 모델 다운로드 UI / 설정 페이지(HF 토큰·모델 크기): 핵심 흐름 외 후속.

## 7. 확정 디자인 대비 충실도 체크
- 단일 폰트(모노 금지)·인디고 단일 액센트·상태 4색 — styles.css 토큰으로 강제.
- 자동 외부 앱 열기 금지 — CopyForClaude는 클립보드+토스트만.
- 회의정보(장소·참석자·안건)가 claude.ai 컨텍스트로 전달 — §3.3 프롬프트 meta 블록.
