import React, { useState, useEffect, useRef } from 'react';
import './InferencePage.css';
import { chain as chainApi } from '../api/client';
import { ws as wsUrls } from '../api/client';

// ── SHA-256 in browser ────────────────────────────────────────────────────────
async function sha256hex(buffer) {
  const digest = await crypto.subtle.digest('SHA-256', buffer);
  return Array.from(new Uint8Array(digest))
    .map(b => b.toString(16).padStart(2, '0'))
    .join('');
}

// ── Helpers ───────────────────────────────────────────────────────────────────
const trunc = (s, n = 12) => s ? `${s.slice(0, n)}…` : '—';
const phaseOrder = ['preprepare', 'prepare', 'commit', 'pos'];
const phaseLabel = { preprepare: 'PRE-PREPARE', prepare: 'PREPARE', commit: 'COMMIT', pos: 'PoS' };

// ── QoI Phase Tracker ─────────────────────────────────────────────────────────
function PhaseTracker({ events }) {
  const latestRound = events.find(e => e.type === 'consensus_round');
  if (!latestRound) return null;

  const currentPhase = latestRound.phase || 'preprepare';
  const committed    = latestRound.status === 'committed';
  const isQoi        = currentPhase !== 'pos';

  const steps = isQoi
    ? ['preprepare', 'prepare', 'commit']
    : ['pos'];

  const currentIdx = steps.indexOf(currentPhase);

  return (
    <div className="phase-tracker card">
      <div className="pt-header">
        <p className="section-title" style={{margin:0}}>
          {isQoi ? 'QoI Consensus Round' : 'PoS Round'} #{latestRound.round}
        </p>
        {committed && <span className="badge badge-ok">Committed ✓</span>}
        {latestRound.participants > 0 && (
          <span className="pt-participants">👥 {latestRound.participants} validators</span>
        )}
      </div>

      {isQoi && (
        <div className="phase-steps">
          {steps.map((s, i) => {
            const state = committed
              ? 'done'
              : i < currentIdx ? 'done'
              : i === currentIdx ? 'active'
              : 'pending';
            return (
              <React.Fragment key={s}>
                <div className={`phase-step phase-${state}`}>
                  <div className="phase-dot">
                    {state === 'done'   && '✓'}
                    {state === 'active' && <span className="spinner" style={{width:12,height:12,border:'2px solid rgba(255,255,255,0.2)',borderTopColor:'currentColor'}} />}
                    {state === 'pending'&& '·'}
                  </div>
                  <span className="phase-name">{phaseLabel[s]}</span>
                </div>
                {i < steps.length - 1 && <div className={`phase-line ${i < currentIdx || committed ? 'done' : ''}`} />}
              </React.Fragment>
            );
          })}
        </div>
      )}
    </div>
  );
}

