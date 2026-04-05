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

## OOD Scoring (Knowledge Self-Assessment)

InferenceChain uses **Out-of-Distribution (OOD) scoring** to bias quorum selection toward
DNN nodes that are most familiar with a given image domain. This is the *Knowledge
Self-Assessment (KSA)* mechanism from the paper.

### How it works

When a `NODE_ADMITTED` transaction is committed (a DNN node passes Proof-of-Model), the
`ConsensusEngine` automatically runs an async calibration pass in the background:

1. Loads the node's PyTorch model
2. Builds class-conditional feature statistics from the CIFAR-10 test set
3. Stores a `NodeOODProfile` in the in-process `OODProfileRegistry`

For each subsequent inference request, `select_quorum()` queries the registry, ranks
all eligible nodes by their OOD score for the specific image, and builds a *top-2K
shortlist*. The final quorum is sampled deterministically from that shortlist — nodes
with lower scores (more in-distribution) are preferred but unpredictably selected.

### Scorers

| Class | Description | Requires |
|---|---|---|
| `MahalanobisOODScorer` | **Default.** Penultimate-layer features. Calibrated on CIFAR-10 test set at admission. | One calibration forward-pass batch |
| `EnergyOODScorer` | Lightweight fallback. Raw logits only, zero calibration. | Just the model |
| `LikelihoodRegretScorer` | Paper-exact VAE-based. Most accurate, most expensive. | Separate VAE training pass |

### Testing OOD calibration manually

```python
from core.consensus.ood import MahalanobisOODScorer, NodeOODProfile, get_ood_registry
from models.model_registry import ModelRegistry

model   = ModelRegistry("models/weights").load("resnet20", device="cpu")
scorer  = MahalanobisOODScorer()
# calibrate against CIFAR-10 test set (needs data/cifar-10-batches-py/)
import torchvision, torchvision.transforms as T, torch
loader = torch.utils.data.DataLoader(
    torchvision.datasets.CIFAR10("./data", train=False,
        transform=T.Compose([T.ToTensor(),
            T.Normalize((0.4914,0.4822,0.4465),(0.2023,0.1994,0.2010))])),
    batch_size=64, shuffle=False,
)
scorer.calibrate(model, loader)
profile = NodeOODProfile(node_id="<your_node_id>", scorer=scorer, model=model)
get_ood_registry().register(profile)
```

---

## LLM Orchestration Layer

The LLM layer is an **optional** coordination service that runs _above_ the blockchain.
It never touches consensus, key management, or quorum selection directly.

### Capabilities (POST /llm/*)

| Endpoint | Purpose |
|---|---|
| `POST /llm/route` | Recommend `model_hint` + `dataset_id` for an image description |
| `POST /llm/analyse` | Scan validator reputations for anomalous behaviour, suggest PoM re-challenges |
| `POST /llm/decompose` | Break a complex multi-image task into parallel sub-requests |
| `POST /llm/explain` | Natural-language Q&A about the current chain state |

### Starting a node with LLM support

**Local Ollama (recommended for testnet):**
```bash
# 1. Install and start Ollama  https://ollama.com/download
ollama pull llama3.2

# 2. Start the InferenceChain node
python node_runner.py --llm-provider ollama --llm-model llama3.2
```

**OpenAI:**
```bash
export OPENAI_API_KEY=sk-...
python node_runner.py --llm-provider openai --llm-model gpt-4o-mini
```

**Mock (deterministic, no network — for tests/CI):**
```bash
python node_runner.py --llm-provider mock
```

**Disabled (default):**  
Omit `--llm-provider` entirely. The `/llm/*` endpoints return HTTP 503 with instructions.

### Example requests

```bash
# Routing recommendation
curl -X POST http://localhost:8000/llm/route \
  -H "Content-Type: application/json" \
  -d '{"image_description": "street view house numbers in San Francisco"}'

# Validator anomaly scan
curl -X POST http://localhost:8000/llm/analyse -H "Content-Type: application/json" -d '{}'

# Decompose a complex task
curl -X POST http://localhost:8000/llm/decompose \
  -H "Content-Type: application/json" \
  -d '{"task_description": "Classify 10 street scenes and 10 fashion items separately"}'

# Chain state Q&A
curl -X POST http://localhost:8000/llm/explain \
  -H "Content-Type: application/json" \
  -d '{"question": "Which validator has the highest reputation score?"}'
```

### Security note

The LLM provider credentials (`--openai-key` / `OPENAI_API_KEY`) are never stored on-chain
and are not gossiped to peers. Each node operator configures (or omits) their own provider
independently. The consensus layer remains fully deterministic regardless of LLM availability.

---

## Common Issues

- Port already in use when starting testnet:
  - stop previous node processes or free ports before re-running scripts
- Frontend build errors on CI from warnings:
  - `CI=false` is already applied in `vercel.json`
- Missing frontend manifest files on deployment:
  - ensure `frontend/package.json` and `frontend/package-lock.json` are committed

## License

Use and distribution terms are governed by the repository owner.
