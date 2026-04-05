import React, { useState, useEffect } from 'react';
import '../WizardPage.css';
import './StepSubmit.css';

export default function StepSubmit({
  apiBase, back,
  archSource, datasetInfo, config, trainingResult,
  onComplete,
}) {
  const [privateKey, setPrivateKey]   = useState('');
  const [manifest, setManifest]       = useState(null);
  const [sigHex, setSigHex]           = useState('');
  const [pubKeyHex, setPubKeyHex]     = useState('');
  const [phase, setPhase]             = useState('idle'); // idle|signing|signed|submitting|done|saved|error
  const [error, setError]             = useState(null);
  const [chainOnline, setChainOnline] = useState(null); // null=checking, true, false

  // Check chain connectivity when the user reaches this step
  useEffect(() => {
    fetch(`${apiBase}/chain/status`)
      .then((r) => r.json())
      .then((d) => setChainOnline(d.reachable))
      .catch(() => setChainOnline(false));
  }, [apiBase]);

  const hashString = async (str) => {
    const buf = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(str));
    return Array.from(new Uint8Array(buf)).map((b) => b.toString(16).padStart(2, '0')).join('');
  };

  const sign = async () => {
    if (!privateKey.trim() || privateKey.trim().length !== 64) {
      setError('Private key must be a 64-character hex string (32 bytes).');
      return;
    }
    if (!trainingResult?.checkpoint) {
      setError('No training checkpoint found.');
      return;
    }
    setPhase('signing');
    setError(null);
    try {
      const [archHash, datasetHash] = await Promise.all([
        hashString(archSource),
        hashString(datasetInfo?.url || datasetInfo?.dataset_name || ''),
      ]);

      const resp = await fetch(`${apiBase}/chain/sign-checkpoint`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          checkpoint_path: trainingResult.checkpoint,
          arch_hash: archHash,
          dataset_hash: datasetHash,
          config,
          metrics: trainingResult.metrics || [],
          node_private_key_hex: privateKey.trim(),
        }),
      });
      const data = await resp.json();
      if (!data.ok) { setError(data.error); setPhase('error'); return; }

      setManifest(data.manifest);
      setSigHex(data.signature_hex);
      setPubKeyHex(data.public_key_hex);
      setPhase('signed');
    } catch (e) {
      setError(e.message);
      setPhase('error');
    }
  };

  const submit = async () => {
    setPhase('submitting');
    setError(null);
    try {
      const resp = await fetch(`${apiBase}/chain/submit`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          manifest,
          signature_hex: sigHex,
          node_public_key_hex: pubKeyHex,
        }),
      });
      const data = await resp.json();
      if (!data.ok) { setError(data.error || JSON.stringify(data.response)); setPhase('error'); return; }
      setPhase('done');
    } catch (e) {
      setError(e.message);
      setPhase('error');
    }
  };

  const saveLocally = async () => {
    setPhase('submitting');
    setError(null);
    try {
      const resp = await fetch(`${apiBase}/chain/save-manifest`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          manifest,
          signature_hex: sigHex,
          node_public_key_hex: pubKeyHex,
        }),
      });
      const data = await resp.json();
      if (!data.ok) { setError(data.error); setPhase('error'); return; }
      setPhase('saved');
    } catch (e) {
      setError(e.message);
      setPhase('error');
    }
  };

  return (
    <div className="wstep-card">
      <div className="wstep-kicker">Step 5 of 5</div>
      <div className="wstep-title">Join the Network</div>
      <div className="wstep-subtitle">
        Sign your training manifest with your node private key, then submit it
        to the InferenceChain network. Validators will verify the model before
        activating your node.
      </div>

      {/* Chain connectivity indicator */}
      <div className={`submit-chain-status ${chainOnline === null ? 'checking' : chainOnline ? 'online' : 'offline'}`}>
        {chainOnline === null && '⏳ Checking chain connectivity…'}
        {chainOnline === true  && '● Chain reachable — live submission enabled'}
        {chainOnline === false && '● Chain offline — you can still sign and save the manifest locally. Submit it later from the Dashboard when the network is up.'}
      </div>

      {/* Metrics summary */}
      {trainingResult?.metrics?.length > 0 && (
        <div className="submit-metrics">
          {(() => {
            const last = trainingResult.metrics[trainingResult.metrics.length - 1];
            return (
              <>
                <Pill label="Epochs" value={last.epoch} />
                <Pill label="Train acc" value={`${(last.train_acc * 100).toFixed(1)}%`} />
                {last.val_acc != null && <Pill label="Val acc" value={`${(last.val_acc * 100).toFixed(1)}%`} accent />}
                {last.train_loss != null && <Pill label="Train loss" value={last.train_loss} />}
              </>
            );
          })()}
        </div>
      )}

      {/* Private key input */}
      {phase !== 'done' && phase !== 'saved' && (
        <div className="wstep-field" style={{ marginTop: 16 }}>
          <label>Node Private Key (hex)</label>
          <input
            type="password"
            placeholder="64-character hex string"
            value={privateKey}
            onChange={(e) => { setPrivateKey(e.target.value); setError(null); }}
          />
          <span className="hint">
            Your 32-byte Ed25519 private key in hex. It never leaves this device.
          </span>
        </div>
      )}

      {phase === 'idle' && (
        <button className="btn-primary" onClick={sign}>Sign Manifest</button>
      )}
      {phase === 'signing' && (
        <div className="wstep-status info">Signing…</div>
      )}

      {phase === 'signed' && (
        <>
          <div className="wstep-status ok">✓ Manifest signed.</div>
          <div className="submit-manifest">
            <div className="submit-manifest-label">Manifest preview</div>
            <pre data-selectable>{JSON.stringify(manifest, null, 2).slice(0, 600)}</pre>
          </div>
          <div style={{ display: 'flex', gap: 12, marginTop: 16, flexWrap: 'wrap' }}>
            <button className="btn-ghost" onClick={() => { setPhase('idle'); setManifest(null); }}>
              Re-sign
            </button>
            {chainOnline
              ? (
                <button className="btn-primary" onClick={submit}>
                  Submit to Network →
                </button>
              ) : (
                <button className="btn-primary" onClick={saveLocally}>
                  Save Locally (submit when online) →
                </button>
              )
            }
          </div>
        </>
      )}

      {phase === 'submitting' && (
        <div className="wstep-status info">
          {chainOnline ? 'Submitting to network…' : 'Saving manifest locally…'}
        </div>
      )}

      {phase === 'done' && (
        <>
          <div className="wstep-status ok" style={{ fontSize: 15, padding: '16px 20px' }}>
            <strong>🎉 Node registration submitted!</strong><br />
            Your public key: <code data-selectable style={{ fontSize: 11 }}>{pubKeyHex}</code><br />
            Validators will challenge your model. Once verified, your node goes live.
          </div>
          <div className="wstep-actions">
            <button className="btn-primary" onClick={onComplete}>Open Dashboard →</button>
          </div>
        </>
      )}

      {phase === 'saved' && (
        <>
          <div className="wstep-status ok" style={{ fontSize: 15, padding: '16px 20px' }}>
            <strong>Manifest saved locally.</strong><br />
            Your public key: <code data-selectable style={{ fontSize: 11 }}>{pubKeyHex}</code><br />
            Open the <strong>Dashboard → Node Status</strong> tab to submit it once the network is live.
          </div>
          <div className="wstep-actions">
            <button className="btn-primary" onClick={onComplete}>Open Dashboard →</button>
          </div>
        </>
      )}

      {phase === 'error' && (
        <div className="wstep-status error">
          <pre style={{ whiteSpace: 'pre-wrap', fontSize: 11 }}>{error}</pre>
          <button className="btn-ghost" style={{ marginTop: 10 }} onClick={() => { setPhase('idle'); setError(null); }}>
            Retry
          </button>
        </div>
      )}

      {phase !== 'done' && phase !== 'saved' && (
        <div className="wstep-actions">
          <button className="btn-ghost" onClick={back} disabled={phase === 'signing' || phase === 'submitting'}>
            ← Back
          </button>
        </div>
      )}
    </div>
  );
}

