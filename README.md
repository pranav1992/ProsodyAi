# AutoAce AI — Voice Tone & Background Noise Dashboard

Hybrid pipeline (deterministic acoustic analysis + self-hosted transcription +
lightweight LLM classification) for the AutoAce technical trial, with a hosted
batch-upload dashboard.

See [MEMO.md](MEMO.md) for architecture and rationale, [VALIDATION.md](VALIDATION.md)
for accuracy/F1/confusion-matrix results, [COST.md](COST.md) and [LATENCY.md](LATENCY.md)
for the cost/latency analysis required by the brief.

## Architecture

```
audio file
   |
   +--> acoustic_features.py  (librosa + webrtcvad, deterministic)
   |        -> background_noise_present/severity, audio_quality,
   |           speaker_overlap_present, long_silence_present
   |
   +--> transcribe.py  (faster-whisper, self-hosted, no per-minute API cost)
            |
            +--> classify.py  (OpenAI gpt-4o-mini, text-only)
                     -> emotional_tone, emotional_intensity,
                        background_noise_type, confidence
```

Only the transcript and a small numeric feature summary are ever sent to
OpenAI — raw audio never leaves the backend. See MEMO.md for why this
split was chosen over sending raw audio to an audio-native model.

## Repo layout

```
backend/     FastAPI service: pipeline, batch processing, auth, REST API
frontend/    Next.js dashboard: login, batch upload, results, download
scripts/     (in backend/) leave-one-call-out validation script
docker-compose.yml   local dev: postgres + backend + frontend
render.yaml           one-shot Render deployment config
```

## Local development

Requires Docker, or Python 3.11 + [uv](https://docs.astral.sh/uv/) + Node 20 + `ffmpeg` installed locally.

### With Docker (recommended)

```bash
cp backend/.env.example backend/.env      # fill in OPENAI_API_KEY
export OPENAI_API_KEY=sk-...
docker compose up --build
```

- Frontend: http://localhost:3000
- Backend API: http://localhost:8000
- Login with `ADMIN_EMAIL` / `ADMIN_PASSWORD` from `backend/.env` (defaults:
  `admin@autoace.ai` / `changeme123` — **change these before deploying**).

### Without Docker

```bash
# backend
cd backend
uv sync                # creates .venv and installs pinned deps from uv.lock
brew install ffmpeg    # or apt-get install ffmpeg
cp .env.example .env   # fill in OPENAI_API_KEY; DATABASE_URL can stay sqlite for local use
uv run uvicorn app.main:app --reload

# frontend, in a second terminal
cd frontend
npm install
cp .env.example .env.local
npm run dev
```

## Running validation against the labeled calls

```bash
cd backend
uv run python scripts/evaluate.py path/to/labeled_calls_dir
```

`labeled_calls_dir` must contain the audio files plus a `labels.csv` with
`name` and `result_json` columns (ground truth), matching the batch-upload
format described in the brief. This prints per-field accuracy, macro F1 and
a confusion matrix for `emotional_tone`, and per-file latency — the numbers
that back VALIDATION.md and LATENCY.md.

## Batch upload format (dashboard)

```
evaluation_batch.zip
├── call_001.wav
├── call_002.mp3
├── call_003.wav
└── labels.csv          # name,result_json  (result_json empty/omitted for unlabeled hidden set)
```

Upload the zip from the dashboard after logging in. The dashboard validates
the manifest, reports unmatched/missing files, processes each valid clip
in the background, and shows live per-file progress. Results are
downloadable as CSV or JSON once complete; individual file failures don't
block the rest of the batch.

## Deployment (Render)

1. Push this repo to GitHub.
2. In Render, create a new Blueprint from `render.yaml`.
3. Set the `OPENAI_API_KEY`, `ADMIN_EMAIL`, `ADMIN_PASSWORD` secrets when prompted
   (marked `sync: false` in render.yaml so Render asks for them instead of
   committing them to the repo).
4. Deploy. Render builds both Dockerfiles and provisions the Postgres database
   automatically. Update `CORS_ORIGINS` on the backend service and
   `NEXT_PUBLIC_API_URL` build arg on the frontend once you know the final
   `*.onrender.com` URLs (or custom domains).

Whisper transcription runs on CPU by default (`WHISPER_DEVICE=cpu`,
`WHISPER_MODEL_SIZE=base`) — no GPU instance required, which keeps hosting
cost predictable. See LATENCY.md for measured throughput on this configuration.

## Known limitations / next steps

See MEMO.md § Failure modes and next steps.