// ── Recent inference blocks ───────────────────────────────────────────────────
function RecentInferenceBlocks({ blocks }) {
  const qoiBlocks = (blocks || []).filter(b => b.block_type === 'qoi');

  return (
    <div className="recent-inf card">
      <p className="section-title">Recent QoI Blocks ({qoiBlocks.length})</p>
      {qoiBlocks.length === 0 ? (
        <div className="empty-state" style={{minHeight:60}}>No QoI blocks committed yet</div>
      ) : (
        <div className="inf-block-list">
          {qoiBlocks.map(b => (
            <div key={b.height} className="inf-block-row">
              <span className="inf-block-height">#{b.height}</span>
              <span className={`badge badge-dnn`}>QoI</span>
              <span className="hash mono">{trunc(b.hash, 16)}</span>
              <span className="hash mono" style={{fontSize:11,color:'var(--text-3)'}}>
                proposer: {trunc(b.proposer_id, 12)}
              </span>
              <span className="inf-txcount">{b.tx_count} txs</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ── Submit panel ──────────────────────────────────────────────────────────────
function SubmitPanel({ onSubmitted }) {
  const [file,       setFile]       = useState(null);
  const [hash,       setHash]       = useState('');
  const [preview,    setPreview]    = useState(null);
  const [step,       setStep]       = useState('idle');  // idle | hashing | ready | submitting | done | error
  const [txId,       setTxId]       = useState('');
  const [errMsg,     setErrMsg]     = useState('');
  const fileRef = useRef();

  const handleFile = async (e) => {
    const f = e.target.files?.[0];
    if (!f) return;
    setFile(f);
    setStep('hashing');
    setHash('');
    setPreview(null);

    // Preview
    const url = URL.createObjectURL(f);
    setPreview(url);

    // Compute SHA-256
    const buf = await f.arrayBuffer();
    const h   = await sha256hex(buf);
    setHash(h);
    setStep('ready');
  };

  const handleSubmit = async () => {
    if (!hash || !file) return;
    setStep('submitting');
    setErrMsg('');

    try {
      // Build a minimal INFERENCE_REQUEST transaction body.
      // The real tx needs a sender address + signature — for testnet we
      // build a dev/unsigned tx that the node accepts in dev mode.
      const body = {
        tx_type: 'INFERENCE_REQUEST',
        sender:  '0x0000000000000000000000000000000000000000',
        nonce:   1,
        fee:     0.001,
        signature: 'dev',
        payload: {
          image_hash:   hash,
          model_id:     'auto',
          reward:       1.0,
        },
      };
      const res = await fetch(
        (process.env.REACT_APP_API_URL || 'http://localhost:8000') + '/tx/submit',
        { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }
      );
      const data = await res.json().catch(() => ({}));

      if (!res.ok || data.accepted === false) {
        setErrMsg(data.detail || data.reason || 'Submission failed');
        setStep('error');
        return;
      }

      setTxId(data.tx_id || '');
      setStep('done');
      onSubmitted?.();
    } catch (err) {
      setErrMsg(err.message);
      setStep('error');
    }
  };

  const reset = () => {
    setFile(null); setHash(''); setPreview(null);
    setStep('idle'); setTxId(''); setErrMsg('');
    if (fileRef.current) fileRef.current.value = '';
  };

  return (
    <div className="submit-panel card">
      <p className="section-title">Submit Inference Request</p>

      {/* Drop zone */}
      <div
        className={`dropzone ${file ? 'has-file' : ''}`}
        onClick={() => fileRef.current?.click()}
        onDragOver={e => e.preventDefault()}
        onDrop={e => { e.preventDefault(); const f = e.dataTransfer.files?.[0]; if (f) fileRef.current.files = e.dataTransfer.files; handleFile({ target: e.dataTransfer }); }}
      >
        {preview ? (
          <img src={preview} alt="preview" className="img-preview" />
        ) : (
          <div className="dropzone-inner">
            <span className="dz-icon">◈</span>
            <span className="dz-label">Drop an image or click to browse</span>
            <span className="dz-hint">PNG, JPG, JPEG · 32×32 CIFAR-10 compatible</span>
          </div>
        )}
        <input ref={fileRef} type="file" accept="image/*" onChange={handleFile} style={{display:'none'}} />
      </div>

      {/* Hash display */}
      {step === 'hashing' && (
        <div className="hash-row"><div className="spinner" /><span>Computing SHA-256…</span></div>
      )}
      {hash && (
        <div className="hash-row">
          <span className="hash-label">SHA-256</span>
          <span className="hash mono">{hash}</span>
        </div>
      )}

      {/* Actions */}
      <div className="submit-actions">
        {(step === 'ready' || step === 'error') && (
          <button className="btn btn-primary" onClick={handleSubmit} disabled={step === 'submitting'}>
            {step === 'submitting' ? <><div className="spinner" />Submitting…</> : 'Submit to Chain →'}
          </button>
        )}
        {step === 'submitting' && (
          <button className="btn btn-primary" disabled>
            <div className="spinner" />Broadcasting…
          </button>
        )}
        {(step === 'done' || step === 'error' || file) && (
          <button className="btn btn-ghost" onClick={reset}>Reset</button>
        )}
      </div>

      {/* Result */}
      {step === 'done' && (
        <div className="result-box result-ok">
          <span className="result-icon">✓</span>
          <div>
            <div className="result-title">Transaction accepted</div>
            {txId && <div className="hash mono" style={{marginTop:4}}>{txId}</div>}
            <div className="result-sub">Watch the Consensus Monitor below for the QoI round to complete.</div>
          </div>
        </div>
      )}
      {step === 'error' && (
        <div className="result-box result-err">
          <span className="result-icon">✗</span>
          <div>
            <div className="result-title">Submission failed</div>
            <div className="result-sub">{errMsg}</div>
          </div>
        </div>
      )}
    </div>
  );
}

// ── Live consensus events ─────────────────────────────────────────────────────
function ConsensusFeed() {
  const [events,   setEvents]   = useState([]);
  const [wsStatus, setWsStatus] = useState('disconnected');
  const wsRef = useRef(null);

  const connect = () => {
    const ws = new WebSocket(wsUrls.consensus);
    ws.onopen    = () => setWsStatus('connected');
    ws.onerror   = () => setWsStatus('error');
    ws.onclose   = () => { setWsStatus('reconnecting'); setTimeout(connect, 3000); };
    ws.onmessage = (e) => {
      try {
        const msg = JSON.parse(e.data);
        setEvents(prev => [{ ...msg, _id: Date.now() + Math.random() }, ...prev].slice(0, 50));
      } catch {}
    };
    wsRef.current = ws;
  };

  useEffect(() => {
    connect();
    return () => wsRef.current?.close();
  }, []);

  const statusDot = wsStatus === 'connected' ? '🟢' : wsStatus === 'reconnecting' ? '🟡' : '🔴';

  return (
    <div className="cf-panel card">
      <div className="cf-header">
        <p className="section-title" style={{margin:0}}>Consensus Monitor</p>
        <span className="cf-status">{statusDot} {wsStatus}</span>
      </div>

      <PhaseTracker events={events} />

      <div className="cf-log">
        {events.length === 0 ? (
          <div className="empty-state" style={{minHeight:80}}>Waiting for consensus events…</div>
        ) : events.map(ev => (
          <div key={ev._id} className={`cf-event ${ev.status === 'committed' ? 'cf-committed' : ''}`}>
            <span className="cf-time">
              {new Date().toLocaleTimeString('en-US', { hour12: false })}
            </span>
            <span className="cf-type">{ev.phase?.toUpperCase() || ev.type}</span>
            <span className="cf-detail">
              {ev.type === 'consensus_round' && <>
                Block #{ev.round}
                {ev.participants > 0 && ` · ${ev.participants} validators`}
                {ev.status === 'committed' && <strong className="cf-ok"> ✓ COMMITTED</strong>}
              </>}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Main ──────────────────────────────────────────────────────────────────────
export default function InferencePage() {
  const [blocks,  setBlocks]  = useState([]);
  const [refresh, setRefresh] = useState(0);

  useEffect(() => {
    chainApi.blocks(20).then(setBlocks).catch(() => {});
    const id = setInterval(() =>
      chainApi.blocks(20).then(setBlocks).catch(() => {}), 5000);
    return () => clearInterval(id);
  }, [refresh]);

  return (
    <div className="page-wrap">
      <div className="inf-page-header">
        <div>
          <h2 className="page-title">Inference</h2>
          <p className="page-subtitle">
            Submit an image to the network and watch QoI consensus commit it on-chain
          </p>
        </div>
      </div>

      <div className="inf-grid">
        {/* Left: submit + recent blocks */}
        <div className="inf-left">
          <SubmitPanel onSubmitted={() => setRefresh(r => r + 1)} />
          <div style={{marginTop:16}}>
            <RecentInferenceBlocks blocks={blocks} />
          </div>

          {/* How it works mini */}
          <div className="inf-explainer card">
            <p className="section-title">How QoI consensus works</p>
            <ol className="explainer-list">
              <li>Your image is hashed client-side (SHA-256) — only the hash goes on-chain.</li>
              <li>Nodes with the image run their CIFAR-10 DNN and broadcast inference vectors.</li>
              <li>Cosine similarity between all pairs is computed; a 2f+1 quorum must agree.</li>
              <li>The agreed result + reputation deltas are written to a QoI block.</li>
            </ol>
          </div>
        </div>

        {/* Right: consensus monitor */}
        <div className="inf-right">
          <ConsensusFeed />
        </div>
      </div>
    </div>
  );
}
