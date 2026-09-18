# TaxonBodyMassML prediction microservice

Flask service behind the web interface at <https://taxonbodymassml.github.io>.
It answers every request with `taxonbodymassml.predict_mass()` from the released
Python package, so the website, the R package and the Python package share one
inference implementation. The package is installed from its GitHub release
wheel at image build time and the model artifacts (~0.4 GB) are downloaded from
Hugging Face during the build, so the container starts without network access.

| | |
|---|---|
| Model served | Entity Embeddings by default (`TBM_METHOD=XGBoost` switches) |
| Intervals | 90 % rank-stratified conformal intervals |
| Known species | recorded mass from the training-data dictionary, degenerate interval |
| Taxonomy with no rank in the training data | `prediction: null` plus a `warning` |
| Endpoints | `GET /health`, `POST /xgb_pred_single`, `POST /xgb_pred_multi`, `GET /` |

## Response schema

```json
{
  "taxonomy": {"kingdom": "Animalia", "...": "...", "species": "UNK"},
  "prediction": 12345.6,
  "lower_bound": 1800.2,
  "upper_bound": 84700.9,
  "confidence": 0.9,
  "source": "tbmML_genus",
  "model": "EntityEmbeddings"
}
```

Dictionary species: `lower_bound == upper_bound == prediction`, `confidence: null`,
`source` is the data-source label, `model: null`. Unrepresented taxonomy:
`prediction`, bounds and `confidence` are `null`, `source: "tbmML_UNK"`,
`model: null`, and a `warning` string is added. Batch responses are
`{"items": [...]}` in input order and always HTTP 200; malformed payloads are 400.

Request bodies: `POST /xgb_pred_single` takes one JSON object with any subset of
the keys `kingdom`, `phylum`, `class`, `order`, `family`, `genus`, `species`
(missing or unknown values are treated as `UNK`); `POST /xgb_pred_multi` takes a
bare JSON list of such objects, not an `items` wrapper.

## Local development and tests

```bash
cd regressor_microservice
python -m venv .venv && .venv/bin/pip install -r requirements.txt -e ../packages/python
.venv/bin/pytest -q tests                       # uses the package's cached artifacts
.venv/bin/python ../scripts/check_parity.py --no-r   # golden predictions, from repo root's venv if preferred
.venv/bin/gunicorn -w 1 -b 127.0.0.1:8000 'regressor:create_wsgi_app()'
```

The tests skip unless the package cache already holds the artifacts
(`python -c "import taxonbodymassml as t; t.download_model()"` fetches them).

## Container: build and smoke test

```bash
docker compose -f compose.yml -f compose.local.yml up --build -d regressor
curl -s localhost:8000/health
curl -s -X POST localhost:8000/xgb_pred_single -H 'Content-Type: application/json' \
  -d '{"kingdom":"Animalia","phylum":"Chordata","class":"Mammalia","order":"Carnivora","family":"Canidae","genus":"Canis","species":"Canis notarealwolf"}'
docker compose -f compose.yml -f compose.local.yml down
```

Before a Python package release exists for the version pinned in the
`dockerfile`, build against an earlier wheel:

```bash
docker compose build --build-arg TBM_WHEEL=https://github.com/TaxonBodyMassML/TaxonBodyMassML/releases/download/python-v0.10.0/taxonbodymassml-0.10.0-py3-none-any.whl regressor
```

Images built on an Apple-silicon Mac are `linux/arm64`; for an x86 host build
there or add `--platform linux/amd64`.

## Deployment runbook

Applies to the machine that runs the compose stack (the "host"), not to a
development machine. The stack is two containers on a private Docker network:

| Container | Image | Role |
|---|---|---|
| `regressor_api` | built from `dockerfile` | gunicorn + Flask API on port 8000, reachable only inside the compose network (`expose`, not `ports`) |
| `cloudflared` | `cloudflare/cloudflared:latest` | outbound Cloudflare tunnel that publishes `http://regressor:8000` under a public HTTPS hostname |

The website (GitHub Pages, source in `web_dev/`) calls that public hostname
directly from the visitor's browser, so the hostname written into
`web_dev/index.js` must be the one the running tunnel answers on. Nothing
listens on the host's own network interfaces and no inbound firewall rule is
needed.

