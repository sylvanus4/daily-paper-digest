# daily-paper-digest

A daily **5-minute digest of trending AI/ML papers** for busy engineers.
It fetches the day's trending papers, writes a plain-language Markdown digest,
and (optionally) uses an LLM to explain *why each paper matters* — with graceful
degradation to the paper's own abstract when no API key is present.

Vendor-neutral, local-first, no required API keys, MIT-licensed.

> **Not affiliated with arXiv or Hugging Face.** Summaries are AI-assisted and
> may contain errors — always verify against the linked source.

---

## English

### Who it's for
AI/ML engineers and researchers who want the signal of the day's important
papers without doom-scrolling — a scannable digest they can read with coffee.

### What it does
1. Fetches trending papers from the **Hugging Face daily papers API**
   (`https://huggingface.co/api/daily_papers`).
2. Falls back to the **arXiv Atom API** if Hugging Face is unreachable, then to a
   **bundled sample** so it always produces output — even fully offline.
3. Selects the top *N* papers (default 5) by upvotes.
4. For each paper:
   - **With `ANTHROPIC_API_KEY` set** → asks Claude for a 3-sentence "why it
     matters" plus 3 takeaway bullets.
   - **Without a key** → degrades to the paper's abstract (truncated) + metadata.
5. Writes `docs/YYYY-MM-DD.md` and updates `docs/index.md` + `docs/README.md`.

### Content from papers, format owned by code
The Markdown structure — headers, ordering, metadata lines, links, disclaimers —
is **fixed and generated deterministically by `digest.py`**. The language model
only fills the prose ("why it matters" + bullets). This keeps every digest
consistent regardless of model or mood, and means a missing/failed API call
never corrupts the layout — it just falls back to the abstract.

### Run it locally
No third-party packages are strictly required — `digest.py` runs on the Python
standard library alone (Python 3.9+).

```bash
# Degraded mode (no key, no network needed):
python3 digest.py --top 5 --offline

# Live mode (fetches Hugging Face / arXiv):
python3 digest.py --top 5

# With AI-assisted summaries:
export ANTHROPIC_API_KEY="sk-ant-..."
python3 digest.py --top 5

# Pick a date / output dir:
python3 digest.py --date 2026-07-10 --top 5 --out docs
```

`requirements.txt` lists `requests` for convenience/parity with common setups,
but the tool itself uses only stdlib, so `pip install` is optional.

### Host it free on GitHub Pages
1. Push this repo to GitHub.
2. **Settings → Pages → Build and deployment → Source: Deploy from a branch**,
   branch `main`, folder `/docs`.
3. The included **`daily.yml`** GitHub Action runs at ~23:00 UTC, generates a new
   `docs/YYYY-MM-DD.md`, and commits it. It's also manually runnable via
   **Actions → daily-digest → Run workflow**.
4. To enable AI summaries in CI, add a repo secret named `ANTHROPIC_API_KEY`
   (**Settings → Secrets and variables → Actions**). Without it, CI still
   produces a valid degraded digest.

Your digest archive is then served at `https://<user>.github.io/daily-paper-digest/`.

### Bring your own TTS (optional, not included)
The digest is plain Markdown, so if you want an audio version you can pipe it
through any local text-to-speech tool of your choice. **No audio/TTS is bundled
with this project** — that's left entirely to you.

---

## 한국어

### 누구를 위한 도구인가
매일 쏟아지는 AI/ML 논문을 다 볼 시간은 없지만 흐름은 놓치고 싶지 않은 엔지니어·
연구자를 위한 **하루 5분 트렌딩 논문 다이제스트**입니다.

### 무엇을 하나
1. **Hugging Face daily papers API**에서 그날의 트렌딩 논문을 가져옵니다.
2. 접속이 안 되면 **arXiv Atom API**로, 그것도 안 되면 **동봉된 샘플**로 폴백해
   완전 오프라인에서도 항상 결과를 만듭니다.
3. upvote 기준 상위 N개(기본 5개)를 고릅니다.
4. 각 논문에 대해:
   - `ANTHROPIC_API_KEY`가 있으면 → Claude가 "왜 중요한가" 3문장 + 핵심 3가지를 작성.
   - 키가 없으면 → 논문 초록(요약본) + 메타데이터로 자연스럽게 강등.
5. `docs/YYYY-MM-DD.md`를 쓰고 `docs/index.md`·`docs/README.md`를 갱신합니다.

### 내용은 논문에서, 포맷은 코드가 소유
헤더·정렬·메타데이터·링크·면책 문구 등 마크다운 골격은 `digest.py`가 **결정론적으로
고정**합니다. LLM은 산문(왜 중요한가 + 불릿)만 채웁니다. 덕분에 모델이 바뀌어도
포맷이 흔들리지 않고, API 호출이 실패해도 레이아웃이 깨지지 않고 초록으로 폴백됩니다.

### 로컬 실행
서드파티 패키지 없이 파이썬 표준 라이브러리만으로 동작합니다(Python 3.9+).

```bash
python3 digest.py --top 5 --offline        # 키·네트워크 없이 강등 모드
python3 digest.py --top 5                   # 실시간(HF/arXiv) 수집
export ANTHROPIC_API_KEY="sk-ant-..."       # AI 요약 켜기
python3 digest.py --top 5
```

### GitHub Pages로 무료 호스팅
1. 이 저장소를 GitHub에 푸시.
2. **Settings → Pages → Source: Deploy from a branch**, `main` 브랜치의 `/docs` 폴더.
3. 동봉된 `daily.yml` 액션이 매일 ~23:00 UTC에 새 다이제스트를 만들어 커밋합니다.
   **Actions** 탭에서 수동 실행도 가능합니다.
4. CI에서 AI 요약을 켜려면 저장소 시크릿 `ANTHROPIC_API_KEY`를 추가하세요. 없어도
   강등 모드로 유효한 다이제스트가 생성됩니다.

### TTS는 직접 (선택, 미포함)
결과물이 순수 마크다운이라 원하는 로컬 TTS 도구로 오디오를 만들 수 있습니다. **오디오/
TTS는 이 프로젝트에 포함되어 있지 않습니다.**

---

## License

MIT — see [LICENSE](LICENSE). Do what you like; no warranty. The papers and their
abstracts belong to their respective authors and platforms.
