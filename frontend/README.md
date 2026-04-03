# InferenceChain Dashboard - Frontend Setup Guide

## Overview

The InferenceChain Dashboard is a real-time web interface for managing validators, models, and monitoring consensus rounds in a local InferenceChain node.

**Features:**
- 👥 Validator Registration & Management
- 📚 Model Upload & Registry
- 🔄 Real-time Consensus Monitoring via WebSocket
- 📊 Live Statistics & Performance Metrics
- 🎨 Responsive Design with Modern UI

## Prerequisites

- Node.js 16+ and npm 8+
- Backend InferenceChain API running on `http://localhost:8000`

## Installation

### 1. Install Dependencies

```bash
cd frontend
npm install
```

### 2. Configure Environment Variables

Copy `.env.example` to `.env.local` and adjust URLs if needed:

```bash
cp .env.example .env.local
```

The default configuration assumes:
- Backend API: `http://localhost:8000`
- WebSocket: `ws://localhost:8000`

For production, update `.env.production.local`:
```env
REACT_APP_API_URL=https://your-domain.com
REACT_APP_WS_URL=wss://your-domain.com
```

## Development Server

Start the development server:

```bash
npm start
```

The dashboard will open at `http://localhost:3000`

**In parallel**, ensure the InferenceChain backend is running:

```bash
# From project root
python -m core.runner --port 8000
```

## Build for Production

Create an optimized production build:

```bash
npm run build
```

The build artifacts will be in the `build/` directory, ready to be deployed.

## Project Structure

```
frontend/
├── public/                 # Static HTML and manifest
│   ├── index.html         # Entry point
│   └── manifest.json      # PWA configuration
│
├── src/
│   ├── components/        # React components
│   │   ├── ValidatorDashboard.jsx
│   │   ├── ValidatorDashboard.css
│   │   ├── ModelManagement.jsx
│   │   ├── ModelManagement.css
│   │   ├── ConsensusMonitor.jsx
│   │   └── ConsensusMonitor.css
│   │
│   ├── api/
│   │   └── client.js      # API client with all endpoints
│   │
│   ├── App.jsx            # Main app component
│   ├── App.css            # Global styling
│   ├── index.jsx          # React entry point
│   └── index.css          # Global CSS reset
│
├── .env.example           # Environment template
├── .env.local             # Local environment (git-ignored)
├── .env.production.local  # Production environment (git-ignored)
├── .gitignore             # Git ignore rules
├── package.json           # Dependencies and scripts
└── README.md              # This file
```

## Component Overview

### ValidatorDashboard (`components/ValidatorDashboard.jsx`)

Manage validator nodes with:
- **Registration Form**: Register new validators with minimum 32.0 IC stake
- **Validator List**: Filter by status (all/active/pending/inactive/slashed)
- **Stake Confirmation**: Complete pending registrations
- **Live Updates**: Auto-refreshes every 5 seconds

### ModelManagement (`components/ModelManagement.jsx`)

Upload and track ML models:
- **Upload Form**: Submit models with framework, shapes, constraints
- **Model Gallery**: Browse by state (approved/validating/draft/rejected)
- **Validation History**: Inspect validation checks and results
- **Performance Stats**: Track accuracy and latency metrics

### ConsensusMonitor (`components/ConsensusMonitor.jsx`)

Real-time blockchain monitoring:
- **Live Connection**: WebSocket streaming of consensus rounds
- **Round Display**: Current round #, phase, participants
- **Event Log**: Last 50 consensus events with timestamps
- **Statistics**: Count by event type (rounds, validators, models)

## API Endpoints

The dashboard communicates with the backend via:

### Validator Endpoints
- `POST /validators/register` - Register new validator
- `POST /validators/{id}/confirm-stake` - Confirm stake
- `GET /validators` - List validators (with filters)
- `GET /validators/{id}` - Get validator details
- `POST /validators/{id}/heartbeat` - Send heartbeat
- `GET /validators/active/list` - Get active validators

### Model Endpoints
- `POST /models/upload` - Upload model file
- `GET /models` - List models (with state filters)
- `GET /models/{id}` - Get model details
- `GET /models/{id}/validations` - Get validation history

### Statistics
- `GET /stats` - Dashboard statistics
- `GET /health` - Health check

### WebSocket Streams
- `WS /ws/consensus-rounds` - Stream consensus rounds
- `WS /ws/validators` - Stream validator activity
- `WS /ws/models` - Stream model validation events

## Styling System

The dashboard uses CSS3 with:
- **Color Scheme**: Purple gradient (#667eea → #764ba2)
- **Animations**: Smooth transitions and entrance effects
- **Responsive**: Mobile-first design with breakpoints at 768px, 480px
- **Components**: Cards, forms, badges, modals, event logs

## Troubleshooting

### "Failed to fetch from API"
- Ensure backend is running: `python -m core.runner --port 8000`
- Check `REACT_APP_API_URL` in `.env.local` matches backend address
- Verify CORS is enabled in backend

### WebSocket Connection Fails
- Ensure backend has WebSocket routes registered
- Check `REACT_APP_WS_URL` in `.env.local` is correct
- Verify firewall allows WebSocket connections

### Build Fails
```bash
# Clear cache and reinstall
rm -rf node_modules package-lock.json
npm install
npm run build
```

## Development Tips

### Hot Reload
Changes to source files automatically reload in the browser during `npm start`

### Debug Mode
Check browser DevTools (F12) for:
- React DevTools browser extension
- Network tab for API calls
- Console for errors/warnings

### Performance
- React.StrictMode highlights unused state updates
- CSS animations use GPU acceleration (transform/opacity)
- API client batches requests and handles caching

## Deployment

### Docker

Build a Docker image for the frontend:

```dockerfile
FROM node:18-alpine AS builder
WORKDIR /app
COPY package*.json ./
RUN npm install
COPY . .
RUN npm run build

FROM node:18-alpine
WORKDIR /app
RUN npm install -g serve
COPY --from=builder /app/build ./build
EXPOSE 3000
CMD ["serve", "-s", "build", "-l", "3000"]
```

### Nginx (Reverse Proxy)

Serve the built dashboard with nginx:

```nginx
server {
    listen 80;
    server_name _;
    
    root /usr/share/nginx/html;
    index index.html;
    
    location / {
        try_files $uri /index.html;
    }
    
    location /api {
        proxy_pass http://backend:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
    
    location /ws {
        proxy_pass http://backend:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "Upgrade";
    }
}
```

## Contributing

When adding new features:
1. Create components in `src/components/`
2. Add styles in matching `.css` files
3. Update `.env.example` for any new env vars
4. Document API requirements in their components

## License

Part of the InferenceChain project.
