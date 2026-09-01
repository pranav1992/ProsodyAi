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
- Login with the `ADMIN_EMAIL` / `ADMIN_PASSWORD` values set in `backend/.env`.
  Local-dev-only defaults live in `app/config.py` if you don't set them —
  **do not rely on those defaults beyond local dev; set real values in
  `.env` before deploying** (the EC2 pilot path already generates random
  ones automatically, see Deployment below).

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

The three labeled production calls are confidential (brief §5) and are
**not** committed to this repo — `backend/eval_data/` is gitignored.

1. Download the labeled calls + `labels.csv` from the source provided by
   AutoAce (e.g. the shared Drive folder) to a local folder.
2. Unzip if needed — `evaluate.py` reads loose files from a directory, not
   a zip (the zip format is only for the dashboard's `/batches` upload).
3. Place the audio files and `labels.csv` directly (unzipped, no
   subfolders) into `backend/eval_data/labeled_calls/`, e.g.:
   ```bash
   mkdir -p backend/eval_data/labeled_calls
   mv ~/Downloads/call_*.ogg ~/Downloads/labels.csv backend/eval_data/labeled_calls/
   ```
   Watch for a browser download renaming the manifest to `labels (1).csv`
   or similar — it must be named exactly `labels.csv` for the script to
   find it (`directory.glob("*.csv")` picks up whatever CSV is there, so
   make sure there's only one).
4. Run the script:
   ```bash
   cd backend
   uv run python scripts/evaluate.py eval_data/labeled_calls
   ```

This prints per-field accuracy, macro F1 and a confusion matrix for
`emotional_tone`, per-file latency, and measured `gpt-4o-mini`
classification cost (from real OpenAI API usage) — the numbers that back
VALIDATION.md, LATENCY.md, and COST.md.

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
single public entry point on port 80. Port 80 is public and the
backend/frontend container ports (8000/3000) are bound to loopback only, so
the database is never exposed regardless of the SSH posture below.

**SSH (port 22) is open to all IPs (`0.0.0.0/0`), not restricted to a
single IP as `provision-ec2.sh` sets up initially.** This was changed so
`.github/workflows/deploy.yml` (the "Deploy to EC2" action) can SSH in —
GitHub Actions' hosted runners come from large, rotating IP ranges with no
fixed address to allowlist, so a single-IP security group rule blocks CI
deploys entirely. Key-based auth is still required to actually log in;
this only widens who can *attempt* a connection, not who can authenticate.
The more correct fix — a self-hosted Actions runner on the instance itself,
polling GitHub outbound instead of accepting inbound SSH — removes this
exposure entirely and is a real next step, not done here under pilot
time constraints.

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
instance, not the most scalable one — see the scaling plan below for what
changes and when.

## Scaling plan

The current architecture is deliberately sized for a single pilot: one
EC2 instance, in-process background tasks, local disk storage. None of
that is wrong for a pilot, but none of it scales past one instance either.
This is staged by what actually becomes the bottleneck first, not a
rewrite-everything plan — per LATENCY.md, transcription is ~85% of
processing time, so that's the first thing to scale, not the API tier.

**Baseline concurrency safety (already in place, not deferred):** on a
`t3.medium` (2 vCPU, 4GB RAM), uploads used to be buffered fully into
memory before touching disk, uploads had no concurrency limit at all, and
batch processing had no concurrency limit either — a handful of large
uploads or several batches landing at once could OOM the instance or
thrash the 2 vCPUs against each other. All three are fixed now:

- `save_upload_stream()` (`app/services/storage.py`) writes uploads to
  disk one chunk at a time regardless of size.
- `upload_batch()` (`app/routes/batches.py`) is capped by an
  `asyncio.Semaphore(MAX_CONCURRENT_UPLOADS)` (default 4) — bounds how
  many uploads can be streaming/extracting to disk *at the exact same
  instant*, which the per-IP rate limit alone can't do: `3/hour` throttles
  one IP hammering the endpoint over time, but says nothing about 20
  *different* users' requests all landing in the same second. Requests
  beyond the cap simply wait their turn (nginx's `proxy_read_timeout` is
  300s, generous headroom for a short queue).
- `process_batch()` (`app/services/batch_processor.py`) is capped
  separately by a `threading.Semaphore(MAX_CONCURRENT_BATCHES)` (default
  2) — this is a distinct cap from uploads, since processing
  (CPU-bound transcription) and uploading (I/O-bound streaming) compete
  for different resources. Batches beyond this cap wait in `"pending"`,
  which the dashboard already renders correctly.

Both semaphore types matter: `asyncio.Semaphore` for the upload route
(runs on the event loop) vs. `threading.Semaphore` for batch processing
(runs on a background thread via `BackgroundTasks` → anyio's threadpool) —
mixing them up wouldn't coordinate correctly across the two contexts.

| Trigger | What's scaled | Change |
|---|---|---|
| Batch concurrency exceeds what `MAX_CONCURRENT_BATCHES` and one worker process should hold | Audio processing | Move off in-process `BackgroundTasks` onto a real queue (Celery/RQ + Redis, or SQS) with a separate worker pool, so multiple `faster-whisper` inferences run in parallel instead of being capped to a small fixed number on one instance (see MEMO.md next steps #3). |
| Worker pool needs to grow/shrink with queue depth | Transcription throughput | Autoscaling worker pool (ECS Fargate or an EC2 ASG) instead of a fixed instance — scales roughly linearly with worker count since transcription is CPU-bound and embarrassingly parallel across files. |
| API/dashboard traffic outgrows one instance, or the single EC2 instance becomes a reliability concern | Request-serving tier | FastAPI + Next.js containers are already stateless — put them behind a load balancer, run 2+ replicas. No code change needed; this is the cheapest scaling step since nothing here holds session state locally. |
| Storage becomes a single point of failure, or multiple app/worker instances need to share uploaded audio | Audio storage | Swap `STORAGE_DIR` (local Docker volume, single-instance-only) for S3 + presigned URLs. Also removes the current constraint that only one instance can ever see uploaded files. |
| Uptime/backup guarantees matter beyond a pilot | Database | Self-hosted Postgres container → managed RDS (multi-AZ), for automated backups/failover instead of a container restart being the only recovery path. |
| A second environment (staging) needs to stay in sync with prod | Infra-as-code | Terraform instead of the current shell-script provisioning (`deploy/provision-ec2.sh`), which is fine for one hand-run environment but doesn't scale to keeping N environments consistent. |

**Cost implication:** every row above adds infrastructure cost, which
pushes back against the $0.003/minute ceiling (COST.md) — the current
~7x headroom absorbs some of this, but scaling decisions should be
re-checked against COST.md's ceiling as they're made, not assumed to stay
under budget. GPU-backed transcription in particular would be a much
bigger cost jump than horizontally scaling CPU workers, so exhaust the
CPU-worker-pool option first if latency at scale becomes the binding
constraint.

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
