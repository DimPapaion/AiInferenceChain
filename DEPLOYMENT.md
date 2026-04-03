# InferenceChain Dashboard - Deployment Guide

## Quick Start (Local Development)

### 1. Install Dependencies

```bash
# Backend (already installed)
# Frontend
cd frontend
npm install
```

### 2. Set Up Environment Files

```bash
# Create .env.local in frontend/
cp frontend/.env.example frontend/.env.local
```

### 3. Start Backend API

From project root:
```bash
python -m core.runner --port 8000
```

Expected output:
```
INFO:     Uvicorn running on http://0.0.0.0:8000
INFO:     Application startup complete
```

The API will be available at:
- REST API: `http://localhost:8000`
- Swagger Docs: `http://localhost:8000/docs`
- Dashboard: `http://localhost:8000/ui` (after frontend build)

### 4. Start Frontend Development Server

In a new terminal:
```bash
cd frontend
npm start
```

Expected output:
```
Compiled successfully!

You can now view inference-chain-dashboard in the browser.

  Local:            http://localhost:3000
  On Your Network:  http://192.168.x.x:3000
```

### 5. Access the Dashboard

Open `http://localhost:3000` in your browser.

## Directory Structure

```
InferenceChain/
├── core/
│   ├── registry/              # Dashboard layers
│   │   ├── model_validator.py
│   │   ├── validator_registry.py
│   │   └── model_registry.py
│   │
│   ├── qoi/
│   │   └── consensus_stream.py  # WebSocket streaming
│   │
│   ├── api/
│   │   ├── routes/
│   │   │   ├── dashboard.py     # Dashboard API endpoints
│   │   │   └── websocket.py     # WebSocket endpoints
│   │   └── __init__.py          # FastAPI app factory
│   │
│   └── ...
│
├── frontend/                  # React dashboard
│   ├── public/                # Static files
│   ├── src/
│   │   ├── components/        # React components with CSS
│   │   ├── api/               # API client
│   │   ├── App.jsx
│   │   ├── index.jsx
│   │   └── ...
│   ├── package.json
│   ├── .env.local             # Local configuration
│   └── README.md
│
├── README.md
├── requirements.txt
└── ...
```

## Understanding the Architecture

### Backend Stack

**FastAPI Application** (`core/api/__init__.py`)
- Base URL: `http://localhost:8000`
- CORS enabled for frontend development
- WebSocket support for real-time updates
- Static file serving for frontend (at `/ui`)

**Dashboard Layer** (New in this session)

1. **Model Validator** (`core/registry/model_validator.py`)
   - Framework detection (PyTorch, TensorFlow, ONNX)
   - Input/output shape validation
   - Benchmark criteria verification
   - Extensible check pipeline

2. **Validator Registry** (`core/registry/validator_registry.py`)
   - Validator lifecycle: pending→active→inactive/slashed
   - Stake management (minimum 32.0 IC)
   - Performance tracking (models validated, blocks proposed)

3. **Model Registry** (`core/registry/model_registry.py`)
   - SQLite persistence with WAL mode
   - Version tracking for models
   - Validation history and benchmarks
   - State transitions: draft→approved→invalid

4. **Dashboard API** (`core/api/routes/dashboard.py`)
   - 12 validator endpoints
   - 4 model endpoints
   - 2 statistics endpoints
   - Pydantic validation for all requests/responses

5. **WebSocket Streaming** (`core/qoi/consensus_stream.py`)
   - ConsensusStreamManager for multi-channel broadcasts
   - Three channels: consensus_rounds, validators, models
   - Real-time event delivery to connected clients

6. **WebSocket Routes** (`core/api/routes/websocket.py`)
   - `/ws/consensus-rounds` - Stream consensus events
   - `/ws/validators` - Stream validator activity
   - `/ws/models` - Stream model validation events

### Frontend Stack

**React Application** (`frontend/src/`)

1. **App Component** (`App.jsx`)
   - Main orchestrator with tab navigation
   - Stats bar with live metrics
   - Error handling and auto-refresh
   - Tab routing between: Validators, Models, Consensus

2. **API Client** (`api/client.js`)
   - ApiClient class with 14 methods
   - Combined REST/WebSocket support
   - Error handling and automatic retries
   - FormData support for file uploads

3. **Components**

   - **ValidatorDashboard** (`components/ValidatorDashboard.jsx`)
     - Register validators with stake confirmation
     - Filter validators by status
     - Display validator metrics and lifecycle
     - Auto-refresh every 5 seconds

   - **ModelManagement** (`components/ModelManagement.jsx`)
     - Upload models with framework selection
     - View model registry with state filtering
     - Inspection of validation history
     - Performance statistics for models

   - **ConsensusMonitor** (`components/ConsensusMonitor.jsx`)
     - Real-time WebSocket connection
     - Current round and phase display
     - Event log with 50-event history
     - Connection status indicator

4. **Styling** (CSS3)
   - `App.css` - Global layout and header
   - `ValidatorDashboard.css` - Card animations, forms
   - `ModelManagement.css` - Modal dialogs, upload flows
   - `ConsensusMonitor.css` - Real-time event styling
   - Responsive design with mobile support

