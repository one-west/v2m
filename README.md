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
  (녹음 원본 재생 · mp3 다운로드 · 전사본 Markdown/TXT 내보내기 가능)
```

## 주요 기능

- **브라우저 녹음 + 유실 방지**: 녹음 조각을 IndexedDB에 계속 저장하므로 새로고침·절전·크래시 후에도
  다시 열면 **복구** 버튼으로 이어서 업로드할 수 있습니다. 녹음 중 화면을 옮겨도 녹음은 계속되고,
  창을 닫으려 하면 경고합니다.
- **회의 정보 입력**: 날짜·시간·장소·참석자·안건(모두 선택)을 저장하면 프롬프트/내보내기에 `회의 정보` 블록으로 들어갑니다.
  녹음 후 상세 화면에서도 수정할 수 있습니다.
- **회의별 전사 언어**: 새 회의 폼에서 `한국어 / English / 자동 감지`를 선택(기본은 `V2M_LANGUAGE`).
  조용하거나 짧은 한국어를 다른 언어로 오인식하는 문제를 막기 위해 기본은 언어를 고정합니다.
- **전사 진행 단계 표시**: 모델 로딩 → 음성 인식 → 정렬 → 화자 분리 단계(긴 녹음은 `음성 인식 (k/n)`)를 화면에 표시합니다.
- **실패 시 재시도**: 전사 실패나 서버 재시작으로 중단된 녹음은 `실패`로 표시되고 버튼 하나로 다시 전사합니다.
- **빠른 모드**(`V2M_DIARIZE=false`): 정렬·화자분리를 건너뛰어 약 10배 빠르게 전사합니다(화자 구분 없이 `SPEAKER_00`).
  긴 녹음은 ~1시간 단위로 무음 지점에서 잘라 순차 전사합니다(`V2M_CHUNK_MINUTES`).
- **녹음 재생·다운로드**: 앱 안에서 원본을 재생(탐색 가능)하고, mp3로 내려받을 수 있습니다.
  파일명은 회의 제목을 따릅니다.

## 상태

- ✅ **백엔드**(`server/`, FastAPI): 업로드 → 백그라운드 전사 잡 → 전사본/프롬프트/내보내기 API + 회의 정보(meta) + 녹음 재생·mp3 다운로드. 100 테스트.
- ✅ **프론트엔드**(`web/`, Vite + React + TS): 녹음·회의정보 입력·목록·전사본 뷰·녹음 재생·claude.ai용 복사·내보내기. 52 테스트.
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
| **mp3 다운로드** | **ffmpeg**(PATH 또는 `V2M_FFMPEG_DIR`) — 전사와 같은 ffmpeg를 씁니다 |
| 프론트엔드 | Node.js 18+ |

> 테스트 스위트는 가짜 전사기를 쓰므로 torch/whisperx 없이 어떤 3.11+ 에서도 동작합니다.
> 실제 전사만 별도의 Python 3.12 venv가 필요합니다.

## 빠른 시작

### 원클릭 실행 (실사용) — `start.bat`

빌드된 프론트(`web/dist`)를 백엔드가 `/`에서 서빙하는 단일 프로세스 모드입니다. 루트의 **`start.bat`을 더블클릭**하면:

1. `web/dist`가 없으면 최초 1회 빌드
2. 백엔드(`server/.venv-ml`)를 실행하고
3. 3초 뒤 기본 브라우저로 `http://127.0.0.1:8000`을 자동으로 엽니다.

창을 닫으면 서버가 정지합니다. `.venv-ml`을 먼저 만들어 두어야 하며(아래 백엔드 셋업), `.env`에서 `V2M_PORT`를 바꾸면 `start.bat`의 URL도 함께 고치세요. UI를 수정했다면 `web/dist`를 지우고 다시 실행하면 자동으로 재빌드됩니다.

### 한 번에 실행 (개발) — 권장

루트에서 한 번만 설치하면 백엔드+프론트가 같이 뜹니다.

```bash
npm install        # 루트: concurrently 설치 (최초 1회)
npm run dev        # 백엔드(:8000) + 프론트(:5174) 동시 실행
```

- 백엔드는 **`server/.venv-ml`**(실제 전사용 Python 3.12 venv)로 실행됩니다 — 아래 백엔드 셋업에서
  `.venv-ml`을 먼저 만들어 두세요. (비-Windows는 `package.json`의 `dev:server` 경로를 `.venv-ml/bin/python`으로 조정)
- 프론트는 `/api`를 백엔드 `:8000`으로 프록시합니다. 브라우저에서 `http://localhost:5174` 접속.

각각 따로 실행하려면 아래를 참고하세요.

### 1) 백엔드