The first deployment on a new host follows the same steps: step 2 is then a
no-op and step 5 always applies.

### Prerequisites (once per host)

- Docker Engine with the Compose v2 plugin: `docker compose version` must print
  `v2` or later (the compose files have no `version:` key). Enable the daemon
  at boot (`sudo systemctl enable --now docker`) so that `restart: unless-stopped`
  brings the stack back after a reboot.
- Disk: the image is about 3.2 GB and BuildKit keeps several GB of build cache.
  Allow 10 GB under `/var/lib/docker`; `docker builder prune -f` reclaims the
  cache when space runs short.
- Memory: the service uses about 320 MB at rest and while serving; 1 GB of
  free RAM is ample.
- Outbound HTTPS during the build to `github.com` (the wheel), `pypi.org`
  (Flask, gunicorn) and `huggingface.co` (the artifacts). At run time only
  `cloudflared` needs outbound access, to Cloudflare's edge; the API container
  makes no network calls.
- Build on the host itself so the image matches its CPU architecture (see the
  `--platform` note above if you must build elsewhere).
- A clone of this repository with push access if the host is where you will
  edit `web_dev/index.js` (step 5); otherwise make that edit on your
  workstation.

  ```bash
  git clone https://github.com/TaxonBodyMassML/TaxonBodyMassML.git
  cd TaxonBodyMassML/regressor_microservice
  ```

### 1. Confirm that the release you are about to deploy exists

The image installs the wheel URL pinned in `dockerfile` (`ARG TBM_WHEEL`) and
downloads the artifacts whose checksums that wheel embeds. Both are produced by
the package release process (`packages/UpdatingModelGuide.md`), never on the
host.

```bash
git pull --ff-only
grep -n '^ARG TBM_WHEEL' dockerfile                                   # the version you expect to deploy
curl -sIL -o /dev/null -w '%{http_code}\n' "$(grep -oE '^ARG TBM_WHEEL=\S+' dockerfile | cut -d= -f2-)"   # must print 200
```

`404` means the "Python package CI" workflow has not published that release
yet (or the pin is wrong): wait for the workflow, or build against the previous
wheel with `--build-arg TBM_WHEEL=...` as shown above.

### 2. Keep the running image as a rollback target

```bash
docker tag regressor_microservice-regressor:latest regressor_microservice-regressor:previous 2>/dev/null || true
```

The `|| true` covers the first deployment, when no image exists yet.

### 3. Build the new image while the old one keeps serving

```bash
docker compose build regressor
```

This takes a few minutes: dependency install, then the 0.4 GB artifact download
with checksum verification. The running containers are untouched. Failures to
expect:

| Build output | Meaning | Action |
|---|---|---|
| `ERROR: HTTP error 404 while getting https://github.com/...whl` | wheel not published, or wrong pin | step 1 |
| `RuntimeError: SHA256 mismatch for <file>` | the Hugging Face tag does not match the wheel's checksums | do not deploy; the release itself needs fixing (`scripts/publish_artifacts.py`) |
| `no space left on device` | Docker disk full | `docker builder prune -f`, `docker image prune -f`, retry |

### 4. Switch to the new image and check it

```bash
docker compose up -d
```

Compose recreates `regressor_api` from the new image (a few seconds of
downtime). It normally leaves `cloudflared` running because that service's
configuration did not change, in which case the tunnel hostname is preserved;
step 5 checks this. Then:

```bash
docker compose ps                         # regressor_api "Up ... (healthy)" within ~30 s; cloudflared "Up"
docker compose logs --tail 20 regressor   # "Model loaded successfully: method=..., taxonbodymassml X.Y.Z, artifacts X.Y.Z." and no [ERROR] lines
docker compose exec -T regressor python -c "import urllib.request; print(urllib.request.urlopen('http://localhost:8000/health').read().decode())"
```

The health line must report the `package_version` and
`model_artifact_version` you deployed, for example
`{"method":"EntityEmbeddings","model_artifact_version":"0.11.0","package_version":"0.11.0","status":"ok"}`.
The image has no `curl`; use Python inside the container as above, or the
public URL from outside (step 6). A prediction through the internal port:

