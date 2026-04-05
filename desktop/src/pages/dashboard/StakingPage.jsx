import React, { useState } from 'react';
import '../DashboardPage.css';

export default function StakingPage() {
  const [amount, setAmount] = useState('1000');
  const [apy, setApy] = useState('8.4');

  return (
    <div>
      <div className="dash-panel-title">Staking</div>
      <div className="dash-panel-sub">Manage stake allocation and projected rewards.</div>

      <div className="staking-grid">
        <div className="card">
          <div className="staking-title">Stake Dashboard</div>
          <div className="staking-kpis">
            <Kpi label="Active Stake" value="-- INC" />
            <Kpi label="Pending Rewards" value="-- INC" />
            <Kpi label="Epoch Yield" value={`${apy}%`} />
          </div>
        </div>

        <div className="card">
          <div className="staking-title">Stake Planner</div>
          <label className="staking-label">Stake Amount (INC)</label>
          <input className="staking-input" value={amount} onChange={(e) => setAmount(e.target.value)} />

          <label className="staking-label">Expected APY (%)</label>
          <input className="staking-input" value={apy} onChange={(e) => setApy(e.target.value)} />

          <div style={{ marginTop: 10, fontSize: 13, color: 'var(--text-2)' }}>
            Estimated annual rewards: <strong style={{ color: 'var(--green)' }}>
              {Number(amount || 0) * Number(apy || 0) / 100} INC
            </strong>
          </div>

          <div style={{ display: 'flex', gap: 8, marginTop: 12, flexWrap: 'wrap' }}>
            <button className="btn-primary" disabled>Stake (coming soon)</button>
            <button className="btn-ghost" disabled>Unstake (coming soon)</button>
          </div>
        </div>
      </div>
    </div>
  );
}

function Kpi({ label, value }) {
  return (
    <div className="staking-kpi">
      <div className="staking-kpi-label">{label}</div>
      <div className="staking-kpi-value">{value}</div>
    </div>
  );
}