```bash
cd server
python -m venv .venv && .venv/Scripts/activate        # Windows
pip install -e ".[dev]"                                # 앱 + 테스트 (torch 없음)
python -m pytest -q                                    # 100 tests

# 실제 전사까지 하려면 (Python 3.12 venv 권장):
#   pip install -e ".[dev,ml]"
#   cp .env.example .env  → V2M_HF_TOKEN 입력 (community-1 약관 동의 후)
#   (.env.example 은 빠른 모드 기본값 — 화자 구분이 필요하면 V2M_DIARIZE=true)
#   ffmpeg 를 PATH 에 설치
python run.py                                          # http://127.0.0.1:8000
```

### 2) 프론트엔드

```bash
cd web
npm install
npm run dev      # 개발 서버 (백엔드 :8000 으로 /api 프록시)
npm test         # 52 tests
npm run build    # web/dist 생성 → 백엔드가 / 에서 서빙
```

운영: `web` 빌드 후 `server`의 `python run.py`만 실행하면 한 프로세스로 UI+API가 뜹니다.

## 설정 (`server/.env`)

모든 설정은 `V2M_` 접두사 환경변수입니다. `server/.env.example`을 복사해 쓰세요.

> **`.env.example`은 실사용 권장값**(`large-v3-turbo` + 빠른 모드)이고, 코드 기본값(`medium` + 화자분리 켬)과 다릅니다.
> 화자별 전사본이 필요하면 `V2M_DIARIZE=true`로 바꾸세요.

| 변수 | 코드 기본값 | 설명 |
|---|---|---|
| `V2M_HF_TOKEN` | (빈 값) | 화자분리(pyannote)용 HuggingFace 토큰 |
| `V2M_WHISPER_MODEL` | `medium` | `tiny`·`base`·`small`·`medium`·`large-v3`·`large-v3-turbo` |
| `V2M_LANGUAGE` | `ko` | 회의에 언어가 지정되지 않았을 때 쓰는 기본 언어(`auto`/빈 값 = 자동 감지) |
| `V2M_DIARIZE` | `true` | `false` = 빠른 모드(정렬·화자분리 생략, ~10배 빠름) |
| `V2M_CHUNK_MINUTES` | `60` | 빠른 모드에서 이보다 긴 녹음을 나눠 전사(`0` = 끔, 화자분리 시 무시) |
| `V2M_BATCH_SIZE` | `16` | WhisperX 배치 크기(클수록 빠르지만 메모리 증가) |
| `V2M_CPU_THREADS` | `0` | CPU 스레드 수(`0` = 전체 코어) |
| `V2M_SUPPRESS_NUMERALS` | `true` | 숫자를 한글로 표기(숫자 오인식 감소) |
| `V2M_INITIAL_PROMPT` | (빈 값) | 전문 용어·이름 등 디코더 힌트 문장 |
| `V2M_VAD_METHOD` | `silero` | 음성 구간 검출 방식(`pyannote`는 더 느림, 품질 차이 없음) |
| `V2M_FFMPEG_DIR` | (빈 값) | ffmpeg가 PATH에 없을 때 `ffmpeg.exe`가 있는 폴더 |
| `V2M_HOST` / `V2M_PORT` | `127.0.0.1` / `8000` | 서버 주소 |
| `V2M_DATA_DIR` | `%LOCALAPPDATA%\v2m` | 데이터 저장 위치 |

> ⚠️ **인증이 없으므로 `V2M_HOST`는 `127.0.0.1`로 유지하세요.** `0.0.0.0`으로 바꾸면 삭제 API를 포함한
> 모든 기능이 같은 네트워크 전체에 노출됩니다.

## 데이터 위치

DB·오디오·모델·로그는 설치 폴더가 아닌 **`%LOCALAPPDATA%\v2m\`** 아래에 저장됩니다
(`V2M_DATA_DIR`로 변경 가능). mp3는 처음 요청할 때 변환되어 원본 옆에 `{id}.mp3`로 캐시되고,
녹음을 삭제하면 함께 지워집니다.

## 정형화(회의록) 단계

앱은 LLM을 호출하지 않습니다. 전사본 화면에서 **"전사본 + 프롬프트 복사"**를 누르면
한국어 회의록 지시 프롬프트와 화자별 전사본(+입력한 회의 정보)이 클립보드에 복사됩니다 —
**claude.ai 데스크탑 앱에 붙여넣으면** 요약·핵심 논의·결정사항·액션아이템으로 정형화됩니다.
(앱이 claude.ai를 자동으로 열지는 않습니다. 긴 회의는 입력 한도 안내가 표시됩니다.)

## 라이선스

[LICENSE](LICENSE) 참고.
