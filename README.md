# InferenceChain

InferenceChain is a local-first blockchain + inference network prototype.

It combines:
- A Python node runtime (FastAPI + P2P + consensus loop)
- A DNN inference flow with QoI-style validation components
- A React dashboard frontend for explorer, validators, inference, network, and whitepaper views

## Repository Layout

- `core/` - blockchain, consensus, networking, API, registry, and serving logic
- `node/` - node roles and identity helpers
- `qoi/` - quality, proposer, and state-machine logic
- `models/` - model architectures and weight registry support
- `frontend/` - React dashboard app
- `scripts/` - helper scripts (`start_testnet.bat`, `start_testnet.sh`)
- `tests/` - unit/integration tests
- `node_runner.py` - single node entry point

## Prerequisites

- Python 3.10+
- Node.js 18+ and npm
- Optional GPU + CUDA for model-related workflows

## Python Setup

```bash
python -m venv .venv
# Windows
.venv\\Scripts\\activate
# Linux/macOS
source .venv/bin/activate

pip install -r requirements.txt
```

## Run a Single Node

```bash
python node_runner.py --port 8000 --db-path data/node0.db
```

Useful options:
- `--peer http://127.0.0.1:8000` to bootstrap from another node
- `--config config/testnet.yaml` to load network settings
- `--node-type dnn --model resnet20 --weights-dir models/weights` for DNN role

API docs for a node are available at:
- `http://localhost:<port>/docs`

## Run Local Testnet

Windows:
```bat
scripts\\start_testnet.bat
```

Linux/macOS:
```bash
bash scripts/start_testnet.sh
```

Default script endpoints:
- Dashboard/API gateway: `http://localhost:8010/ui/`
- Docs: `http://localhost:8010/docs`
- Additional node docs: `http://localhost:8011/docs`, `http://localhost:8012/docs`, `http://localhost:8013/docs`

## Frontend (Dashboard)

The frontend lives in `frontend/`.

Development:
```bash
cd frontend
npm install
npm start
```

Production build:
```bash
cd frontend
npm run build
```

## Tests

Run Python tests from repo root:

```bash
pytest -q
```

## Vercel Deployment Notes

This repo includes `vercel.json` configured for a Create React App build.

Current build settings in `vercel.json`:
- `buildCommand`: `npm install && CI=false npm run build`
- `outputDirectory`: `build`
- `installCommand`: `echo skip`

For Vercel project settings, use:
- Root Directory: `frontend`
- Let `vercel.json` control build/install/output commands

## Common Issues

- Port already in use when starting testnet:
  - stop previous node processes or free ports before re-running scripts
- Frontend build errors on CI from warnings:
  - `CI=false` is already applied in `vercel.json`
- Missing frontend manifest files on deployment:
  - ensure `frontend/package.json` and `frontend/package-lock.json` are committed

## License

Use and distribution terms are governed by the repository owner.
