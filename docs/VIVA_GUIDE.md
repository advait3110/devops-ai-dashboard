# Viva guide: how and why the project is built this way

Each section explains one major implementation step: what it does, where the code
is, and the reasoning an examiner will ask about. Likely questions and answers
are at the end.

---

## 1. Overall architecture

**Three tiers:** React frontend → FastAPI backend → real DevOps tools.

- The browser **never** talks to Docker, Jenkins or Gemini directly. Only the backend holds
  credentials (API tokens, kubeconfig, Gemini key), so secrets never reach the browser.
- The backend uses a **service + router** pattern:
  - `app/services/*_service.py`: one class per tool. It knows how to talk to that tool and
    converts its answer into a simple, uniform dictionary.
  - `app/routers/*.py`: thin HTTP endpoints that call the services.
  - `app/state.py`: creates exactly **one** instance of each service (a simple dependency
    container), so every request shares the same metric history and alert database.
- **Configuration** (`app/config.py`) comes only from environment variables / `.env`
  (the 12-factor principle). The same code runs on a laptop, in Docker, in Kubernetes and on EC2.
- **Graceful degradation**: each service raises `IntegrationError(message, status, hint)` when
  its tool is missing or unreachable. `main.py` converts that into JSON, and the frontend shows
  the hint ("set JENKINS_URL…"). This is what allows *gradual integration* without fake data.

## 2. FastAPI and asynchronous code

- FastAPI is async (built on Starlette + asyncio). One process handles many concurrent requests
  while waiting on the network, which matters because almost everything we do is I/O: HTTP
  calls to Jenkins, GitHub, Prometheus and Gemini.
- Blocking work (psutil, `subprocess.run`, boto3) runs through `asyncio.to_thread()` so it
  never freezes the event loop.
- Pydantic models (`ChatRequest`, `AnalyzeRequest`) validate request bodies, for example by
  limiting message length. FastAPI generates the interactive documentation at `/docs` from them.
- `asyncio.gather()` runs independent checks in parallel (all integration statuses at once),
  and `asyncio.wait_for()` puts a timeout on each so one slow tool cannot block the others.

## 3. Background tasks (lifespan)

`main.py` → `lifespan()` starts two asyncio tasks when the server starts and cancels them on shutdown:

| Task | Interval | Work |
|---|---|---|
| `system_loop` | 5 s | psutil sample → history → threshold alerts → Prometheus gauges → webhook flush |
| `integration_loop` | 60 s | asks each **configured** tool for problems (crashed containers, failed builds, bad pods, Prometheus alerts) |

Why not Celery/Redis? They would add two more processes and hundreds of MB of RAM. For a
single-instance dashboard, asyncio tasks are enough. That is also why the Kubernetes
Deployment runs **1 replica**: the history and alert state live in this process.

## 4. System monitoring with psutil

- `psutil` reads OS counters directly (`/proc` on Linux, Win32 APIs on Windows), so no agent is needed.
- `cpu_percent(interval=None)` is **non-blocking**: it compares against the previous call.
  The original code used `interval=1`, which made every request wait one second.
- **Rates** (network bytes/s, disk read/write bytes/s) are computed from two cumulative counters:
  `(value_now − value_before) / seconds_between`.
- **Ring buffer:** `deque(maxlen=720)` keeps exactly one hour of 5-second samples. Memory use is
  constant (~150 KB) and old samples are dropped automatically.
- Per-process CPU is divided by the core count so it reads as a share of the whole machine.

## 5. Talking to real tools without heavy SDKs

| Tool | How | Why |
|---|---|---|
| Docker | `docker` CLI on the laptop, **Engine REST API over `/var/run/docker.sock`** inside a container (httpx supports Unix sockets) | no Docker SDK needed; works on Windows and Linux |
| Kubernetes | `kubectl get --raw /api/v1/pods` on the laptop; **in-cluster** HTTPS to `kubernetes.default.svc` with the ServiceAccount token | both return the *same raw API JSON*, so one parser serves both; no 40 MB Kubernetes client |
| Jenkins | REST: `/api/json?tree=...` + API token | `tree=` asks for only the needed fields, so responses stay small |
| GitHub Actions | REST: `/repos/{o}/{r}/actions/runs`, `/jobs/{id}/logs` | official API, fine-grained token |
| Prometheus | HTTP API with PromQL (`/api/v1/query_range`) | the standard way to read Prometheus |
| Gemini | REST `generateContent` with httpx | avoids the Google SDK + gRPC stack |
| AWS | boto3, imported **lazily** only when `AWS_ENABLED=true` | no RAM cost if unused |

