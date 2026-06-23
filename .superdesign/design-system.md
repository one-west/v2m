# V2M Design System — Dark Modern (Linear/Vercel 풍)

## Product context
V2M (Voice to Minutes): 로컬·$0 회의록 도구. 브라우저에서 회의를 녹음 → 로컬 WhisperX로 화자분리 전사 →
전사본 + 회의 정보를 복사해 **claude.ai 데스크탑 앱**에 붙여넣어 정형화된 회의록을 얻는다.
단일 사용자·localhost·한국어 UI.

### Screens
1. **홈** — `새 회의` 폼(제목·일자·시간·장소·참석자·안건/목적) + 녹음 버튼/타이머 + `회의 목록`
   (행: 제목 · 일자 · 참석 N명 · 상태 뱃지[대기/전사중/완료/실패] · 삭제).
2. **상세** — 편집 가능한 `회의 정보` 폼 + `회의록 만들기` 액션(전사본+프롬프트 **복사**[claude.ai 데스크탑앱에
   붙여넣기, 자동 열기 없음] + Markdown/TXT 내보내기) + 화자별·타임스탬프 `전사본`.

## Visual direction
Near-black, high-contrast, engineered "dev-tool" 미학. 단일 인디고/바이올렛 액센트를 CTA·포커스·상태에 절제해서 사용.
헤어라인 보더, 은은한 글로우, 라운드 카드, 상단 앰비언트 그라데이션. 차분하고 프리미엄. 장난스럽지 않음.

## Color tokens (CSS variables)
```
--bg:            #0a0a0c;
--panel:         #0e0f13;
--surface:       rgba(255,255,255,.025);
--surface-2:     rgba(255,255,255,.045);
--border:        rgba(255,255,255,.08);
--border-strong: rgba(255,255,255,.14);
--text:    #ededf2;
--muted:   rgba(237,237,242,.62);
--faint:   rgba(237,237,242,.40);
--accent:        #6366f1;
--accent-bright: #818cf8;
--accent-deep:   #4338ca;
--accent-soft:   rgba(99,102,241,.16);
--ok:   #34d399;  --ok-soft:   rgba(52,211,153,.14);
--info: #818cf8;  --info-soft: rgba(129,140,248,.14);
--warn: #fbbf24;  --warn-soft: rgba(251,191,36,.14);
--err:  #f87171;  --err-soft:  rgba(248,113,113,.14);
```
- `::selection` 은 accent-soft 배경.
- Ambient glow (fixed, behind content):
  `radial-gradient(620px 320px at 50% -8%, rgba(99,102,241,.20), transparent 70%)` +
  `radial-gradient(500px 300px at 90% 0%, rgba(139,92,246,.12), transparent 70%)`.
- Glow util: `0 0 0 1px rgba(99,102,241,.35), 0 18px 60px -24px rgba(99,102,241,.55)` — primary CTA·로고·녹음 강조에만.

## Typography
- **단일 폰트로 통일**: 모든 텍스트(제목·본문·라벨·메타·타임스탬프·뱃지·숫자)에
  `"Pretendard","Inter",system-ui,"Apple SD Gothic Neo","Malgun Gothic",sans-serif` 하나만 사용. **별도 모노스페이스 폰트 없음.**
  디스플레이는 tight(letter-spacing -0.02em). 라벨/메타는 굵기·크기·뮤트색으로만 위계 구분.
- 위계: H1 ~22px/700, 카드 H2 ~16px/650, 본문 15px, 라벨 13px, 메타 11~12px.
- 숫자(타이머·타임스탬프)는 같은 폰트에 `font-variant-numeric: tabular-nums`만 적용.

## Spacing / radius / motion
- Spacing: 4 / 8 / 12 / 16 / 20 / 24 / 32.
- Radius: 카드 14px, 인풋·버튼 9px, pill/뱃지 999px.
- 컨테이너: 단일 컬럼, max-width 840px, 좌우 패딩 20~32px.
- Motion: 0.15s ease hover/focus. 녹음 점 pulse 1.4s. 과한 모션 금지.

## Components
- **Top bar**: sticky, backdrop blur, 반투명 ink 배경, 하단 헤어라인. 좌측 그라데이션 로고 타일(V, glow) + 워드마크 `V2M` + 뮤트 태그라인.
- **Card**: surface 배경, 1px border, radius 14, 패딩 20~24. 제목 H2 + 인라인 상태 뱃지.
- **Form**: 2열 그리드(제목·일자 / 시간·장소), 참석자·안건은 전체 너비. 라벨(mute,13px) + 인풋.
  인풋: 어두운 필드(rgba white .03), 1px border, focus 시 accent border + 3px accent-soft ring. textarea resize-y. date 는 color-scheme: dark.
- **Buttons**: primary = indigo→violet 그라데이션 + glow, hover brightness↑·translateY(-1px); secondary = 투명 + border-strong; danger-ghost = 투명 + err 텍스트. 라운드 9px(주요)/pill(부가). 아이콘+라벨.
- **Recorder bar**: 펄스 점(err 글로우) + 큰 타이머(tabular,700) + 시작/정지 버튼(시작=accent, 정지=red 그라데이션) + 힌트(mute).
- **Status badge**: pill, soft 배경 + 컬러 텍스트 + 같은 색 .25 보더. done=ok, transcribing=info, recorded=warn, failed=err. 라벨 한국어.
- **List row**: 헤어라인 카드 행, 제목(600) + 서브(mute: `일자 · 참석 N명`) + 상태 뱃지 + 삭제 아이콘버튼(hover err-soft). hover 시 surface-2.
- **Transcript**: 어두운 안쪽 패널(rgba black .25), max-height 340 스크롤. 세그먼트: 화자 칩(accent-soft, info) + 타임스탬프(faint, tabular-nums) + 본문 라인.
- **Toast**: ok-soft pill, "복사되었습니다 (N자) — claude.ai 데스크탑 앱에 붙여넣으세요".

## Hard constraints (fidelity)
- 위 팔레트·폰트·간격·컴포넌트 스타일만 사용. 새 색(핑크/네온/세리프)·폰트·그라데이션 임의 추가 금지.
- 단일 액센트(인디고/바이올렛)만. 상태색은 정의된 4색만. 모든 카피는 한국어.
