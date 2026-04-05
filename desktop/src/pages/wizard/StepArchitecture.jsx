import React, { useState } from 'react';
import '../WizardPage.css';

export default function StepArchitecture({
  apiBase, next,
  archSource, setArchSource,
  archInfo, setArchInfo,
}) {
  const [loading, setLoading] = useState(false);
  const [status, setStatus] = useState(null); // { type: 'ok'|'error', message }

  const openFile = async () => {
    if (!window.electronAPI) return;
    const filePath = await window.electronAPI.openFileDialog({
      filters: [{ name: 'Python files', extensions: ['py'] }],
    });
    if (!filePath) return;

    const result = await window.electronAPI.readFile(filePath);
    if (!result.ok) {
      setStatus({ type: 'error', message: `Could not read file: ${result.error}` });
      return;
    }
    setArchSource(result.content);
    setArchInfo(null);
    setStatus(null);
  };

  const validate = async () => {
    if (!archSource.trim()) {
      setStatus({ type: 'error', message: 'No architecture source loaded.' });
      return;
    }
    setLoading(true);
    setStatus(null);
    try {
      const resp = await fetch(`${apiBase}/validate/architecture`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ source: archSource, num_classes: 10 }),
      });
      const data = await resp.json();
      if (data.ok) {
        setArchInfo(data);
        setStatus({
          type: 'ok',
          message: `✓ ${data.model_name} — output shape ${JSON.stringify(data.output_shape)}`,
        });
      } else {
        setStatus({ type: 'error', message: data.error });
        setArchInfo(null);
      }
    } catch (e) {
      setStatus({ type: 'error', message: `Sidecar not reachable: ${e.message}` });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="wstep-card">
      <div className="wstep-kicker">Step 1 of 5</div>
      <div className="wstep-title">Upload Your Architecture</div>
      <div className="wstep-subtitle">
        Provide a <code>architecture.py</code> file that defines an{' '}
        <code>nn.Module</code> subclass. The file will be safety-checked and
        dry-run before training starts.
      </div>

      <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
        <button className="btn-ghost" onClick={openFile}>
          Browse .py file
        </button>
        <button
          className="btn-ghost"
          onClick={validate}
          disabled={!archSource || loading}
        >
          {loading ? 'Validating…' : 'Validate'}
        </button>
      </div>

      {archSource && (
        <pre
          style={{
            marginTop: 16,
            background: 'var(--bg-1)',
            border: '1px solid var(--border)',
            borderRadius: 'var(--radius-sm)',
            padding: '12px 14px',
            fontSize: 12,
            color: 'var(--text-2)',
            maxHeight: 220,
            overflowY: 'auto',
            userSelect: 'text',
          }}
        >
          {archSource.slice(0, 2000)}{archSource.length > 2000 ? '\n…' : ''}
        </pre>
      )}

      {status && (
        <div className={`wstep-status ${status.type}`}>{status.message}</div>
      )}

      <div className="wstep-actions">
        <button
          className="btn-primary"
          disabled={!archInfo}
          onClick={next}
        >
          Continue →
        </button>
      </div>
    </div>
  );
}