**Safety when running commands** (`utils/shell.py`): arguments are passed as a *list* with
`shell=False`, so input is never interpreted by a shell (no `;`, `&&`, `|` injection). Names are
validated with regular expressions so a container called `--help` cannot inject an option.
Every command has a timeout.

**Rate limits:** GitHub allows 60 unauthenticated requests per hour. `utils/cache.py` is a small
TTL cache: results are reused for 10–30 s, and concurrent callers share one upstream request (a lock).

## 6. AI integration (Gemini)

1. **Why Gemini instead of Ollama?** A local model needs several GB of disk and RAM. Gemini runs in
   Google's cloud, so the laptop only sends HTTPS requests.
2. **Grounding / retrieval-augmented prompting** (`app/context.py`): when *Use live data* is on,
   the backend collects a short text summary (CPU, memory, top processes, firing alerts,
   stopped containers, failing pods, latest builds) and puts it above the user's question.
   The system prompt tells the model to use only this data and never invent names.
   The **What is sent** button shows exactly this text, for transparency.
3. **Error analysis** (`/api/ai/analyze`): a different system prompt forces a fixed structure:
   Summary → Root cause → Fix (commands) → Prevention → Severity. Temperature 0.2 keeps the
   answer focused and repeatable.
4. **Secret redaction** (`utils/redact.py`): passwords, tokens, AWS keys, JWTs, private keys and
   credentials in URLs are masked **before** anything leaves the machine.
5. **Smart excerpt:** long logs are not cut blindly. Every error-looking line is kept with two lines
   of context, plus the last 60 lines, capped at about 14,000 characters.
6. **Conversation memory:** the frontend keeps the chat in localStorage and sends the last 12
   messages each time. The API itself is stateless.
7. **Model fallback:** Google retires model names over time (the 2.x models are already closed to new
   projects). If the configured model returns 404, the backend tries `GEMINI_FALLBACK_MODEL` and
   remembers the one that works.
8. **Error handling:** 429 (quota), invalid key, timeouts and empty answers each return a clear message.

## 7. Log analysis

- **Sources:** the app's own rotating log, whitelisted files, OS logs (`journalctl` on Linux,
  `wevtutil` Windows Event Log), `docker logs`, and Kubernetes pod logs (with automatic fallback to
  the *previous* crashed container).
- **Tail without loading the file:** `tail_file()` seeks to the end and reads backwards in 8 KB
  blocks, so a 2 GB log costs the same as a 2 KB log.
- **Level detection:** an *explicit level field* (`WARNING`, `[error]`, `level=warn`, klog `E1108`) in
  the first 100 characters wins. Keywords (`Traceback`, `failed`) are only a fallback for free text
  such as build output. This prevents `WARNING … ALERT FIRING [critical]` from being counted as critical.
- **Grouping repeated errors:** each error line is normalised by replacing timestamps, UUIDs, IPs,
  hex IDs and numbers with placeholders, then counted. `timeout after 31 ms` and `timeout after 87 ms`
  become one pattern with count 2.
- **Security:** only names listed in `LOG_FILES` can be read; arbitrary paths are rejected.

## 8. Alerting

State machine per problem key (`services/alert_service.py`):

```
OK ──(value ≥ threshold for N samples)──► FIRING ──(value < threshold − 5)──► RESOLVED
```

- **`for` window** (N = 3 samples = 15 s): a one-second spike does not alert (same idea as Prometheus `for:`).
- **Hysteresis (5 %)** prevents flapping when a value hovers around the threshold.
- **De-duplication:** a unique key (`system:cpu`, `docker:payment-worker`, `k8s:pod:ns/name`) means a
  continuing problem updates the existing alert instead of creating new ones.
- **Tool alerts** use `sync_source()`: whatever problems a tool reports now are firing, and anything
  from that source that disappeared is resolved.
- **Persistence:** SQLite (built into Python, zero setup). History survives restarts.
- **Notifications:** sidebar badge, browser Notification API (only for *new* alerts), and an optional
  Slack/Discord webhook sent once on fire and once on resolve.

## 9. Prometheus and Grafana

- **Pull model:** Prometheus scrapes `/metrics` endpoints every 15 s and stores time series.
- **node-exporter** exposes host metrics. Our backend exposes its *own* metrics with `prometheus_client`:
  request counter, latency histogram, host gauges, active alerts, AI calls. The dashboard is therefore
  itself observable (a common interview point).
- **Cardinality:** the `path` label uses the route *template* (`/api/docker/containers/{container}/logs`),
  not the real URL; otherwise every container id would create a new time series.
- **Alert rules** (`alert_rules.yml`): TargetDown, high CPU, low memory, disk almost full, API 5xx.
  The dashboard reads firing alerts via `/api/v1/alerts`.
