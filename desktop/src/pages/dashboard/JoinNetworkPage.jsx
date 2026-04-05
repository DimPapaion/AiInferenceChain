import React, { useEffect, useMemo, useState } from 'react';
import '../DashboardPage.css';

function makeInitialSteps() {
  return {
    consensus: [
      { label: 'Download checkpoint', progress: 0 },
      { label: 'Find consensus peers', progress: 0 },
      { label: 'Download slot data', progress: 0 },
    ],
    execution: [
      { label: 'Find execution peers', progress: 0 },
      { label: 'Download state', progress: 0 },
      { label: 'Download block data', progress: 0 },
    ],
  };
}

export default function JoinNetworkPage({ apiBase }) {
  const [status, setStatus] = useState({ reachable: false, endpoint: 'http://localhost:8000' });
  const [syncing, setSyncing] = useState(false);
  const [steps, setSteps] = useState(makeInitialSteps);

  const overall = useMemo(() => {
    const all = [...steps.consensus, ...steps.execution];
    const sum = all.reduce((acc, s) => acc + s.progress, 0);
    return Math.round(sum / all.length);
  }, [steps]);

  useEffect(() => {
    fetch(`${apiBase}/chain/status`)
      .then((r) => r.json())
      .then(setStatus)
      .catch(() => setStatus({ reachable: false, endpoint: 'http://localhost:8000' }));
  }, [apiBase]);

  useEffect(() => {
    if (!syncing) return;
    const t = setInterval(() => {
      setSteps((prev) => {
        const bump = (arr) => arr.map((s) => ({ ...s, progress: Math.min(100, s.progress + Math.max(3, Math.floor(Math.random() * 16))) }));
        return { consensus: bump(prev.consensus), execution: bump(prev.execution) };
      });
    }, 900);
    return () => clearInterval(t);
  }, [syncing]);

  useEffect(() => {
    if (overall >= 100) setSyncing(false);
  }, [overall]);

  const startSync = () => {
    setSteps(makeInitialSteps());
    setSyncing(true);
  };

  return (
    <div>
      <div className="dash-panel-title">Join The Network</div>
      <div className="dash-panel-sub">Peer discovery and chain synchronization.</div>

      <div className="card" style={{ marginBottom: 12 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap' }}>
          <div>
            <div style={{ fontSize: 12, color: 'var(--text-3)', textTransform: 'uppercase' }}>Endpoint</div>
            <div style={{ fontFamily: 'var(--mono)', fontSize: 13 }} data-selectable>{status.endpoint}</div>
          </div>
          <div>
            <div style={{ fontSize: 12, color: 'var(--text-3)', textTransform: 'uppercase' }}>Network Status</div>
            <div style={{ color: status.reachable ? 'var(--green)' : 'var(--orange)', fontWeight: 700 }}>
              {status.reachable ? 'Online' : 'Offline'}
            </div>
          </div>
        </div>
      </div>

      <div className="card sync-card">
        <div className="sync-top">
          <div>
            <div className="sync-title">Syncing node data</div>
            <div className="sync-sub">{status.reachable ? 'Fetching peers and chain state.' : 'Network offline. You can still preview the sync flow.'}</div>
          </div>
          <button className="btn-primary" onClick={startSync} disabled={syncing}>
            {syncing ? 'Syncing...' : 'Start Sync'}
          </button>
        </div>

        <div className="sync-progress-wrap">
          <div className="sync-progress-label">Overall progress: {overall}%</div>
          <div className="sync-progress-bar"><span style={{ width: `${overall}%` }} /></div>
        </div>

        <div className="sync-columns">
          <SyncColumn title="Consensus Layer" steps={steps.consensus} />
          <SyncColumn title="Execution Layer" steps={steps.execution} />
        </div>
      </div>
    </div>
  );
}

function SyncColumn({ title, steps }) {
  return (
    <div>
      <div className="sync-col-title">{title}</div>
      <div className="sync-steps">
        {steps.map((s) => (
          <div key={s.label} className="sync-step">
            <div className="sync-step-row">
              <span>{s.label}</span>
              <span>{s.progress}%</span>
            </div>
            <div className="sync-mini"><span style={{ width: `${s.progress}%` }} /></div>
          </div>
        ))}
      </div>
    </div>
  );
}