```bash
docker compose exec -T regressor python -c "
import json, urllib.request
tax = {'kingdom': 'Animalia', 'phylum': 'Mollusca', 'class': 'Gastropoda', 'order': 'Neogastropoda',
       'family': 'Muricidae', 'genus': 'Nucella', 'species': 'Nucella lima'}
req = urllib.request.Request('http://localhost:8000/xgb_pred_single', json.dumps(tax).encode(),
                             {'Content-Type': 'application/json'})
print(urllib.request.urlopen(req).read().decode())"
```

Expect `"model": "EntityEmbeddings"`, `"source": "tbmML_genus"`,
`"confidence": 0.9` and a finite `prediction` bracketed by `lower_bound` and
`upper_bound`.

### 5. Point the website at the tunnel

```bash
docker compose logs cloudflared 2>&1 | grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' | tail -1
grep -n 'trycloudflare' ../web_dev/index.js
```

If the two hostnames agree, the site is already live on the new service and
you can skip to step 6. If they differ (`cloudflared` was recreated or
restarted; every start of a quick tunnel draws a new random hostname):

```bash
OLD=<hostname shown by grep>   NEW=<hostname shown by the log>
sed -i "s#https://$OLD#https://$NEW#g" ../web_dev/index.js        # macOS: sed -i '' "s#...#...#g" ...
git -C .. diff --stat web_dev/index.js                            # exactly two changed lines: /xgb_pred_single and /xgb_pred_multi
git -C .. add web_dev/index.js
git -C .. commit -m "web: point the prediction service at the new tunnel URL"
git -C .. push origin main
```

The push runs the `deploy` job of `.github/workflows/CI.yml`, which copies
`web_dev/` into the `taxonbodymassml.github.io` repository (rsync, commit,
push). GitHub Pages serves the new file within a minute or two; hard-refresh
the page to bypass the browser cache.

### 6. Verify end to end

```bash
curl -s https://<hostname>.trycloudflare.com/health
curl -s -X POST https://<hostname>.trycloudflare.com/xgb_pred_single -H 'Content-Type: application/json' \
  -d '{"kingdom":"Animalia","phylum":"Mollusca","class":"Gastropoda","order":"Neogastropoda","family":"Muricidae","genus":"Nucella","species":"Nucella lima"}'
```

Then open <https://taxonbodymassml.github.io> and try a species that is in the
training data (*Nucella ostrina*: recorded mass, no interval), one that is not
(*Nucella lima*: estimate with interval) and a small batch upload. The page
resolves names through a separate taxonomy-lookup service
(`look-up-service.onrender.com`), which is not part of this stack; if the name
lookup fails, the prediction service is not the cause.

### 7. Clean up

```bash
docker image prune -f      # removes the now-untagged old layers (about 3 GB per superseded image)
```

The `:previous` tag protects the rollback image from pruning. Remove it with
`docker rmi regressor_microservice-regressor:previous` once the new deployment
has proven itself.

### Rolling back

```bash
docker tag regressor_microservice-regressor:previous regressor_microservice-regressor:latest
docker compose up -d --no-build --force-recreate regressor
```

Only the API container is recreated, so a preserved quick-tunnel hostname stays
valid. Alternatively rebuild against an older release:
`docker compose build --build-arg TBM_WHEEL=<older wheel URL> regressor && docker compose up -d`.

### Day-to-day operation

- `docker compose ps` shows Docker's own health check (`GET /health` every 30 s,
  `healthy` / `unhealthy`). `docker compose logs -f --since 1h regressor` (or
  `cloudflared`) follows the logs: the API logs its startup and any Python
  traceback; cloudflared logs its connections and the hostname.
- `restart: unless-stopped` restarts a crashed container and starts the stack
  when the Docker daemon starts after a reboot. Any restart of `cloudflared`
  (reboot, `docker compose down`, image update) means a new quick-tunnel
  hostname and therefore step 5 again. A named tunnel (next section) removes
  this chore.
- `docker compose down` stops and removes both containers; the image stays and
  `docker compose up -d` brings the stack back.
- Serving the alternative model: set `TBM_METHOD: XGBoost` under
  `environment:` in `compose.yml` and run `docker compose up -d`. No rebuild is
  needed because both models' artifacts are in the image. `/health` reports the
  active method and every response carries it in `model`.