function Pill({ label, value, accent }) {
  return (
    <div className="submit-pill" style={accent ? { borderColor: 'rgba(124,58,237,0.4)' } : {}}>
      <span className="conf-key">{label}</span>
      <span className="conf-val" style={accent ? { color: 'var(--purple-light)' } : {}}>{value}</span>
    </div>
  );
}


export default function StepSubmit({
  apiBase, back,
  archSource, datasetInfo, config, trainingResult,
  onComplete,
}) {
  const [privateKey, setPrivateKey]   = useState('');
  const [manifest, setManifest]       = useState(null);
  const [sigHex, setSigHex]           = useState('');
  const [pubKeyHex, setPubKeyHex]     = useState('');
  const [phase, setPhase]             = useState('idle'); // idle|signing|signed|submitting|done|error
  const [error, setError]             = useState(null);

  const hashString = async (str) => {
    const buf = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(str));
    return Array.from(new Uint8Array(buf)).map((b) => b.toString(16).padStart(2, '0')).join('');
  };

  const sign = async () => {
    if (!privateKey.trim() || privateKey.trim().length !== 64) {
      setError('Private key must be a 64-character hex string (32 bytes).');
      return;
    }
    if (!trainingResult?.checkpoint) {
      setError('No training checkpoint found.');
      return;
    }
    setPhase('signing');
    setError(null);
    try {
      const [archHash, datasetHash] = await Promise.all([
        hashString(archSource),
        hashString(datasetInfo?.url || datasetInfo?.dataset_name || ''),
      ]);

      const resp = await fetch(`${apiBase}/chain/sign-checkpoint`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          checkpoint_path: trainingResult.checkpoint,
          arch_hash: archHash,
          dataset_hash: datasetHash,
          config,
          metrics: trainingResult.metrics || [],
          node_private_key_hex: privateKey.trim(),
        }),
      });
      const data = await resp.json();
      if (!data.ok) { setError(data.error); setPhase('error'); return; }

      setManifest(data.manifest);
      setSigHex(data.signature_hex);
      setPubKeyHex(data.public_key_hex);
      setPhase('signed');
    } catch (e) {
      setError(e.message);
      setPhase('error');
    }
  };

  const submit = async () => {
    setPhase('submitting');
    setError(null);
    try {
      const resp = await fetch(`${apiBase}/chain/submit`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          manifest,
          signature_hex: sigHex,
          node_public_key_hex: pubKeyHex,
        }),
      });
      const data = await resp.json();
      if (!data.ok) { setError(data.error || JSON.stringify(data.response)); setPhase('error'); return; }
      setPhase('done');
    } catch (e) {
      setError(e.message);
      setPhase('error');
    }
  };

  return (
    <div className="wstep-card">
      <div className="wstep-kicker">Step 5 of 5</div>
      <div className="wstep-title">Join the Network</div>
      <div className="wstep-subtitle">
        Sign your training manifest with your node private key, then submit it
        to the InferenceChain network. Validators will verify the model before
        activating your node.
      </div>

      {/* Metrics summary */}
      {trainingResult?.metrics?.length > 0 && (
        <div className="submit-metrics">
          {(() => {
            const last = trainingResult.metrics[trainingResult.metrics.length - 1];
            return (
              <>
                <Pill label="Epochs" value={last.epoch} />
                <Pill label="Train acc" value={`${(last.train_acc * 100).toFixed(1)}%`} />
                {last.val_acc != null && <Pill label="Val acc" value={`${(last.val_acc * 100).toFixed(1)}%`} accent />}
                {last.train_loss != null && <Pill label="Train loss" value={last.train_loss} />}
              </>
            );
          })()}
        </div>
      )}

      {/* Private key input */}
      {phase !== 'done' && (
        <div className="wstep-field" style={{ marginTop: 16 }}>
          <label>Node Private Key (hex)</label>
          <input
            type="password"
            placeholder="64-character hex string"
            value={privateKey}
            onChange={(e) => { setPrivateKey(e.target.value); setError(null); }}
          />
          <span className="hint">
            Your 32-byte Ed25519 private key in hex. It never leaves this device.
          </span>
        </div>
      )}

      {phase === 'idle' && (
        <button className="btn-primary" onClick={sign}>Sign Manifest</button>
      )}
      {phase === 'signing' && (
        <div className="wstep-status info">Signing…</div>
      )}

      {phase === 'signed' && (
        <>
          <div className="wstep-status ok">✓ Manifest signed — ready to submit.</div>
          <div className="submit-manifest">
            <div className="submit-manifest-label">Manifest preview</div>
            <pre data-selectable>{JSON.stringify(manifest, null, 2).slice(0, 600)}</pre>
          </div>
          <div style={{ display: 'flex', gap: 12, marginTop: 16 }}>
            <button className="btn-ghost" onClick={() => { setPhase('idle'); setManifest(null); }}>
              Re-sign
            </button>
            <button className="btn-primary" onClick={submit}>
              Submit to Network →
            </button>
          </div>
        </>
      )}

      {phase === 'submitting' && (
        <div className="wstep-status info">Submitting to network…</div>
      )}

      {phase === 'done' && (
        <>
          <div className="wstep-status ok" style={{ fontSize: 15, padding: '16px 20px' }}>
            <strong>🎉 Node registration submitted!</strong><br />
            Your public key: <code data-selectable style={{ fontSize: 11 }}>{pubKeyHex}</code><br />
            Validators will challenge your model. Once verified, your node goes live.
          </div>
          <div className="wstep-actions">
            <button className="btn-primary" onClick={onComplete}>
              Open Dashboard →
            </button>
          </div>
        </>
      )}

      {phase === 'error' && (
        <div className="wstep-status error">
          <pre style={{ whiteSpace: 'pre-wrap', fontSize: 11 }}>{error}</pre>
          <button className="btn-ghost" style={{ marginTop: 10 }} onClick={() => { setPhase('idle'); setError(null); }}>
            Retry
          </button>
        </div>
      )}

      {phase !== 'done' && (
        <div className="wstep-actions">
          <button className="btn-ghost" onClick={back} disabled={phase === 'signing' || phase === 'submitting'}>
            ← Back
          </button>
        </div>
      )}
    </div>
  );
}

function Pill({ label, value, accent }) {
  return (
    <div className="submit-pill" style={accent ? { borderColor: 'rgba(124,58,237,0.4)' } : {}}>
      <span className="conf-key">{label}</span>
      <span className="conf-val" style={accent ? { color: 'var(--purple-light)' } : {}}>{value}</span>
    </div>
  );
}
