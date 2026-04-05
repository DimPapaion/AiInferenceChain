const { contextBridge, ipcRenderer } = require('electron');

/**
 * Expose a minimal, typed API surface to the renderer.
 * The renderer never has access to Node.js or Electron APIs directly —
 * everything goes through this bridge.
 */
contextBridge.exposeInMainWorld('electronAPI', {
  // Sidecar
  getSidecarPort: () => ipcRenderer.invoke('sidecar:port'),

  // File system (user-initiated only)
  openFileDialog: (opts) => ipcRenderer.invoke('dialog:openFile', opts),
  readFile: (filePath) => ipcRenderer.invoke('fs:readFile', filePath),

  // App paths
  getDataPath: () => ipcRenderer.invoke('app:dataPath'),
});
