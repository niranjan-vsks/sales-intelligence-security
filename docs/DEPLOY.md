# Deploy

**Live URL: https://sis-niranjan.fly.dev/** (deployed 2026-11-03, bundle 20261102-1135-1.1.0,
image `registry.fly.io/sis-niranjan:20261102-1135-1.1.0-2`).

Host: Fly.io, app `sis-niranjan`, 1 machine shared-cpu-1x with 1 GB RAM in fra, always on.
Cost: **7.73 USD a month** for that machine started in fra (6.70 USD in the cheapest regions,
iad and ewr), from https://docs.fly.io/about/pricing on 2026-11-03. Shared IPv4 and registry
image storage are free; outbound data transfer is extra and not measured.

## What is deployed

1 Docker image: the code, `config/`, `DESIGN.md` (rendered by the About page) and 1 serve bundle
baked into `/app/bundle`. No database, no object storage. The app opens the bundle's Parquet
files read-only with DuckDB at boot (memory_limit 512 MB). There is no authentication: the link
is the share mechanism, so anyone with the URL can read the ranking and post feedback.

Feedback (`POST /api/feedback`, the 2 buttons on an account page) is appended to
`/app/bundle/feedback.jsonl` inside the running machine. The file lives in the machine's
filesystem and is lost on redeploy; copy it out before deploying a new image
(`flyctl ssh console --app sis-niranjan -C "cat /app/bundle/feedback.jsonl" > feedback-<bundle>.jsonl`).

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
flyctl auth login
flyctl apps create sis-niranjan   # once; Fly app names are global, so not "sis"
flyctl auth docker
docker tag sis registry.fly.io/sis-niranjan:<tag>
docker push registry.fly.io/sis-niranjan:<tag>
flyctl deploy --app sis-niranjan --image registry.fly.io/sis-niranjan:<tag> --ha=false
```

On this Windows machine the binary is `C:/Users/NIRANJAN VSKS/.fly/bin/flyctl.exe`, called
`flyctl` (not `fly`). `--ha=false` keeps 1 machine; Fly otherwise starts 2 for a new app.

The first deploy (tag `20261102-1135-1.1.0`) served every page with an `http://` stylesheet
link: Fly terminates TLS at its proxy and uvicorn did not trust the forwarded scheme, so the
browser blocked the CSS as mixed content. The image now runs uvicorn with `--proxy-headers
--forwarded-allow-ips *`, redeployed as tag `20261102-1135-1.1.0-2`.

## 4. Live smoke, 2026-11-03 (cards/P5.md step 9)

Measured from the pipeline machine (Europe) against https://sis-niranjan.fly.dev with a small
httpx script, after the second deploy:

| request | result | time |
|---|---|---|
| `/api/health`, first request | 200, bundle_version 20261102-1135-1.1.0, n_accounts 487,133 | 233 ms |
| `/api/accounts?segment=untouched&page_size=5` | 200, 5 items by priority (wide.ad.jp 92.2 first) | 273 ms, then 261 ms warm |
| `/api/accounts?segment=untouched` | 200, 50 items | 478 ms |
| `/api/accounts/<id>` | 200, 15 signals, 57 evidence rows | 461 ms |
| `/`, `/accounts/<id>`, `/about`, `/api/stats` | 200 each | 262 to 440 ms |
| `POST /api/feedback` | 200 | |

`flyctl ssh console --app sis-niranjan -C "wc -l /app/bundle/feedback.jsonl"` printed 2: 1 line
from the smoke POST and 1 from clicking Mark prospect in a browser on the live account page.
Both are test entries. The browser walk on the live URL (accounts table, htmx paging, detail
page, feedback button, About page) showed the stylesheet loading and no console errors.
`flyctl status` showed 1 machine started, health check 1 of 1 passing.

## Logfire

`logfire.configure(send_to_logfire="if-token-present")`: with `LOGFIRE_TOKEN` set (as a Fly
secret: `flyctl secrets set LOGFIRE_TOKEN=...`) spans go to Logfire; without it they print to
the console. No token is set on the deployed app, so tracing is console only: every request is
a span (`instrument_fastapi`) and every DuckDB query a child span `query`, visible in
`flyctl logs --app sis-niranjan`.
