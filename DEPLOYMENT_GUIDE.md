# InferenceChain Desktop Application - Deployment Guide

**Build Date:** April 6, 2026  
**Application Version:** 0.1.0  
**Python Sidecar Status:** ✓ Built with PyInstaller  
**React Frontend Status:** ✓ Built with React Scripts  
**Electron Application Status:** ✓ Packaged and Ready  

---

## Deployment Package Contents

The complete InferenceChain desktop application is located in:  
```
desktop/dist/win-unpacked/
```

**Package Size:** ~1575 MB

### Directory Structure

```
desktop/dist/win-unpacked/
├── InferenceChain.exe          # Main application executable
├── run.bat                      # Simple launcher script (optional)
├── resources/
│   ├── app/                     # React frontend bundle
│   ├── app.asar                 # Electron app archive
│   └── ...                      # Other Electron resources
├── sidecar/                     # Python FastAPI sidecar
│   ├── sidecar.exe             # Standalone Python executable
│   ├── PyQt5/                  # UI libraries
│   └── ...                     # All dependencies (torch, fastapi, etc.)
├── node_modules/               # Node.js dependencies
├── locales/                    # Electron localization
├── *.dll                       # Windows system libraries
└── [other Electron files]
```

---

## Getting Started

### Run the Application

**Option 1: Direct Execution**  
Double-click: `desktop/dist/win-unpacked/InferenceChain.exe`

**Option 2: Using Launcher Script**  
Double-click: `desktop/dist/win-unpacked/run.bat`

### Expected Startup Behavior

1. **Electron App Window Opens** (~2-3 seconds)
   - React dashboard loads on the main thread
   - FastAPI sidecar launches in background

2. **Sidecar Initializes** (~5-10 seconds)
   - Python environment loads
   - FastAPI server starts on `127.0.0.1:47291`
   - OOD profile registry initializes

3. **Application Ready**
   - Dashboard UI becomes interactive
   - API endpoints available at `http://127.0.0.1:47291/docs`

### System Requirements

- **OS:** Windows 10 / Windows 11 (64-bit)
- **RAM:** 4 GB minimum (8+ GB recommended for model training)
- **Disk:** 2 GB free space (plus ~5-10 GB for CIFAR-10 dataset if training)
- **GPU:** Optional (NVIDIA GPU with CUDA support recommended)

---

## Features Included

### Core Components

✓ **OOD Profiling & Scoring**
- Shared frozen ViT-B/16 encoder
- Class-conditional Mahalanobis distance profiles
- Query-time knowledge scoring with optional Ed25519 signing
- Endpoints: `/ood/fit`, `/ood/score`

✓ **Consensus & Quorum**
- S-BFT quorum selection with multi-factor weighting
- Stake × knowledge × reliability weighted sampling (Efraimidis-Spirakis)
- Deterministic quorum reproducibility via SHA-256 seeding

✓ **Anti-Gaming Infrastructure**
- Per-node reliability tracking with EMA updates (dual pathways)
- Deterministic hidden challenges (15% rate)
- Challenge-driven penalties and rewards
- Challenge record registry with REST API

✓ **Model Management**
- Proof of Model (PoM) verification
- CIFAR-10 model training & registration
- Multiple architecture support (ResNet, DenseNet, MobileNetV2, etc.)

✓ **Blockchain & Transactions**
- Local SQLite persistence (WAL mode)
- PoS consensus layer
- QoI validation rounds
- Transaction signing with secp256k1

✓ **Frontend Dashboard**
- React-based UI
- Network explorer
- Validator performance monitoring
- Consensus round tracking
- Real-time WebSocket updates

---

## Configuration & Customization

### Environment Variables (for advanced users)

```powershell
# Set custom sidecar port (default: 47291)
$env:SIDECAR_PORT=47292

# Enable debug logging
$env:DEBUG=1

# Python log level
$env:LOG_LEVEL=DEBUG
```

### Modifying Sidecar Settings

The Python sidecar runs on `127.0.0.1:47291` by default. No configuration file is needed for basic usage.

For advanced configuration, modify `desktop/sidecar/main.py` before rebuilding.

---

## OOD & Reliability Features (New in v0.1.0)

### Knowledge Scoring Endpoint

**POST** `/ood/score`

Request:
```json
{
  "profile": { /* OOD profile dict */ },
  "image_b64": "base64-encoded-image",
  "energy_score": 0.75,
  "node_private_key_hex": "optional-ed25519-key"
}
```

Response:
```json
{
  "knowledge_score": 0.85,
  "distance": 2.34,
  "embed_score": 0.88,
  "energy_score_norm": 0.75,
  "predicted_cluster": 3,
  "signature_hex": "optional-ed25519-signature"
}
```

