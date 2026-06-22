# V2M (Voice to Minutes) — 설계 문서

- 날짜: 2026-06-22
- 상태: 설계 확정 대기 (사용자 검토 중)

## 1. 목표 (한 문장)

회의 음성을 **로컬에서 무료로** 녹음·전사하고, 화자별로 구분된 타임스탬프 전사본을 만들어,
**구독 중인 claude.ai에 한 번에 붙여넣어 정형화된 회의록**을 받을 수 있게 하는 개인용 로컬 웹앱.

## 2. 핵심 제약 / 결정

| 항목 | 결정 | 근거 |
|---|---|---|
| 비용 | **$0** | STT·화자분리는 로컬 무료, 정형화는 기존 claude.ai 구독(복붙) |
| 실행 환경 | **완전 로컬 (localhost 웹앱)** | 이 PC에서만 사용. 무제한·프라이빗·오프라인 |
| 오프라인 | **전 과정 오프라인 동작** | 녹음·전사까지 인터넷 불필요 (정형화 단계만 claude.ai 접속) |
| 정형화(LLM) | **앱에 미포함 — claude.ai 수동 복붙** | API 키·과금 0원. 앱은 전사본+프롬프트까지만 |
| 결과물 관리 | **전사본만 관리** | 정형화된 회의록은 claude.ai 측에 남김 |
| 대상 기기 | AMD Ryzen AI 7 445 / 32GB RAM / GPU 가속 약함(CPU 기반) | 모델 크기를 CPU 친화적으로 선택 |

### 명시적 비목표 (YAGNI)
- 앱 내 LLM 호출 (Claude API / Ollama) — 미포함 (향후 확장 여지만 남김)
- 정형화된 회의록의 앱 내 저장·PDF/Word 내보내기
- 다중 기기/외부 접속, 멀티 유저, 인증
- 오프라인 업로드 동기화 큐(tus·Background Sync) — localhost라 불필요
- PWA 오프라인 셸 — localhost 전용이라 불필요

## 3. 아키텍처 개요

PC에서 로컬 서버를 실행하고 브라우저로 접속하는 단일 사용자 로컬 웹앱.

```
[브라우저] 녹음 (MediaRecorder, webm/opus)
   → 로컬 서버 업로드 · 디스크 저장 (status: recorded)
   → [백그라운드 잡] WhisperX: STT + 화자분리 + 타임스탬프 (status: transcribing)
   → 전사본(segments) SQLite 저장 (status: done)
   → [화면] 화자별·타임스탬프 전사본 표시
   → "전사본 + 회의록 프롬프트 한 번에 복사" → claude.ai 열기 → 붙여넣기 → 정형화 회의록
```

## 4. 기술 스택

| 레이어 | 선택 | 비고 |
|---|---|---|
| 프론트 | **Vite + React + TypeScript** | 녹음 UI·전사본 뷰·복사 |
| 녹음 | **MediaRecorder** (`audio/webm;codecs=opus`, `start(timeslice)` 청크) | 긴 녹음 크래시 견딤 |
| 백엔드 | **FastAPI (Python)** + 백그라운드 잡 | AI 도구가 Python 네이티브 |
| STT+화자분리 | **WhisperX** (faster-whisper `medium` int8 + pyannote 3.x) | 전사+화자+단어 타임스탬프 한 파이프라인. 로컬 $0 |
| DB | **SQLite** (SQLModel) | 단순·로컬 |
| 오디오 저장 | 로컬 디스크 (`data/audio/`) | DB엔 경로만 |
| 내보내기 | 전사본 → **Markdown / TXT + 클립보드 복사** | 정형화 회의록은 claude.ai |
| 외부 의존 | **ffmpeg** (WhisperX 필수), **HuggingFace 토큰** (pyannote 게이트 모델, 무료 1회 설정) | |

### CPU 기반 모델 기본값 (32GB RAM)
- WhisperX: **`medium`** (int8) — 한국어 정확도/속도 균형. 느리면 `small`로 설정 변경
- 처리는 **백그라운드 잡 큐**로 실행하고 진행 상태 표시 (1시간 회의 STT가 수십 분 걸릴 수 있음)
- ⚠️ pyannote 화자분리 모델은 HuggingFace 토큰 + 모델 약관 동의(무료)가 1회 필요

## 5. 저장소 구조

```
v2m/
  web/                    # Vite + React + TS 프론트엔드
    src/
      lib/api.ts          # 백엔드 API 클라이언트
      features/recorder/  # 녹음 컴포넌트·훅
      features/recordings/# 목록·상세(전사본)·복사
  server/                 # FastAPI 백엔드
    app/
      main.py             # FastAPI 진입점, 정적 프론트 서빙
      api/recordings.py   # 업로드·목록·상세·상태·재시도 엔드포인트
      jobs/queue.py       # 백그라운드 전사 잡
      transcribe/whisperx_runner.py  # WhisperX 래퍼
      store/models.py     # SQLModel 모델
      store/db.py         # 세션·초기화
      prompt/builder.py   # 회의록 프롬프트 + 전사본 직렬화
      export/markdown.py  # 전사본 MD/TXT 내보내기
    data/                 # SQLite + 오디오 (gitignore)
```

