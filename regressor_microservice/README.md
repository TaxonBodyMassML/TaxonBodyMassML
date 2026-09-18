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

## Deployment runbook (on the host that runs the compose stack)

1. Release the Python package first (the `dockerfile` pins its wheel URL; bump
   the `TBM_WHEEL` default with every release) and publish the matching
   Hugging Face artifact tag.
2. On the host:

   ```bash
   git pull
   cd regressor_microservice
   docker compose down
   docker compose up --build -d          # installs the wheel, downloads ~0.4 GB at build
   docker compose logs -f regressor      # wait for "Model loaded successfully"
   docker compose exec regressor python -c "import urllib.request;print(urllib.request.urlopen('http://localhost:8000/health').read())"
   docker compose logs cloudflared | grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' | tail -1
   ```

3. Paste the tunnel URL printed by the last command into the two fetch URLs in
   `web_dev/index.js`, commit and push. The repository's CI syncs `web_dev/` to
   the GitHub Pages repository.

A quick tunnel gets a new hostname on every restart, which forces step 3 each
time. With a Cloudflare-managed domain, a named tunnel gives a stable hostname:
`cloudflared tunnel create tbm-api`, put the credentials file in `./cloudflared`,
route a DNS name to it, and change the `cloudflared` service command to
`tunnel run tbm-api`.

## Files

| File | Purpose |
|---|---|
| `regressor.py` | Flask app; normalises the taxonomy, calls the package, maps the result to the response schema |
| `requirements.txt` | Flask/gunicorn/pandas; the package itself comes from the wheel pinned in the `dockerfile` |
| `dockerfile`, `compose.yml`, `compose.local.yml` | image, production stack (API + Cloudflare tunnel), local port mapping |
| `tests/test_app.py` | endpoint tests incl. the golden-prediction check |
| `sliced_model/` | git-ignored pickle bundle written by `predictive_models/decision_tree.py` and read by `scripts/export_artifacts.py`; not used by the service |
