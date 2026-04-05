import React, { useState } from 'react';
import './DashboardPage.css';
import HomeHub from './dashboard/HomeHub';
import JoinNetworkPage from './dashboard/JoinNetworkPage';
import StakingPage from './dashboard/StakingPage';
import TrainPage from './dashboard/TrainPage';
import SettingsPage from './dashboard/SettingsPage';

const TABS = [
  { id: 'home',     label: 'Home',           icon: '⌂' },
  { id: 'join',     label: 'Join Network',   icon: '◉' },
  { id: 'staking',  label: 'Staking',        icon: '⟐' },
  { id: 'dnn',      label: 'Become DNN Node', icon: '⬢' },
  { id: 'settings', label: 'Settings',       icon: '⚙' },
];

export default function DashboardPage({ apiBase }) {
  const [tab, setTab] = useState('home');

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
            title={t.label}
          >
            <span className="dash-nav-icon">{t.icon}</span>
            <span className="dash-nav-label">{t.label}</span>
          </button>
        ))}
        <div className="dash-sidebar-spacer" />
        <button className="dash-nav-btn danger" onClick={() => window.location.reload()} title="Reload app">
          <span className="dash-nav-icon">↩</span>
          <span className="dash-nav-label">Reload</span>
        </button>
      </nav>

      {/* Content */}
      <main className="dash-content">
        {tab === 'home'    && <HomeHub />}
        {tab === 'join'    && <JoinNetworkPage apiBase={apiBase} />}
        {tab === 'staking' && <StakingPage apiBase={apiBase} />}
        {tab === 'dnn' && <TrainPage apiBase={apiBase} />}
        {tab === 'settings' && <SettingsPage />}
      </main>
    </div>
  );
}