- **Grafana provisioning:** the data source and the dashboard JSON are loaded from files at startup
  (configuration as code), so no manual clicking is needed.
- Retention is limited to 3 days to protect laptop disk space.

## 10. Containerisation (Docker, Compose, Nginx)

- **Multi-stage builds:** the frontend image builds with Node and ships only the static files in
  `nginx:alpine` (~25 MB). The backend image has a `test` stage (ruff + pytest) used by CI and a
  slim `runtime` stage.
- **Layer caching:** `requirements.txt` / `package-lock.json` are copied before the code, so a code
  change does not reinstall dependencies.
- **Security:** non-root user (uid 10001), `.dockerignore` keeps `.env` and the venv out of the image,
  and the Docker socket is mounted only where it is needed.
- **HEALTHCHECK**: Docker marks the container unhealthy if `/api/health` stops answering.
- **Nginx as reverse proxy:** `/` serves the React files, `/api/` is forwarded to the backend. The
  browser sees one origin, so no CORS is needed; gzip and long-term caching of hashed assets
  improve load time.
- **Compose profiles:** `monitoring` and `ci` start only when asked, and every service has a memory
  limit. This is how the stack fits in 8 GB.

## 11. Kubernetes

- `Deployment` (desired state + self-healing), `Service` (stable DNS name: `backend`),
  `ConfigMap` (settings), `Secret` (Gemini key), `NodePort` (reach the UI from the laptop).
- **Probes:** readiness (receive traffic only when ready) and liveness (restart if hung) both use `/api/health`.
- **Resource requests/limits** keep the pods small on Minikube.
- **RBAC with least privilege:** a ServiceAccount bound to a ClusterRole that can only *read*
  pods/logs/events/nodes/services and *patch* deployments (for the restart button).
- `imagePullPolicy: IfNotPresent` + `minikube image build`: images are built inside Minikube, so no registry is needed.
- **Rollout restart** = patching the annotation `kubectl.kubernetes.io/restartedAt`, which creates a
  new ReplicaSet and replaces pods gradually.

## 12. CI/CD

- **GitHub Actions** (`.github/workflows/ci.yml`): three jobs. *Backend* (ruff + pytest) and
  *Frontend* (eslint + build) run in parallel, then *Docker* builds both images and pushes them to
  GitHub Container Registry on `main`. It uses dependency caching and `concurrency` to cancel
  outdated runs.
- **Jenkins** (`Jenkinsfile`): declarative pipeline Checkout → Backend tests → Build images (parallel)
  → Deploy (`docker compose up`, main only) → Smoke test (`/api/health`). Tests run *inside*
  Docker build stages, so the Jenkins machine only needs the Docker CLI.
- **Closing the loop:** the dashboard monitors its own pipelines. A failing build raises an alert,
  and *Diagnose* sends the real console log to Gemini.

## 13. Infrastructure as Code (Terraform + AWS)

- **Declarative:** we describe the desired infrastructure; `terraform plan` shows the difference and
  `apply` makes it so. The **state file** records what exists, so the next plan only shows changes.
- Resources: EC2 (latest Amazon Linux 2023 AMI looked up through SSM, no hard-coded IDs), Elastic IP,
  security group (80/443 public for the website, SSH only from your IP, app port 8088 closed), IAM role +
  instance profile, SSM SecureStrings for the Gemini key, GitHub token and site password,
  encrypted/versioned private S3 bucket with lifecycle expiry, CloudWatch alarms + optional SNS e-mail.
- **Public HTTPS website:** **Caddy** runs in front of the app's Nginx. It obtains a free **Let's Encrypt**
  certificate automatically (ACME protocol: Let's Encrypt checks the server answers on port 80, then
  signs the certificate), redirects http to https, renews the certificate itself, and asks for a
  username/password (HTTP basic auth, bcrypt hash) because the dashboard can start/stop containers.
  Without a domain the URL is `https://<elastic-ip>`: Let's Encrypt has issued 6-day IP-address
  certificates since January 2026. The Elastic IP is created *before* the instance (then attached with
  `aws_eip_association`) so its address can be written into the first-boot script.
- **Real-world debugging story (good viva answer):** after the first deploy, `curl` got an instant
  `401` but the browser hung. The response header `Alt-Svc: h3=":443"` showed Caddy was inviting
  browsers to switch to **HTTP/3 (QUIC over UDP)**, and those connections stalled. Fix: Caddy serves
  `protocols h1 h2` only. Also fixed on the way: AWS rejects apostrophes in security-group
  descriptions, and a changing home IP blocks SSH until `allowed_cidr` is updated.
