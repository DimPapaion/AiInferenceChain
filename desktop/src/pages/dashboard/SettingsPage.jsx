import React, { useEffect, useState } from 'react';
import '../DashboardPage.css';

const DEFAULTS = {
  closeBehavior: 'ask',
  startToTray: false,
};

export default function SettingsPage() {
  const [settings, setSettings] = useState(DEFAULTS);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!window.electronAPI?.getSettings) return;
    window.electronAPI.getSettings().then((s) => setSettings({ ...DEFAULTS, ...(s || {}) })).catch(() => {});
  }, []);

  const save = async (next) => {
    setSaving(true);
    setSettings(next);
    try {
      await window.electronAPI?.setSettings?.(next);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div>
      <div className="dash-panel-title">Settings</div>
      <div className="dash-panel-sub">Control startup and close behavior.</div>

      <div className="card" style={{ maxWidth: 760 }}>
        <div style={{ marginBottom: 14 }}>
          <div style={{ fontSize: 14, fontWeight: 700, marginBottom: 6 }}>On Close</div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
            {[
              ['ask', 'Ask every time'],
              ['background', 'Run in background (tray)'],
              ['quit', 'Always fully quit'],
            ].map(([value, label]) => (
              <button
                key={value}
                className={`dash-nav-btn-lite ${settings.closeBehavior === value ? 'active' : ''}`}
                onClick={() => save({ ...settings, closeBehavior: value })}
              >
                {label}
              </button>
            ))}
          </div>
        </div>

        <div style={{ marginBottom: 10 }}>
          <div style={{ fontSize: 14, fontWeight: 700, marginBottom: 6 }}>Startup</div>
          <label style={{ display: 'flex', alignItems: 'center', gap: 8, color: 'var(--text-2)', fontSize: 13 }}>
            <input
              type="checkbox"
              checked={!!settings.startToTray}
              onChange={(e) => save({ ...settings, startToTray: e.target.checked })}
            />
            Start minimized to tray
          </label>
        </div>

        <div style={{ marginTop: 14, color: 'var(--text-3)', fontSize: 12 }}>
          {saving ? 'Saving settings...' : 'Settings are stored locally in your app data folder.'}
        </div>
      </div>
    </div>
  );
}