- Updating cloudflared: `docker compose pull cloudflared && docker compose up -d`
  (new hostname for a quick tunnel).

### Stable hostname: replace the quick tunnel with a named tunnel

Quick tunnels (`tunnel --url ...`) need no Cloudflare account, but every start
issues a new hostname and Cloudflare gives no uptime commitment for them. With
a domain on Cloudflare, a named tunnel provides a permanent hostname, so step 5
disappears from redeploys and reboots:

1. In the Cloudflare Zero Trust dashboard, under Networks → Tunnels, create a
   tunnel of type Cloudflared named, for example, `tbm-api`. Copy the connector
   token from the Docker installation command it shows (the value after
   `--token`).
2. Add a public hostname to the tunnel, for example `api.example.org`, with
   service type `HTTP` and URL `regressor:8000` (the compose service name;
   cloudflared runs on the same Docker network).
3. On the host, store the token outside git and outside the image (`.env` is
   git-ignored and listed in `.dockerignore`):

   ```bash
   printf 'TUNNEL_TOKEN=%s\n' '<token>' > .env && chmod 600 .env
   ```

4. In `compose.yml`, change the `cloudflared` service command to
   `tunnel --no-autoupdate run --token ${TUNNEL_TOKEN}`; Compose substitutes
   the value from `.env`. The `volumes:` entry is only needed for the
   credentials-file variant below and can stay. Commit this `compose.yml`
   change (the token is not in it) so later `git pull --ff-only` runs stay
   clean, then `docker compose up -d`. `docker compose logs cloudflared` should
   show "Registered tunnel connection" lines and no errors.
5. Set both URLs in `web_dev/index.js` to `https://api.example.org` once, commit
   and push. They never change again.

Cloudflare's locally managed alternative (`cloudflared tunnel create`, a
credentials JSON plus `config.yml` mounted at `/etc/cloudflared` through the
existing `volumes:` entry, command
`tunnel --no-autoupdate --config /etc/cloudflared/config.yml run`) works as
well; `./cloudflared/` is git-ignored for that purpose.

### Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Website: the prediction request fails ("Failed to fetch"); `curl https://<hostname>/health` fails too | tunnel hostname changed (cloudflared restarted), or the stack is down | `docker compose ps`; step 5 |
| Website: the name lookup fails before any prediction is requested | the separate lookup service (`look-up-service.onrender.com`) is asleep or down; its free-tier cold start takes up to a minute | retry; check the Render dashboard |
| `regressor_api` is `unhealthy` or restarts in a loop | startup exception (see `docker compose logs regressor`), typically a wheel/artifact mismatch or out-of-memory | rebuild from a consistent release; check `docker stats` and host RAM |
| `/health` reports an older `package_version` than the one built | container not recreated after the build | `docker compose up -d --force-recreate regressor` |
| Build fails with `HTTP error 404` on the wheel | release not published yet, or wrong pin | step 1 |
| Build fails with `SHA256 mismatch` | Hugging Face artifacts and wheel checksums disagree | do not deploy; fix the release |
| `[ERROR] Control server error: ... Permission denied: '/home/appuser'` in the gunicorn log | image built from a `dockerfile` older than 2026-09-18 (service user had no home directory) | `git pull` and rebuild; serving is unaffected meanwhile |
| Requests hang for a few seconds right after a start | checksum verification of the 0.4 GB artifacts and the model warm-up run before the worker accepts connections | wait for "Model loaded successfully" |

## Files

| File | Purpose |
|---|---|
| `regressor.py` | Flask app; normalises the taxonomy, calls the package, maps the result to the response schema |
| `requirements.txt` | Flask, flask-cors, gunicorn; the package itself (with numpy, pandas, xgboost) comes from the wheel pinned in the `dockerfile` |
| `dockerfile`, `compose.yml`, `compose.local.yml` | image, production stack (API + Cloudflare tunnel), local port mapping |
| `tests/test_app.py` | endpoint tests incl. the golden-prediction check |
| `sliced_model/` | git-ignored pickle bundle written by `predictive_models/decision_tree.py` and read by `scripts/export_artifacts.py`; not used by the service |
