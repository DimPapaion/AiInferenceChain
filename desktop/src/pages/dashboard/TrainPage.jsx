import React, { useEffect, useState } from 'react';
import '../DashboardPage.css';
import WizardPage from '../WizardPage';
import { getUnlockedPriv } from '../../utils/wallet';

export default function TrainPage({ apiBase, initialMode = 'new' }) {
  const [mode, setMode] = useState(initialMode);
  const [chainOnline, setChainOnline] = useState(false);

  useEffect(() => {
    setMode(initialMode);
  }, [initialMode]);

  useEffect(() => {
    fetch(`${apiBase}/chain/status`)
      .then((r) => r.json())
      .then((d) => setChainOnline(!!d.reachable))
      .catch(() => setChainOnline(false));
  }, [apiBase]);

  return (
    <div>
      <div className="dash-panel-title">Train & Register</div>
      <div className="dash-panel-sub">Train a new model or register a pre-trained checkpoint.</div>

      <div className="train-switch">
        <button className={`dash-nav-btn-lite ${mode === 'new' ? 'active' : ''}`} onClick={() => setMode('new')}>
          Train New Model
        </button>
        <button className={`dash-nav-btn-lite ${mode === 'register' ? 'active' : ''}`} onClick={() => setMode('register')}>
          Register Existing Model
        </button>
      </div>

      {mode === 'new' ? (
        <WizardPage apiBase={apiBase} onComplete={() => localStorage.setItem('ic_onboarded', 'true')} />
      ) : (
        <RegisterTrainedModel apiBase={apiBase} chainOnline={chainOnline} />
      )}
    </div>
  );
}

function RegisterTrainedModel({ apiBase, chainOnline }) {
  const [checkpointPath, setCheckpointPath] = useState('');
  const [archHash, setArchHash] = useState('');
  const [datasetHash, setDatasetHash] = useState('');
  const [configJson, setConfigJson] = useState('{"epochs": 90, "batch_size": 128}');
  const [metricsJson, setMetricsJson] = useState('[{"epoch": 90, "val_acc": 0.91}]');
  const [privateKey, setPrivateKey] = useState('');
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState('');
  const [error, setError] = useState('');

  useEffect(() => {
    const unlocked = getUnlockedPriv();
    if (unlocked && unlocked.length === 64) setPrivateKey(unlocked);
  }, []);

  const chooseCheckpoint = async () => {
    if (!window.electronAPI?.openFileDialog) return;
    const file = await window.electronAPI.openFileDialog({
      filters: [{ name: 'Model Checkpoint', extensions: ['pt', 'pth', 'ckpt', 'bin'] }],
    });
    if (file) setCheckpointPath(file);
  };

  const submit = async () => {
    setBusy(true);
    setError('');
    setStatus('Signing manifest...');
    try {
      const config = JSON.parse(configJson || '{}');
      const metrics = JSON.parse(metricsJson || '[]');

      const signResp = await fetch(`${apiBase}/chain/sign-checkpoint`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          checkpoint_path: checkpointPath,
          arch_hash: archHash,
          dataset_hash: datasetHash,
          config,
          metrics,
          node_private_key_hex: privateKey.trim(),
        }),
      });
      const signed = await signResp.json();
      if (!signed.ok) throw new Error(signed.error || 'Sign failed');

      const endpoint = 'http://localhost:8000';
      if (chainOnline) {
        setStatus('Submitting to network...');
        const submitResp = await fetch(`${apiBase}/chain/submit`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            manifest: signed.manifest,
            signature_hex: signed.signature_hex,
            node_public_key_hex: signed.public_key_hex,
            network_endpoint: endpoint,
          }),
        });
        const result = await submitResp.json();
        if (!result.ok) throw new Error(result.error || 'Submit failed');
        setStatus('Submitted successfully.');
      } else {
        setStatus('Chain offline. Saving manifest locally...');
        const saveResp = await fetch(`${apiBase}/chain/save-manifest`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            manifest: signed.manifest,
            signature_hex: signed.signature_hex,
            node_public_key_hex: signed.public_key_hex,
            network_endpoint: endpoint,
          }),
        });
        const result = await saveResp.json();
        if (!result.ok) throw new Error(result.error || 'Save failed');
        setStatus('Saved locally. It will be submitted once the chain is online.');
      }
    } catch (e) {
      setError(e.message || 'Registration failed');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="card train-register-card">
      <div className="train-register-title">Register Existing Trained Model</div>
      <div className="train-register-sub">Use this if you already have a trained checkpoint and want to register directly.</div>

      <div className="train-form-grid">
        <label>Checkpoint Path</label>
        <div className="train-file-row">
          <input value={checkpointPath} onChange={(e) => setCheckpointPath(e.target.value)} placeholder="C:/models/model.pth" />
          <button className="btn-ghost" onClick={chooseCheckpoint}>Browse</button>
        </div>

        <label>Architecture Hash (sha256)</label>
        <input value={archHash} onChange={(e) => setArchHash(e.target.value)} placeholder="64-char hex" />

        <label>Dataset Hash (sha256)</label>
        <input value={datasetHash} onChange={(e) => setDatasetHash(e.target.value)} placeholder="64-char hex" />

        <label>Config (JSON)</label>
        <textarea rows={3} value={configJson} onChange={(e) => setConfigJson(e.target.value)} />

        <label>Metrics (JSON array)</label>
        <textarea rows={3} value={metricsJson} onChange={(e) => setMetricsJson(e.target.value)} />

        <label>Node Private Key (hex)</label>
        <input type="password" value={privateKey} onChange={(e) => setPrivateKey(e.target.value)} placeholder="64-char hex" />
      </div>

      <div style={{ display: 'flex', gap: 10, marginTop: 14, flexWrap: 'wrap' }}>
        <button className="btn-primary" onClick={submit} disabled={busy || !checkpointPath || privateKey.length !== 64}>
          {busy ? 'Processing...' : chainOnline ? 'Register On Network' : 'Save For Later'}
        </button>
        <span className="badge" style={{
          background: chainOnline ? 'rgba(16,185,129,0.12)' : 'rgba(245,158,11,0.12)',
          color: chainOnline ? 'var(--green)' : 'var(--orange)',
        }}>
          {chainOnline ? 'Chain Online' : 'Chain Offline'}
        </span>
      </div>

      {status && <div className="train-status-ok">{status}</div>}
      {error && <div className="train-status-err">{error}</div>}
    </div>
  );
}