> 프론트(TS)·백엔드(Python)가 다른 언어라 pnpm 워크스페이스 없이 두 폴더로 단순 분리.
> 운영 시 FastAPI가 `web/dist` 정적 파일을 서빙해 단일 프로세스로 실행.

## 6. 데이터 모델

```
Recording
  id            (uuid)
  title         (str)            # 기본값: 녹음 일시
  created_at    (datetime)
  duration_sec  (int | null)
  audio_path    (str)            # data/audio/<id>.webm
  status        (enum)           # recorded | transcribing | done | failed
  error         (str | null)
  transcript    (JSON | null)    # { segments: [...], full_text: str, language: str }
```

전사본 `segments` 항목:
```
{ "speaker": "SPEAKER_01", "start_ms": 0, "end_ms": 4200, "text": "..." }
```

> 전사본은 단일 JSON 컬럼으로 저장(MVP 단순화). 화자/타임스탬프 검색이 필요해지면 별도 Segment 테이블로 정규화.

### 상태 머신
```
recorded → transcribing → done
                       ↘ failed → (재시도) → transcribing
```

## 7. 컴포넌트 / 책임

| 모듈 | 책임 | 의존 |
|---|---|---|
| `Recorder` (web) | MediaRecorder 녹음, opus 청크, 업로드 | api |
| `RecordingList` (web) | 회의 목록·상태·진행률 | api |
| `RecordingDetail` (web) | 화자별·타임스탬프 전사본 표시 | api |
| `CopyForClaude` (web) | 전사본+프롬프트 클립보드 복사, claude.ai 열기 | prompt 결과 |
| `IngestAPI` (server) | 오디오 수신·디스크 저장·Recording 생성·잡 등록 | store, jobs |
| `JobQueue` (server) | 전사 잡 백그라운드 실행, 상태 갱신 | transcribe, store |
| `WhisperXRunner` (server) | WhisperX 호출 → segments. **인터페이스 추상화**(향후 교체) | whisperx |
| `Store` (server) | SQLite CRUD (Recording) | sqlmodel |
| `PromptBuilder` (server) | 한국어 회의록 프롬프트 + 전사본 직렬화 | — |
| `Exporter` (server) | 전사본 MD/TXT 변환 | — |

## 8. API (로컬)

| 메서드 | 경로 | 설명 |
|---|---|---|
| POST | `/api/recordings` | 오디오 업로드 → Recording 생성(recorded) → 전사 잡 등록 |
| GET | `/api/recordings` | 목록 (id, title, created_at, status, duration) |
| GET | `/api/recordings/{id}` | 상세 + 전사본(segments) |
| GET | `/api/recordings/{id}/status` | 진행 상태·진행률 폴링 |
| POST | `/api/recordings/{id}/retry` | 실패 시 전사 재시도 |
| GET | `/api/recordings/{id}/prompt` | 회의록 프롬프트 + 전사본 텍스트 (복사용) |
| GET | `/api/recordings/{id}/export?format=md\|txt` | 전사본 내보내기 |
| DELETE | `/api/recordings/{id}` | 녹음·전사본 삭제 |

## 9. 정형화 프롬프트 (claude.ai 붙여넣기용)

`PromptBuilder`가 생성하는 묶음:
1. 회의록 정형화 지시 프롬프트 (한국어) — 요약 / 핵심 논의 / 결정사항 / 액션아이템(담당·기한) 형식 지정
2. 화자별·타임스탬프로 정리된 전사본 텍스트

> 긴 회의(수만 토큰)는 claude.ai 입력 한도에 걸릴 수 있어, UI에서 길이 경고 + 분할 복사 옵션 제공.

## 10. 에러 처리

- 마이크 권한 거부 → 명확한 안내 UI
- 전사 실패 → `failed` + error 저장, 부분결과 보존, 재시도 버튼
- ffmpeg/pyannote 토큰 미설정 → 서버 기동 시 점검 + 설정 안내 메시지
- 큰 녹음 → 청크 녹음으로 메모리 안전, 정지 후 단일 파일 업로드
- 디스크 여유 점검(선택)

## 11. 테스트 전략

- **백엔드 단위**: `WhisperXRunner`(모킹), `PromptBuilder`, 상태 머신 전이, `Exporter` 렌더링, `Store` CRUD
- **백엔드 통합**: 업로드 → 백그라운드 전사(WhisperX 모킹) → status=done → 전사본 조회
- **프론트 단위**: 녹음 훅, api 클라이언트, CopyForClaude 동작
- **E2E (Playwright)**: 녹음(모킹) → 전사본 표시 → 복사 → 내보내기

## 12. 실행 방식

- 백엔드: Python 3.11+, `uvicorn app.main:app`. ffmpeg PATH 필요. `.env`에 HF 토큰.
- 프론트: 개발 시 Vite dev 서버가 `/api`를 FastAPI로 프록시. 운영 시 `web/dist` 빌드 후 FastAPI가 서빙.
- 단일 명령 실행 스크립트로 서버 기동 → 브라우저에서 `http://localhost:<port>` 접속.

## 13. 향후 확장 여지 (지금은 미구현)

- `MinutesGenerator` 인터페이스 추가로 앱 내 자동 정형화(Claude API / 로컬 Ollama) 옵션
- 정형화 회의록 앱 내 저장·검색
- Tauri 래핑으로 원클릭 데스크톱 실행
- 외부 접속(터널) 또는 무료 클라우드 호스팅
