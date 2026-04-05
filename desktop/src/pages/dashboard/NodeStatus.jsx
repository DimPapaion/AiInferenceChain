import React, { useEffect, useState } from 'react';
import '../DashboardPage.css';

export default function NodeStatus({ apiBase }) {
  const [status, setStatus] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch(`${apiBase}/health`)
      .then((r) => r.json())
      .then(() => {
        // Placeholder: in production, query /api/node/status from the chain
        setStatus({
          state: 'pending_validation',
          public_key: localStorage.getItem('ic_pubkey') || '—',
          submissions: 1,
          challenges_passed: 0,
          challenges_pending: 1,
        });
      })
      .catch(() => setStatus(null))
      .finally(() => setLoading(false));
  }, [apiBase]);

  const STATE_LABELS = {
    pending_validation: { label: 'Pending validation', color: 'var(--orange)' },
    active:             { label: 'Active',              color: 'var(--green)'  },
    inactive:           { label: 'Inactive',            color: 'var(--text-3)' },
  };

  return (
    <div>
      <div className="dash-panel-title">Node Status</div>
      <div className="dash-panel-sub">Live status of your registered DNN inference node.</div>

      {loading && <div style={{ color: 'var(--text-3)' }}>Connecting to sidecar…</div>}

      {!loading && !status && (
        <div className="card" style={{ color: 'var(--red)' }}>
          Could not reach the local sidecar. Make sure the app is running correctly.
        </div>
      )}

      {status && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <div className="card">
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 16 }}>
              <div style={{
                width: 10, height: 10, borderRadius: '50%',
                background: STATE_LABELS[status.state]?.color || 'var(--text-3)',
                boxShadow: `0 0 8px ${STATE_LABELS[status.state]?.color || 'var(--text-3)'}`,
              }} />
              <span style={{ fontWeight: 700 }}>
                {STATE_LABELS[status.state]?.label || status.state}
              </span>
            </div>
            <StatRow label="Public Key"          value={status.public_key} mono />
            <StatRow label="Submissions"         value={status.submissions} />
            <StatRow label="Challenges Passed"   value={status.challenges_passed} />
            <StatRow label="Challenges Pending"  value={status.challenges_pending} />
          </div>

          <div className="card" style={{ background: 'rgba(124,58,237,0.06)', borderColor: 'rgba(124,58,237,0.2)' }}>
            <div style={{ fontSize: 13, color: 'var(--text-2)', lineHeight: 1.6 }}>
              <strong style={{ color: 'var(--purple-light)' }}>What happens next?</strong><br />
              Network validators will send inference challenges to your model. Once you
              pass the quality-of-inference threshold, your node becomes active and
              eligible to earn rewards.
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function StatRow({ label, value, mono }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                  padding: '8px 0', borderBottom: '1px solid var(--border)' }}>
      <span style={{ fontSize: 13, color: 'var(--text-3)' }}>{label}</span>
      <span style={{ fontSize: 13, color: 'var(--text-1)', fontFamily: mono ? 'var(--mono)' : 'inherit',
                     maxWidth: 340, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
        {value}
      </span>
    </div>
  );
}
