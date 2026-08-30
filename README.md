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
deploy/               AWS EC2 pilot: provision/stop/start/destroy scripts (see below)
.github/workflows/    GitHub Actions: manually-triggered deploy to EC2
docker-compose.yml    local dev: postgres + backend + frontend
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

To stop: `Ctrl+C` if running in the foreground, or `docker compose down` from
another terminal. Either way the `db_data` and `backend_storage` named
volumes persist, so your database and any in-progress batch files survive a
restart — add `-v` to `docker compose down` to wipe them too.

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

Both `uvicorn --reload` and `npm run dev` run in the foreground — `Ctrl+C`
in each terminal stops them. Nothing else to clean up: no containers or
volumes are created in this path (the sqlite file at `backend/autoace.db`
persists on disk between runs, same as the Docker path's `db_data` volume).

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

Audio files may be `.wav`, `.mp3`, `.m4a`, `.ogg`, or `.flac` — anything else
at the archive root is ignored (see `SUPPORTED_AUDIO_EXTENSIONS` in
`backend/app/services/storage.py`). All formats are decoded uniformly via
ffmpeg before transcription.

Upload the zip from the dashboard after logging in. The dashboard validates
the manifest, reports unmatched/missing files, processes each valid clip
in the background, and shows live per-file progress. Results are
downloadable as CSV or JSON once complete; individual file failures don't
block the rest of the batch. Batches can be deleted from the dashboard
(with a confirmation prompt) once you're done with them — this permanently
removes the batch and all of its results.

## Deployment (AWS EC2 pilot)

For a single-instance pilot deployment — the cheapest/simplest option, see
the tradeoffs at the end of this section — `deploy/provision-ec2.sh` scripts
the whole thing: one `t3.medium` running all three containers via Docker Compose,
behind a fixed Elastic IP, with nginx (`deploy/nginx/prosodyai.conf`) as the
single public entry point on port 80. The security group only exposes SSH to
your current IP and port 80 to the public — the backend/frontend container
ports (8000/3000) are bound to loopback only, and the database is never
exposed.

Whisper transcription runs on CPU by default (`WHISPER_DEVICE=cpu`,
`WHISPER_MODEL_SIZE=base`) — no GPU instance required, which keeps hosting
cost predictable. See LATENCY.md for measured throughput on this configuration.

```bash
# needs: AWS CLI configured (`aws configure`) with EC2 permissions,
# and OPENAI_API_KEY either exported or already in backend/.env
./deploy/provision-ec2.sh
```

This allocates an Elastic IP, generates fresh random secrets (JWT signing
key, Postgres password, admin password), launches the instance, and prints
the app URL plus login credentials once bootstrap finishes (a few minutes —
it's installing Docker, cloning the repo, and building both images from
scratch). Resource IDs are saved to `deploy/.state` (gitignored) so the
matching teardown script knows what to remove:

```bash
./deploy/destroy-ec2.sh
```

**Deploy via GitHub Actions (manual trigger):** `.github/workflows/deploy.yml`
SSHes into the instance, runs `git pull && docker compose up -d --build`, and
resyncs the nginx config in case `deploy/nginx/prosodyai.conf` changed. It
does *not* run automatically on push — trigger it from the repo's Actions
tab (`Deploy to EC2` → `Run workflow`) whenever you actually want to ship
what's on `main`. It needs two repository secrets (Settings → Secrets and
variables → Actions), which you should set directly from your own machine
rather than routing the private key through anyone else:

- `EC2_HOST` — the instance's Elastic IP
- `EC2_SSH_KEY` — contents of the `.pem` file `provision-ec2.sh` saved to
  `~/.ssh/prosodyai-pilot.pem`

**Cost:** roughly $30–35/month for continuous `t3.medium` + 30GB gp3 +
Elastic IP. Stop the instance when not in use to only pay for storage
(~$2.74/month for the 30GB volume) plus the small idle-EIP charge:

```bash
./deploy/stop-ec2.sh    # pause billing for compute
./deploy/start-ec2.sh   # resume — same Elastic IP, containers restart on their own
```

Both read the instance ID from `deploy/.state`, same as `provision-ec2.sh`
and `destroy-ec2.sh` — nothing to look up or copy-paste. Since every service
in `docker-compose.yml` runs with `restart: unless-stopped`, no manual SSH
step is needed after starting back up.

**No TLS yet:** traffic to nginx is plain HTTP. Let's Encrypt/certbot can't
issue a cert for a bare IP, so this needs a domain pointed at the Elastic IP
before TLS termination can be added.

This is intentionally the cheapest/simplest option for a single pilot
instance, not the most scalable one. Terraform + ECS Fargate (with the
Whisper processing split into its own worker/queue instead of the current
in-process `BackgroundTasks`) would be worth the extra setup once there's a
second environment to keep in sync or a need to scale transcription
horizontally.

## Logging

The backend logs to stdout only (`app/logging_config.py`) — no file handler,
by design: containers are stateless, so a log file written inside one would
be lost on every restart/redeploy anyway. This follows the standard
12-factor approach of letting the runtime environment own log
storage/routing rather than the app.

- **Levels:** standard Python `logging` levels, `INFO` by default
  (`LOG_LEVEL` env var). `INFO` covers request lines (method/path/status/
  latency) and batch lifecycle (queued/started/per-file/completed);
  `WARNING` covers failed login attempts; `ERROR`/`exception` covers
  unhandled request errors and per-file/per-batch pipeline failures.
- **Where it lands:**
  - Local (`uvicorn`/`pytest`) — printed to the terminal only.
  - Docker (`docker compose up`) — captured by Docker's log driver;
    view with `docker compose logs -f backend`.
  - EC2 pilot — same Docker capture, written to `json-file` on the host
    (`/var/lib/docker/containers/<id>/*-json.log`).
- **Rotation:** `docker-compose.yml` caps each service's `json-file` log at
  10MB × 5 files (50MB max, oldest dropped first), so logs on the EC2
  instance can no longer grow unbounded. Shipping logs off-box (e.g.
  CloudWatch Logs) is a further step worth doing once someone needs to
  debug without SSH access.

## Known limitations / next steps

See MEMO.md § Failure modes and next steps.
