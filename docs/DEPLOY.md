# Deploy

Status: **not deployed yet.** The image builds and runs locally; the Fly.io deploy is waiting on
a logged-in `flyctl` on the pipeline machine (see "Blocked" below). Live URL, plan and cost
figure are filled in after the first deploy.

## What is deployed

1 Docker image: the code, `config/`, `DESIGN.md` (rendered by the About page) and 1 serve bundle
baked into `/app/bundle`. No database, no object storage. The app opens the bundle's Parquet
files read-only with DuckDB at boot (memory_limit 512 MB). There is no authentication: the link
is the share mechanism, so anyone with the URL can read the ranking and post feedback.

Feedback (`POST /api/feedback`, the 2 buttons on an account page) is appended to
`/app/bundle/feedback.jsonl` inside the running machine. The file lives in the machine's
filesystem and is lost on redeploy; copy it out before deploying a new bundle
(`fly ssh console -C "cat /app/bundle/feedback.jsonl" > feedback-<bundle>.jsonl`).

## 1. Export the bundle

```
uv run sis export
# bundle 20261102-1135-1.1.0 -> C:\Users\NIRANJAN VSKS\sis_data\serve\20261102-1135-1.1.0
# accounts 487133 evidence 4549051 signals 3189714 events 0
# size_mb 156.6
```

The bundle stays under `$SIS_DATA/serve/<version>/`, outside the repo (OneDrive).

## 2. Build and run locally

The bundle is passed as a named build context, so it never has to be copied into the repo:

```
docker build --build-context bundle="$SIS_DATA/serve/<version>" -t sis .
docker run -p 8000:8000 sis
```

Measured on 2026-11-02 with bundle 20261102-1135-1.1.0 (image 1.48 GB): `/api/health` 200 in
15 ms; `/api/accounts?segment=untouched&page_size=5` 200, 5 items sorted by priority, 209 ms
cold and 150 ms warm; default page (50 items) 212 ms; account detail 615 ms; feedback POST 200
and `/app/bundle/feedback.jsonl` grew to 1 line.

## 3. Deploy to Fly.io

`fly.toml` describes 1 machine, shared-cpu-1x, 1 GB, internal port 8000, health check
`/api/health`, always on (`min_machines_running = 1`). `flyctl` cannot pass a named build
context, so the image is built locally and pushed to Fly's registry:

```
fly auth login
fly apps create <app>            # "sis" is the PHASE_CONFIG name; Fly app names are global
fly auth docker
docker tag sis registry.fly.io/<app>:<bundle_version>
docker push registry.fly.io/<app>:<bundle_version>
fly deploy --app <app> --image registry.fly.io/<app>:<bundle_version>
```

Then the live smoke (cards/P5.md step 9): `/api/health` 200, `/api/accounts?segment=untouched`
50 items, 1 detail page, 1 feedback POST, and `fly ssh console -C "wc -l /app/bundle/feedback.jsonl"`.

## Blocked

`flyctl` is not installed on the pipeline machine and there is no Fly token, so the deploy needs
the account owner to run `fly auth login` once. Fallback in the card: Render free web service
(spins down when idle), which also needs an account.

## Logfire

`logfire.configure(send_to_logfire="if-token-present")`: with `LOGFIRE_TOKEN` set (as a Fly
secret: `fly secrets set LOGFIRE_TOKEN=...`) spans go to Logfire; without it they print to the
console, which `fly logs` shows. Every request is a span (`instrument_fastapi`) and every DuckDB
query is a child span `query` with its SQL.
