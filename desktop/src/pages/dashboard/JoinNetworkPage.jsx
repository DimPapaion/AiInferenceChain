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
  const [status, setStatus] = useState({ reachable: false, endpoint: 'http://localhost:8000', peer_count: 0, chain_height: 0 });
  const [syncing, setSyncing] = useState(false);
  const [steps, setSteps] = useState(makeInitialSteps);

  const overall = useMemo(() => {
    const all = [...steps.consensus, ...steps.execution];
    const sum = all.reduce((acc, s) => acc + s.progress, 0);
    return Math.round(sum / all.length);
  }, [steps]);

  useEffect(() => {
    let alive = true;
    const tick = async () => {
      try {
        const resp = await fetch(`${apiBase}/chain/sync/status`);
        const data = await resp.json();
        if (!alive) return;
        setStatus({
          reachable: !!data.reachable,
          endpoint: data.endpoint || 'http://localhost:8000',
          peer_count: data.peer_count || 0,
          chain_height: data.chain_height || 0,
        });
        if (Array.isArray(data.consensus) && Array.isArray(data.execution)) {
          setSteps({ consensus: data.consensus, execution: data.execution });
        }
      } catch {
        if (!alive) return;
        setStatus({ reachable: false, endpoint: 'http://localhost:8000', peer_count: 0, chain_height: 0 });
      }
    };
    tick();
    const interval = setInterval(tick, 1400);
    return () => {
      alive = false;
      clearInterval(interval);
    };
  }, [apiBase]);

  useEffect(() => {
    if (overall >= 100) setSyncing(false);
  }, [overall]);

  const startSync = () => {
    setSyncing(true);
    fetch(`${apiBase}/chain/sync/start`, { method: 'POST' }).catch(() => {});
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
          <div>
            <div style={{ fontSize: 12, color: 'var(--text-3)', textTransform: 'uppercase' }}>Peers</div>
            <div style={{ fontWeight: 700 }}>{status.peer_count || 0}</div>
          </div>
          <div>
            <div style={{ fontSize: 12, color: 'var(--text-3)', textTransform: 'uppercase' }}>Chain Height</div>
            <div style={{ fontWeight: 700 }}>{status.chain_height || 0}</div>
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