## Testing the Dashboard

### 1. Verify Backend Health

```bash
curl http://localhost:8000/health
```

Expected response:
```json
{"status": "ok"}
```

### 2. Register a Validator

```bash
curl -X POST http://localhost:8000/validators/register \
  -H "Content-Type: application/json" \
  -d '{
    "address": "http://localhost:8001",
    "name": "Test Validator",
    "email": "test@example.com",
    "stake": 32.0
  }'
```

### 3. Upload a Model

```bash
curl -X POST http://localhost:8000/models/upload \
  -F "metadata={...}" \
  -F "file=@model.pth"
```

### 4. Stream Consensus via WebSocket

```bash
# Using websocat or similar
websocat ws://localhost:8000/ws/consensus-rounds
```

## Configuration Files

### Environment Variables

**Frontend** (`.env.local`)
```env
REACT_APP_API_URL=http://localhost:8000      # Backend API
REACT_APP_WS_URL=ws://localhost:8000         # WebSocket endpoint
```

**Production** (`.env.production.local`)
```env
REACT_APP_API_URL=https://your-domain.com
REACT_APP_WS_URL=wss://your-domain.com
```

### Backend Configuration

Edit `core/runner.py` or use command-line arguments:
```bash
python -m core.runner --port 8000 --host 0.0.0.0
```

## Building for Production

### 1. Build Frontend

```bash
cd frontend
npm run build
```

Creates optimized bundle in `frontend/build/`

### 2. Backend Serving

The backend automatically serves the built frontend at `http://localhost:8000/ui`

### 3. Docker Deployment

**Build Backend & Frontend Image:**

```dockerfile
FROM python:3.10-slim

WORKDIR /app

# Backend dependencies
COPY requirements.txt .
RUN pip install -r requirements.txt

# Install Node for frontend build
RUN apt-get update && apt-get install -y nodejs npm

# Copy backend code
COPY core/ core/

# Copy and build frontend
COPY frontend/ frontend/
WORKDIR /app/frontend
RUN npm install && npm run build

# Copy built frontend to backend static dir
RUN mkdir -p ../core/api/static && cp -r build/* ../core/api/static/

WORKDIR /app

EXPOSE 8000

CMD ["python", "-m", "core.runner", "--host", "0.0.0.0", "--port", "8000"]
```

**Run Container:**

```bash
docker build -t inference-chain:latest .
docker run -p 8000:8000 inference-chain:latest
```

## Database & Persistence

### SQLite Database

Models use SQLite with WAL (Write-Ahead Logging) for reliability:

```bash
# Inspect database
sqlite3 data/models.db
sqlite> .tables
sqlite> SELECT * FROM models;
```

**Schema:**
- `models` - Model metadata and lifecycle
- `model_versions` - Version history
- `validations` - Validation records
- `benchmarks` - Performance metrics

### State Persistence

Validator registry exports state as JSON:
```python
state = validator_registry.export_state()
```

## Monitoring & Debugging

### Backend Logs

```bash
# Verbose logging
python -m core.runner --port 8000 --debug
```

### Frontend DevTools

1. Open browser DevTools (F12)
2. React DevTools tab
3. Network tab for API calls
4. Console for errors

### WebSocket Debugging

```bash
# Monitor WebSocket traffic in browser console
ws = new WebSocket('ws://localhost:8000/ws/consensus-rounds')
ws.onmessage = (e) => console.log(JSON.parse(e.data))
```

## Troubleshooting

### API Connection Failed
- Check backend is running: `curl http://localhost:8000/health`
- Verify `REACT_APP_API_URL` in `.env.local`
- Check CORS settings in `core/api/__init__.py`

### WebSocket Connection Failed
- Check WebSocket routes registered in `core/api/__init__.py`
- Verify correct WS URL: `ws://` for local, `wss://` for HTTPS
- Check firewall/proxy allows WebSocket upgrade

### Database Locked Error
- SQLite uses WAL mode - should be thread-safe
- If issue persists: `sqlite3 data/models.db "VACUUM;"`

### Frontend Build Fails
```bash
cd frontend
rm -rf node_modules package-lock.json
npm install
npm run build
```

## Performance Considerations

### Backend
- FastAPI with async handlers
- SQLite with connection pooling
- WebSocket broadcasts to all connected clients
- Pydantic validation on all API endpoints

### Frontend
- React hooks for efficient re-renders
- CSS animations use GPU acceleration
- Auto-refresh throttled to 10 seconds
- WebSocket auto-reconnect with 3-second backoff

## Next Steps

1. **Authentication**: Add JWT tokens for API security
2. **Metrics**: prometheus/Grafana integration
3. **Testing**: Add integration tests for frontend
4. **Monitoring**: Implement health checks and alerting
5. **Documentation**: OpenAPI/Swagger UI enhancements

## Support

For issues or questions:
1. Check browser console and backend logs
2. Verify all environment variables are set correctly
3. Ensure backend and frontend are on same protocol (HTTP or HTTPS)
4. Review API response in Network tab for actual error details
