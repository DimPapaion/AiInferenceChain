import React, { useState, useEffect, useRef } from 'react';
import '../WizardPage.css';
import './StepTraining.css';

export default function StepTraining({
  apiBase, next, back,
  archSource, archInfo, datasetInfo, config,
  trainingResult, setTrainingResult,
}) {
  const [phase, setPhase]     = useState('idle'); // idle | starting | running | done | error | cancelled
  const [metrics, setMetrics] = useState([]);
  const [error, setError]     = useState(null);
  const abortRef              = useRef(false);

  const dataPath = window.electronAPI
    ? null  // fetched async below
    : '/tmp/ic_checkpoints';
  const [checkpointDir, setCheckpointDir] = useState(dataPath);

  useEffect(() => {
    if (!window.electronAPI) return;
    window.electronAPI.getDataPath().then((p) => {
      setCheckpointDir(p + '/checkpoints');
    });
  }, []);

  const startTraining = async () => {
    setPhase('starting');
    setMetrics([]);
    setError(null);
    abortRef.current = false;

    // 1. Configure run on sidecar
    try {
      const startResp = await fetch(`${apiBase}/train/start`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          arch_source: archSource,
          dataset_info: datasetInfo,
          config,
          checkpoint_dir: checkpointDir || '/tmp/ic_checkpoints',
        }),
      });
      const startData = await startResp.json();
      if (!startData.ok) {
        setError(startData.error);
        setPhase('error');
        return;
      }
    } catch (e) {
      setError(`Could not reach sidecar: ${e.message}`);
      setPhase('error');
      return;
    }

    // 2. Stream epochs via SSE
    setPhase('running');
    try {
      const evtSource = new EventSource(`${apiBase}/train/stream`);
      evtSource.onmessage = (e) => {
        if (abortRef.current) { evtSource.close(); return; }
        const msg = JSON.parse(e.data);
        if (msg.type === 'epoch') {
          setMetrics((prev) => [...prev, msg]);
        } else if (msg.type === 'done') {
          setTrainingResult({ checkpoint: msg.checkpoint, metrics: msg.metrics });
          setPhase('done');
          evtSource.close();
        } else if (msg.type === 'error') {
          setError(msg.error);
          setPhase('error');
          evtSource.close();
        } else if (msg.type === 'cancelled') {
          setPhase('cancelled');
          evtSource.close();
        }
      };
      evtSource.onerror = () => {
        if (!abortRef.current) {
          setError('SSE connection lost.');
          setPhase('error');
        }
        evtSource.close();
      };
    } catch (e) {
      setError(e.message);
      setPhase('error');
    }
  };

  const stopTraining = async () => {
    abortRef.current = true;
    await fetch(`${apiBase}/train/stop`, { method: 'POST' }).catch(() => {});
    setPhase('cancelled');
  };

  const lastMetric = metrics[metrics.length - 1];

  return (
    <div className="wstep-card">
      <div className="wstep-kicker">Step 4 of 5</div>
      <div className="wstep-title">Train Your Model</div>
      <div className="wstep-subtitle">
        Training will run locally on your GPU (or CPU as fallback).
        Checkpoints are saved every 5 epochs.
      </div>

      {/* Config summary */}
      <div className="train-config-summary">
        {[
          ['Optimizer', config.optimizer],
          ['LR', config.lr],
          ['Epochs', config.epochs],
          ['Batch', config.batch_size],
          ['Augmentation', config.augmentation],
          ['Loss', config.loss],
        ].map(([k, v]) => (
          <div key={k} className="train-config-pill">
            <span className="conf-key">{k}</span>
            <span className="conf-val">{v}</span>
          </div>
        ))}
      </div>

      {/* Controls */}
      {phase === 'idle' && (
        <button className="btn-primary" onClick={startTraining}>
          Start Training
        </button>
      )}
      {phase === 'starting' && (
        <div className="wstep-status info">Initialising training run…</div>
      )}
      {phase === 'running' && (
        <button className="btn-ghost" onClick={stopTraining}>Stop Training</button>
      )}

      {/* Live metrics */}
      {metrics.length > 0 && (
        <>
          <div className="train-metric-row" style={{ marginTop: 20 }}>
            <MetricBox label="Epoch" value={`${lastMetric.epoch} / ${lastMetric.total_epochs}`} />
            <MetricBox label="Train loss" value={lastMetric.train_loss} />
            <MetricBox label="Train acc" value={`${(lastMetric.train_acc * 100).toFixed(1)}%`} />
            {lastMetric.val_acc != null && (
              <MetricBox label="Val acc" value={`${(lastMetric.val_acc * 100).toFixed(1)}%`} accent />
            )}
          </div>
          <LossChart metrics={metrics} />
        </>
      )}

      {/* Status messages */}
      {phase === 'done' && (
        <div className="wstep-status ok">
          ✓ Training complete — checkpoint saved at{' '}
          <code style={{ fontSize: 11 }}>{trainingResult?.checkpoint}</code>
        </div>
      )}
      {phase === 'cancelled' && (
        <div className="wstep-status info">Training stopped by user.</div>
      )}
      {phase === 'error' && (
        <div className="wstep-status error">
          <pre style={{ whiteSpace: 'pre-wrap', fontSize: 11 }}>{error}</pre>
        </div>
      )}

      <div className="wstep-actions">
        <button className="btn-ghost" onClick={back} disabled={phase === 'running' || phase === 'starting'}>
          ← Back
        </button>
        <button
          className="btn-primary"
          disabled={phase !== 'done'}
          onClick={next}
        >
          Continue →
        </button>
      </div>
    </div>
  );
}

function MetricBox({ label, value, accent }) {
  return (
    <div className="metric-box" style={accent ? { borderColor: 'rgba(124,58,237,0.4)' } : {}}>
      <span className="metric-label">{label}</span>
      <span className="metric-value" style={accent ? { color: 'var(--purple-light)' } : {}}>{value}</span>
    </div>
  );
}

function LossChart({ metrics }) {
  // Simple SVG sparkline for train/val loss
  const W = 580, H = 100;
  const pad = 8;
  const maxLoss = Math.max(...metrics.map((m) => m.train_loss));
  const minLoss = Math.min(...metrics.map((m) => m.train_loss));
  const range = maxLoss - minLoss || 1;

  const toX = (i) => pad + (i / (metrics.length - 1 || 1)) * (W - pad * 2);
  const toY = (v) => H - pad - ((v - minLoss) / range) * (H - pad * 2);

  const trainPath = metrics.map((m, i) => `${i === 0 ? 'M' : 'L'}${toX(i)},${toY(m.train_loss)}`).join(' ');
  const valPath = metrics
    .filter((m) => m.val_loss != null)
    .map((m, i) => {
      const idx = metrics.indexOf(m);
      return `${i === 0 ? 'M' : 'L'}${toX(idx)},${toY(m.val_loss)}`;
    })
    .join(' ');

  return (
    <div className="loss-chart">
      <div className="loss-chart-legend">
        <span style={{ color: 'var(--blue)' }}>— Train loss</span>
        {valPath && <span style={{ color: 'var(--purple-light)' }}>— Val loss</span>}
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} width="100%" height={H} style={{ overflow: 'visible' }}>
        {trainPath && <path d={trainPath} fill="none" stroke="var(--blue)" strokeWidth="1.5" strokeLinejoin="round" />}
        {valPath   && <path d={valPath}   fill="none" stroke="var(--purple-light)" strokeWidth="1.5" strokeLinejoin="round" strokeDasharray="4 2" />}
      </svg>
    </div>
  );
}
