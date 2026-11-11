# Deployment hand-off: TaxonBodyMassML microservice → Raspberry Pi

## What this is

TaxonBodyMassML is a research tool that predicts vertebrate body mass from taxonomy.
The website at <https://taxonbodymassml.github.io> (GitHub Pages, source in `web_dev/`)
calls a Flask prediction API that runs in Docker on a Raspberry Pi in the owner's
office. A Cloudflare quick tunnel (`cloudflared` container) publishes the API under a
public HTTPS hostname so the browser-side JavaScript can reach it.

The two relevant containers (defined in `regressor_microservice/compose.yml`):

| Container | Role |
|---|---|
| `regressor_api` | gunicorn + Flask, port 8000 (private to Docker network) |
| `cloudflared` | outbound Cloudflare quick tunnel → public `*.trycloudflare.com` URL |

## Current state

- Python package wheel pinned in `regressor_microservice/dockerfile`: **v0.14.0**
- Tunnel URL currently hardcoded in `web_dev/index.js` (lines 256 and 354):
  `https://purse-region-fresh-capabilities.trycloudflare.com`
- The Pi is 64-bit Raspberry Pi OS (aarch64/arm64) — required because xgboost has no
  32-bit wheels.
- The repo on the development Mac is at `~/Git/FracFeed/TaxonBodyMassML/`.
- **Quick tunnel note:** the `cloudflared` container issues a *new random hostname every
  time it restarts*. After deploying on the Pi, the new hostname must be substituted
  into `web_dev/index.js`, committed, and pushed to `main` so CI updates GitHub Pages.

## What still needs to happen

### Step A — On the development Mac: build and package the image

The arm64 image must be built on an Apple-silicon Mac (Docker Desktop builds
`linux/arm64` by default, matching the Pi). This cannot be done on the Pi itself
(slow, fills the SD card).

```bash
cd ~/Git/FracFeed/TaxonBodyMassML/regressor_microservice

# 1. Pull latest code
git pull --ff-only

# 2. Confirm wheel version
grep '^ARG TBM_WHEEL' dockerfile
# Expected: ARG TBM_WHEEL=https://github.com/.../taxonbodymassml-0.14.0-py3-none-any.whl

# 3. Verify the wheel URL returns 200
curl -sIL -o /dev/null -w '%{http_code}\n' \
  "$(grep -oE '^ARG TBM_WHEEL=\S+' dockerfile | cut -d= -f2-)"
# Must print 200. If 404, the GitHub release is not published yet — stop.

# 4. Keep the current image as a rollback target (no-op if none exists)
docker tag regressor_microservice-regressor:latest \
           regressor_microservice-regressor:previous 2>/dev/null || true

# 5. Build the new image (a few minutes; downloads ~0.4 GB of model artifacts)
docker compose build regressor

# 6. Confirm architecture
docker image inspect regressor_microservice-regressor:latest \
  --format '{{.Os}}/{{.Architecture}}'
# Must print: linux/arm64

# 7. Save and compress (~0.9 GB, ~20 s)
docker save regressor_microservice-regressor:latest \
  | gzip > ~/Desktop/tbm-regressor-0.14.0.tar.gz
```

Transfer `~/Desktop/tbm-regressor-0.14.0.tar.gz` to the Pi — either:
- `scp ~/Desktop/tbm-regressor-0.14.0.tar.gz pi@<PI-IP>:~`
- Or copy to a USB drive and carry it in.

### Step B — On the Raspberry Pi: deploy

SSH in or sit at the Pi. The working directory **must** be named
`regressor_microservice` — Docker Compose derives the image name from the directory
name. If you check out into a differently named directory, add `-p regressor_microservice`
to every `docker compose` command.

```bash
# 8. Confirm 64-bit OS (both must pass)
uname -m                    # must be: aarch64
dpkg --print-architecture   # must be: arm64

# 9. Clone the repo (or git pull --ff-only if already cloned)
git clone https://github.com/TaxonBodyMassML/TaxonBodyMassML.git
cd TaxonBodyMassML/regressor_microservice

# 10. Tag any existing image as rollback target (no-op on first deploy)
docker tag regressor_microservice-regressor:latest \
           regressor_microservice-regressor:previous 2>/dev/null || true

# 11. Load the transferred image
gunzip -c ~/tbm-regressor-0.14.0.tar.gz | docker load
# Should print: Loaded image: regressor_microservice-regressor:latest

# 12. Start the stack
docker compose up -d --no-build

# 13. Wait ~30 s, then verify
docker compose ps
# regressor_api must show "(healthy)"; cloudflared must show "Up"

docker compose logs --tail 20 regressor
# Look for: "Model loaded successfully: method=EntityEmbeddings, taxonbodymassml 0.14.0, ..."
# No [ERROR] lines.

docker compose exec -T regressor python -c \
  "import urllib.request; print(urllib.request.urlopen('http://localhost:8000/health').read().decode())"
# Must report package_version: "0.14.0" and status: "ok"

# 14. Get the new tunnel hostname — RECORD THIS VALUE
docker compose logs cloudflared 2>&1 \
  | grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' | tail -1
```

### Step C — Back on the development Mac: update the website

Replace the old tunnel hostname in `web_dev/index.js` with the one from step 14.
This is an operational update; it goes directly to `main` (not an issue branch).

```bash
cd ~/Git/FracFeed/TaxonBodyMassML

OLD=purse-region-fresh-capabilities.trycloudflare.com
NEW=<hostname from step 14, without https://>

sed -i '' "s#https://$OLD#https://$NEW#g" web_dev/index.js

# Confirm exactly 2 lines changed (the two prediction endpoint URLs)
git diff --stat web_dev/index.js

git add web_dev/index.js
git commit -m "web: point the prediction service at the new tunnel URL"
git push origin main
```

The push triggers `.github/workflows/CI.yml`'s `deploy` job, which rsyncs `web_dev/`
into the `taxonbodymassml.github.io` repo. GitHub Pages updates within ~2 minutes.

Hard-refresh <https://taxonbodymassml.github.io> (Cmd+Shift+R) and test:
- *Nucella ostrina* → recorded mass, no interval
- *Nucella lima* → estimate with interval
- A small batch CSV upload

### Step D — Cleanup (on the Pi, after confirming the site works)

```bash
docker image prune -f   # reclaims ~3 GB of old layers
# After ~1 day of stable service:
docker rmi regressor_microservice-regressor:previous
```

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| Wheel URL returns 404 (step 3) | GitHub release not published yet; wait and retry |
| Pi architecture is `armhf` / `armv7l` | Need 64-bit Raspberry Pi OS |
| `docker compose up --no-build` tries to build | Directory not named `regressor_microservice`; add `-p regressor_microservice` |
| Health check shows old version | `docker compose up -d --force-recreate regressor` |
| Website still fails after push | Check GitHub Actions CI completed; hard-refresh page |
| Roll back | `docker tag regressor_microservice-regressor:previous regressor_microservice-regressor:latest && docker compose up -d --no-build --force-recreate regressor` |

## Commit conventions

- Never include a `Co-Authored-By: Claude` trailer in commit messages (project rule).
- All implementation work goes on `issue-<n>-<slug>` branches. The tunnel URL update
  in step C is an operational commit and goes directly to `main`.
- Do not publish/tag/upload TaxonBodyMassML Python package releases without explicit
  owner approval.
