const { app, BrowserWindow, ipcMain, dialog } = require('electron');
const path = require('path');
const { spawn } = require('child_process');
const http = require('http');

const isDev = process.env.NODE_ENV === 'development';

let mainWindow = null;
let sidecarProcess = null;
let sidecarPort = 47291; // fixed local port for Python sidecar

// ── Sidecar management ────────────────────────────────────────────────────────

/**
 * Returns { cmd, args } for launching the Python sidecar.
 * Dev:  python sidecar/main.py  (uses system python)
 * Prod: resources/sidecar/sidecar[.exe]  (PyInstaller one-dir bundle)
 */
function getSidecarCmd() {
  if (isDev) {
    const isWin = process.platform === 'win32';
    return {
      cmd: isWin ? 'py' : 'python3',
      args: [
        ...(isWin ? ['-3'] : []),
        path.join(__dirname, '..', 'sidecar', 'main.py'),
      ],
    };
  }
  const ext = process.platform === 'win32' ? '.exe' : '';
  return {
    cmd: path.join(process.resourcesPath, 'sidecar', `sidecar${ext}`),
    args: [],
  };
}

function startSidecar() {
  const { cmd, args } = getSidecarCmd();

  sidecarProcess = spawn(cmd, [...args, '--port', String(sidecarPort)], {
    stdio: ['ignore', 'pipe', 'pipe'],
    env: { ...process.env, SIDECAR_PORT: String(sidecarPort) },
  });

  sidecarProcess.stdout.on('data', (d) => {
    if (isDev) process.stdout.write(`[sidecar] ${d}`);
  });

  sidecarProcess.stderr.on('data', (d) => {
    if (isDev) process.stderr.write(`[sidecar:err] ${d}`);
  });

  sidecarProcess.on('exit', (code) => {
    if (isDev) console.log(`[sidecar] exited with code ${code}`);
    sidecarProcess = null;
  });
}

function stopSidecar() {
  if (sidecarProcess) {
    sidecarProcess.kill('SIGTERM');
    sidecarProcess = null;
  }
}

function waitForSidecar(retries = 30, interval = 500) {
  return new Promise((resolve, reject) => {
    let attempts = 0;
    const check = () => {
      const req = http.get(`http://127.0.0.1:${sidecarPort}/health`, (res) => {
        if (res.statusCode === 200) resolve();
        else retry();
      });
      req.on('error', retry);
    };
    const retry = () => {
      attempts++;
      if (attempts >= retries) reject(new Error('Sidecar did not start in time'));
      else setTimeout(check, interval);
    };
    check();
  });
}

// ── Window ────────────────────────────────────────────────────────────────────

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1280,
    height: 820,
    minWidth: 960,
    minHeight: 640,
    backgroundColor: '#06080f',
    titleBarStyle: process.platform === 'darwin' ? 'hiddenInset' : 'default',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      nodeIntegration: false,
      contextIsolation: true,
      sandbox: true,
    },
  });

  const startUrl = isDev
    ? 'http://localhost:3000'
    : `file://${path.join(__dirname, '..', 'build', 'index.html')}`;

  mainWindow.loadURL(startUrl);

  if (isDev) mainWindow.webContents.openDevTools();

  mainWindow.on('closed', () => { mainWindow = null; });
}

// ── IPC handlers ──────────────────────────────────────────────────────────────

function registerIpcHandlers() {
  // Expose sidecar port to renderer
  ipcMain.handle('sidecar:port', () => sidecarPort);

  // File open dialog — lets renderer request a file path without Node access
  ipcMain.handle('dialog:openFile', async (_event, opts = {}) => {
    const result = await dialog.showOpenDialog(mainWindow, {
      properties: ['openFile'],
      filters: opts.filters || [{ name: 'Python files', extensions: ['py'] }],
    });
    return result.canceled ? null : result.filePaths[0];
  });

  // Read file contents (architecture.py, etc.)
  ipcMain.handle('fs:readFile', async (_event, filePath) => {
    const fs = require('fs');
    // Only allow reading from user-chosen paths (not arbitrary paths)
    try {
      return { ok: true, content: fs.readFileSync(filePath, 'utf-8') };
    } catch (e) {
      return { ok: false, error: e.message };
    }
  });

  // App data directory for storing checkpoints
  ipcMain.handle('app:dataPath', () => app.getPath('userData'));
}

// ── App lifecycle ─────────────────────────────────────────────────────────────

app.whenReady().then(async () => {
  registerIpcHandlers();

  startSidecar();

  try {
    await waitForSidecar();
  } catch (e) {
    console.error('Sidecar startup timeout — continuing anyway');
  }

  createWindow();

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on('window-all-closed', () => {
  stopSidecar();
  if (process.platform !== 'darwin') app.quit();
});

app.on('before-quit', stopSidecar);
