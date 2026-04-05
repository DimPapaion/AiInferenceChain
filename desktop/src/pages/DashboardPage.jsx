import React, { useState } from 'react';
import './DashboardPage.css';
import NodeStatus from './dashboard/NodeStatus';
import TrainingHistory from './dashboard/TrainingHistory';
import WalletPanel from './dashboard/WalletPanel';
import NetworkView from './dashboard/NetworkView';

const TABS = [
  { id: 'node',     label: 'Node',     icon: '◎' },
  { id: 'training', label: 'Training', icon: '◈' },
  { id: 'network',  label: 'Network',  icon: '⌁' },
  { id: 'wallet',   label: 'Wallet',   icon: '◇' },
];

export default function DashboardPage({ apiBase }) {
  const [tab, setTab] = useState('node');

  return (
    <div className="dash-root">
      {/* Sidebar */}
      <nav className="dash-sidebar">
        <div className="dash-sidebar-logo">IC</div>
        {TABS.map((t) => (
          <button
            key={t.id}
            className={`dash-nav-btn ${tab === t.id ? 'active' : ''}`}
            onClick={() => setTab(t.id)}
          >
            <span className="dash-nav-icon">{t.icon}</span>
            <span className="dash-nav-label">{t.label}</span>
          </button>
        ))}
        <div className="dash-sidebar-spacer" />
        <button
          className="dash-nav-btn danger"
          onClick={() => {
            if (window.confirm('Reset onboarding? You will need to re-train and re-submit your node.')) {
              localStorage.removeItem('ic_onboarded');
              window.location.reload();
            }
          }}
        >
          <span className="dash-nav-icon">↩</span>
          <span className="dash-nav-label">Reset</span>
        </button>
      </nav>

      {/* Content */}
      <main className="dash-content">
        {tab === 'node'     && <NodeStatus     apiBase={apiBase} />}
        {tab === 'training' && <TrainingHistory apiBase={apiBase} />}
        {tab === 'network'  && <NetworkView    apiBase={apiBase} />}
        {tab === 'wallet'   && <WalletPanel    apiBase={apiBase} />}
      </main>
    </div>
  );
}