- **Security choices:** an IAM *role* (temporary credentials) instead of access keys on the server;
  **IMDSv2 required** (protects against SSRF credential theft) with hop limit 2 so the container can
  use the role; the secret is fetched from SSM at boot instead of being written in user-data.
- **user-data** bootstraps the server: swap, Docker, Compose, clone, secrets from SSM into `.env`, Caddy (HTTPS),
  `docker compose up`, nightly S3 backup cron.
- **CI checks the IaC:** GitHub Actions runs `terraform init -backend=false` + `terraform validate` on every push.

## 14. Frontend design decisions

- **No heavy libraries:** charts are hand-written SVG (`components/charts.jsx`) instead of a 100–400 KB
  chart library; routing uses the URL hash instead of react-router; `fetch` instead of axios; plain
  CSS with variables instead of Tailwind. Only 4 runtime dependencies remain (react, react-dom,
  react-markdown, lucide-react). The production bundle is about 115 KB gzipped.
- **`usePolling` hook:** refreshes data on an interval, **pauses when the browser tab is hidden**,
  never overlaps requests, and keeps the last good data if one refresh fails.
- **Colour means state:** green = healthy, amber = warning, coral = critical, blue = data, purple = AI actions.
- Responsive down to phone width; keyboard focus is visible; reduced-motion users get no animation.

## 15. Testing

- `tests/test_units.py`: pure logic, including the alert state machine (for-window, hysteresis,
  de-dup), log level detection, error grouping, tail-of-file, Windows Event Log parsing, secret
  redaction, Docker stream de-multiplexing, CI status mapping and Kubernetes unit conversion.
- `tests/test_api.py`: the real app in-process with `TestClient`, including the lifespan. Gemini is
  **mocked** with monkeypatch, so tests need no key or network, and one test asserts that a password
  in the question is redacted before it reaches the model.
- Run: `pytest -q`. Both CI pipelines run the same tests.

## 16. Limitations and future work (say these honestly)

- Single backend instance (state in memory + SQLite). Scaling out would need Redis/PostgreSQL and a leader for the loops.
- No user login. Add OAuth/OIDC before exposing the dashboard beyond your own IP.
- Inside Docker, psutil measures the container. Use node-exporter / windows_exporter for full host metrics.
- AI answers can be wrong. Commands are shown for a human to review, never executed automatically.
- Future: WebSockets instead of polling, Loki for centralised logs, Alertmanager for routing, Helm chart, Argo CD (GitOps).

---

## Likely viva questions

**Q: Why FastAPI and not Flask/Django?** Native async (many slow network calls at once), automatic
validation with Pydantic, auto-generated OpenAPI docs at `/docs`, and it is light.

**Q: How do you get real-time data?** Short polling (5–30 s per panel, paused in hidden tabs) against
endpoints that read pre-computed samples. It is simpler than WebSockets and cheap because the
backend samples once and serves many reads.

**Q: Difference between Prometheus and your psutil module?** psutil gives the dashboard's own
instant view with 1 hour of RAM history. Prometheus is a proper time-series database with PromQL,
longer retention, alert rules and many targets, and it also scrapes our backend.

**Q: Docker vs Kubernetes?** Docker builds and runs containers on one host. Kubernetes orchestrates
containers across nodes, keeps the desired state (self-healing, rolling updates), and provides
service discovery, probes, RBAC and resource limits.

**Q: What is CrashLoopBackOff?** The container keeps exiting. Kubernetes restarts it with an
exponentially increasing delay. The cause is in the *previous* container's log, which is why our pod
log endpoint falls back to `previous=true`.

**Q: How do you protect secrets?** `.env` is git-ignored and Docker-ignored, Kubernetes uses a Secret,
AWS uses SSM SecureString and an IAM role, tokens stay on the backend, and logs are redacted before
being sent to the AI.

**Q: How does the AI avoid making things up?** Live context is retrieved and put into the prompt, the
system prompt forbids inventing names or metrics, low temperature is used for analysis, and the
exact context is visible to the user. It can still be wrong, so a human reviews every command.

**Q: What happens if Jenkins is down?** The status check times out (independently of the others), the
Tools panel shows it red with the reason, an "integration unreachable" alert fires, and the rest of
the dashboard keeps working.

**Q: Why is the app light enough for 8 GB?** 6 Python packages, 4 frontend packages, no local LLM,
2 asyncio tasks instead of a worker queue, a ring buffer, TTL caching, polling paused in hidden tabs,
memory limits in Compose/Kubernetes, and optional profiles for the heavy tools.

**Q: What is Infrastructure as Code and why Terraform?** Infrastructure is described in versioned
text files: reviewable, repeatable and destroyable with one command. Terraform is
cloud-agnostic, shows a plan before changing anything, and tracks real resources in its state.
