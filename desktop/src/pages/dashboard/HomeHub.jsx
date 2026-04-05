import React from 'react';
import '../DashboardPage.css';

export default function HomeHub() {
  const stats = [
    { label: 'Local Sidecar', value: 'Online', tone: 'var(--green)' },
    { label: 'Wallet', value: localStorage.getItem('ic_pubkey') ? 'Ready' : 'Not set', tone: 'var(--purple-light)' },
    { label: 'Training Runs', value: String((JSON.parse(localStorage.getItem('ic_training_runs') || '[]') || []).length), tone: 'var(--blue)' },
    { label: 'Pending Submissions', value: 'Check Join Network tab', tone: 'var(--orange)' },
  ];

  return (
    <div>
      <div className="dash-panel-title">InferenceChain Home</div>
      <div className="dash-panel-sub">Your local AI node command center.</div>

      <div className="home-hero card">
        <div className="home-hero-glow" />
        <div className="home-hero-title">Decentralized AI Inference Node</div>
        <div className="home-hero-sub">
          Train models, join the network, and stake as a validator from one desktop app.
        </div>
        <div className="home-hero-particles" aria-hidden>
          <span />
          <span />
          <span />
          <span />
          <span />
        </div>
      </div>

      <div className="home-grid">
        {stats.map((s) => (
          <div className="card home-stat" key={s.label}>
            <div className="home-stat-label">{s.label}</div>
            <div className="home-stat-value" style={{ color: s.tone }}>{s.value}</div>
          </div>
        ))}
      </div>

      <div className="card" style={{ marginTop: 14 }}>
        <div style={{ fontSize: 13, color: 'var(--text-2)', lineHeight: 1.7 }}>
          <strong style={{ color: 'var(--text-1)' }}>Recommended flow:</strong><br />
          1. Train a new model in <strong>Train</strong>.<br />
          2. If you already have a trained checkpoint, use <strong>Register Model</strong>.<br />
          3. Open <strong>Join Network</strong> to discover peers and sync when chain is online.<br />
          4. Configure delegation and reward targets in <strong>Staking</strong>.
        </div>
      </div>
    </div>
  );
}
