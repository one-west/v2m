# V2M — Voice to Minutes

회의 음성을 **내 PC에서 무료로** 녹음·전사하고, 화자별 타임스탬프 전사본을 만들어
**구독 중인 claude.ai에 붙여넣어 정형화된 회의록**을 받는 개인용 로컬 도구.

- **로컬 우선·$0**: STT·화자분리를 로컬 WhisperX로 처리(API 과금 없음). 정형화(요약/결정/액션아이템)는
  앱이 LLM을 호출하지 않고, 사용자의 claude.ai 구독에 붙여넣어 수행.
- **오프라인**: 녹음→전사까지 인터넷 없이 동작(localhost). 정형화 단계만 claude.ai 접속.
- **프라이빗**: 오디오·전사본이 PC 밖으로 나가지 않음.

## 처리 흐름

```
[브라우저] 녹음(MediaRecorder, webm/opus)
  → 로컬 서버 업로드 → WhisperX: STT + 화자분리 + 타임스탬프
  → SQLite 저장 → 화면에 회의 정보 폼 + 화자별 전사본 표시
  → "전사본 + 프롬프트 복사" → claude.ai 데스크탑 앱에 붙여넣기 → 정형화 회의록
  (전사본 Markdown/TXT 내보내기 가능)
```

## 상태

- ✅ **백엔드**(`server/`, FastAPI): 업로드 → 백그라운드 전사 잡 → 전사본/프롬프트/내보내기 API + 회의 정보(meta). 53 테스트.
- ✅ **프론트엔드**(`web/`, Vite + React + TS): 녹음·회의정보 입력·목록·전사본 뷰·claude.ai용 복사·내보내기. 27 테스트.
- ✅ **실제 WhisperX 전사 검증 완료**(Windows, Python 3.12): STT + 단어 정렬 + 화자분리 end-to-end.
- 🔜 **데스크탑 앱**(pywebview 패키징)은 Phase 2 계획 — 아직 미구현.

설계·결정 근거는 [docs/superpowers/specs/v2m-voice-to-minutes-design.md](docs/superpowers/specs/v2m-voice-to-minutes-design.md),
구현 계획은 [docs/superpowers/plans/](docs/superpowers/plans/) 참고.

## 구성

```
v2m/
  server/   FastAPI + WhisperX(faster-whisper + pyannote) + SQLite   (Python)
  web/      Vite + React + TypeScript SPA                            (TypeScript)
  docs/     설계 스펙 + 구현 계획
```

프론트는 상대경로 `/api`로 백엔드를 호출합니다. 개발 시 Vite 프록시가 `:8000`으로 연결하고,
운영 시 FastAPI가 빌드된 `web/dist`를 서빙해 단일 프로세스로 동작합니다.

## 요구 사항

| 대상 | 필요 |
|---|---|
| 백엔드 + 테스트 | Python 3.11+ |
| **실제 전사(`[ml]`)** | **Python 3.11–3.12** (torch/ctranslate2가 3.13/3.14 휠 미지원), **ffmpeg**(PATH) |
| 화자분리 | HuggingFace 토큰 + `pyannote/speaker-diarization-community-1` 게이트 약관 동의(무료, 1회) |
| 프론트엔드 | Node.js 18+ |

> 테스트 스위트는 가짜 전사기를 쓰므로 torch/whisperx 없이 어떤 3.11+ 에서도 동작합니다.
> 실제 전사만 별도의 Python 3.12 venv가 필요합니다.

## 빠른 시작

### 한 번에 실행 (개발) — 권장

루트에서 한 번만 설치하면 백엔드+프론트가 같이 뜹니다.

```bash
npm install        # 루트: concurrently 설치 (최초 1회)
npm run dev        # 백엔드(:8000) + 프론트(:5173) 동시 실행
```

- 백엔드는 **`server/.venv-ml`**(실제 전사용 Python 3.12 venv)로 실행됩니다 — 아래 백엔드 셋업에서
  `.venv-ml`을 먼저 만들어 두세요. (비-Windows는 `package.json`의 `dev:server` 경로를 `.venv-ml/bin/python`으로 조정)
- 프론트는 `/api`를 백엔드 `:8000`으로 프록시합니다. 브라우저에서 `http://localhost:5173` 접속.

각각 따로 실행하려면 아래를 참고하세요.

### 1) 백엔드

```bash
cd server
python -m venv .venv && .venv/Scripts/activate        # Windows
pip install -e ".[dev]"                                # 앱 + 테스트 (torch 없음)
python -m pytest -q                                    # 39 tests

# 실제 전사까지 하려면 (Python 3.12 venv 권장):
#   pip install -e ".[dev,ml]"
#   cp .env.example .env  → V2M_HF_TOKEN 입력 (community-1 약관 동의 후)
#   ffmpeg 를 PATH 에 설치
python run.py                                          # http://127.0.0.1:8000
```

### 2) 프론트엔드

```bash
cd web
npm install
npm run dev      # 개발 서버 (백엔드 :8000 으로 /api 프록시)
npm test         # 23 tests
npm run build    # web/dist 생성 → 백엔드가 / 에서 서빙
```

운영: `web` 빌드 후 `server`의 `python run.py`만 실행하면 한 프로세스로 UI+API가 뜹니다.

## 데이터 위치

DB·오디오·모델·로그는 설치 폴더가 아닌 **`%LOCALAPPDATA%\v2m\`** 아래에 저장됩니다
(`V2M_DATA_DIR`로 변경 가능). 설정은 `server/.env`(`V2M_` 접두사)로 관리합니다.

## 정형화(회의록) 단계

앱은 LLM을 호출하지 않습니다. 전사본 화면에서 **"전사본 + 프롬프트 복사"**를 누르면
한국어 회의록 지시 프롬프트와 화자별 전사본(+입력한 회의 정보)이 클립보드에 복사됩니다 —
**claude.ai 데스크탑 앱에 붙여넣으면** 요약·핵심 논의·결정사항·액션아이템으로 정형화됩니다.
(앱이 claude.ai를 자동으로 열지는 않습니다. 긴 회의는 입력 한도 안내가 표시됩니다.)

## 라이선스

[LICENSE](LICENSE) 참고.