### Challenge Records API

**GET** `/inference/challenges/recent?limit=25`

Returns recent challenge round records with per-node honesty, OOD scores, and knowledge scores for auditing.

### Reliability Registry

Per-node tracking with:
- EMA score: ∈ [0.05, 1.5]
- Breakdown: rounds, honest_rounds, byzantine_rounds, challenge_rounds, challenge_penalties
- Regular round updates: α=0.2
- Challenge round updates: α=0.45 (stronger signal)

---

## Troubleshooting

### Application Won't Start

1. **Check Windows Defender/Antivirus**  
   - Application is unsigned; you may need to allow execution
   - Add `desktop/dist/win-unpacked/` to antivirus exceptions

2. **Port Conflict**  
   - Sidecar uses port 47291
   - Check: `netstat -an | findstr :47291`
   - If in use, modify and rebuild

3. **Insufficient Disk Space**  
   - Min 2 GB required
   - CIFAR-10 dataset adds ~5 GB

### Sidecar Won't Initialize

- Check file permissions in `desktop/dist/win-unpacked/`
- Ensure Python path is correct (PyInstaller should handle this)
- Try running as Administrator

### Dashboard UI Unresponsive

- Sidecar may be initializing (PyTorch model loading ~10-30 seconds)
- Wait 30-60 seconds before reporting
- Check browser console for errors (F12)

---

## Deployment to Other Machines

### Method 1: Direct Copy (Simplest)

1. Copy entire `desktop/dist/win-unpacked/` folder to target machine
2. Double-click `InferenceChain.exe` or `run.bat`
3. Done!

**Note:** Application is portable; no installer needed. ~1.6 GB disk space required.

### Method 2: Create NSIS Installer (Optional)

If you need a traditional installer:

```powershell
cd desktop
npm install -g nsis # or download from https://nsis.sourceforge.io/
npm run build:electron  # May require code signing certificate
```

---

## Building a Modified Version

### Prerequisites

```bash
cd c:\Users\dpapa\InferenceChain

# Create Python venv (if needed)
python -m venv .venv
.venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
pip install pyinstaller

# Install Node packages
cd desktop
npm install
```

### Full Rebuild

```powershell
cd desktop
npm run build
```

This runs:
1. `npm run build:sidecar` - PyInstaller for Python sidecar
2. `npm run build:react` - React production build
3. `npm run build:electron` - Electron packaging

Output: `desktop/dist/win-unpacked/` (and `*.exe` files if code signing succeeds)

---

## Documentation Updates (April 6, 2026)

### Added to WHITEPAPER.md

- **Section 6.8:** Node Reliability Tracking (EMA, dual update pathways)
- **Section 6.9:** Deterministic Hidden Challenges (15% rate, challenge records)
- **Section 6.10:** Multi-Factor Weighted Quorum Selection (stake × K × R weighting)
- **Section 12 (Updated):** REST API with new `/ood/score`, `/ood/fit`, `/inference/challenges/recent` endpoints
- **Section 15 (Updated):** Implementation Status listing new features as Complete

### Added Sidecar Endpoints

| Endpoint | Purpose |
|----------|---------|
| `POST /ood/fit` | Train OOD profile on dataset |
| `POST /ood/score` | Query knowledge score K(x) for image |
| `GET /inference/challenges/recent` | View challenge audit trail |

---

## Support & Issues

For technical support or to report issues:

1. Check troubleshooting section above
2. Review application logs in `%APPDATA%\InferenceChain\logs/` (if implemented)
3. Check browser console: F12 → Console tab
4. Review API docs: `http://127.0.0.1:47291/docs` (Swagger UI)

---

## What's New in This Build

**Reliability & Anti-Gaming**
- ✓ Per-node reliability tracking with EMA scoring
- ✓ Deterministic hidden challenges at 15% rate
- ✓ Knowledge-weighted penalty system for dishonest nodes
- ✓ Challenge record registry for transparent auditing

**Enhanced Quorum Selection**
- ✓ Multi-factor weighting: stake × knowledge × reliability
- ✓ Efraimidis-Spirakis algorithm for fair weighted sampling
- ✓ Deterministic seeding for reproducibility

**OOD Improvements**
- ✓ Query-time knowledge scoring endpoint
- ✓ Optional Ed25519 signing for score verification
- ✓ Shared frozen ViT-B/16 encoder across network

**Documentation**
- ✓ Whitepaper updated with new sections and features
- ✓ REST API extended with new endpoints
- ✓ Implementation status updated

---

**Deployment Ready:** April 6, 2026  
**Next Steps:** Follow "Getting Started" section above to launch the application.
