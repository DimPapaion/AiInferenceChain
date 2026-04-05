import React, { useEffect, useState, useCallback } from 'react';
import '../DashboardPage.css';

export default function NodeStatus({ apiBase }) {
  const [sidecarOk, setSidecarOk] = useState(null);
  const [chainOnline, setChainOnline] = useState(null);
  const [pending, setPending] = useState([]);
  const [submitting, setSubmitting] = useState(null);
  const [retryError, setRetryError] = useState(null);

  const refresh = useCallback(() => {
    fetch(`${apiBase}/health`)
      .then((r) => r.json())
      .then(() => setSidecarOk(true))
      .catch(() => setSidecarOk(false));

    fetch(`${apiBase}/chain/status`)
      .then((r) => r.json())
      .then((d) => setChainOnline(d.reachable))
      .catch(() => setChainOnline(false));

    fetch(`${apiBase}/chain/pending-submissions`)
      .then((r) => r.json())
      .then((d) => setPending(d.items || []))
      .catch(() => setPending([]));
  }, [apiBase]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const retrySubmit = async (item) => {
    setSubmitting(item.filename);
    setRetryError(null);
    try {
      const resp = await fetch(`${apiBase}/chain/submit`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          manifest: item.manifest,
          signature_hex: item.signature_hex,
          node_public_key_hex: item.node_public_key_hex,
          network_endpoint: item.network_endpoint,
        }),
      });
      const data = await resp.json();
      if (data.ok) {
        refresh();
      } else {
        setRetryError(`${item.filename}: ${data.error || JSON.stringify(data.response)}`);
      }
    } catch (e) {
      setRetryError(e.message);
    } finally {
      setSubmitting(null);
    }
  };

  return (
    <div>
      <div className="dash-panel-title">Node Status</div>
      <div className="dash-panel-sub">Local sidecar health and network connectivity.</div>

      <StatusBadge
        label="Local sidecar"
        ok={sidecarOk}
        okText="Running"
        failText="Not reachable - restart the app"
      />

      <StatusBadge
        label="InferenceChain network"
        ok={chainOnline}
        okText="Connected"
        failText="Offline - chain not running yet"
        offlineNote="The network is not live yet. You can still train models and sign manifests. They will be submitted once the network launches."
      />

      <button className="btn-ghost" style={{ marginTop: 16, fontSize: 12 }} onClick={refresh}>
        Refresh
      </button>

      {pending.length > 0 && (
        <div style={{ marginTop: 24 }}>
          <div className="dash-panel-sub" style={{ marginBottom: 10 }}>
            Pending Submissions ({pending.length})
          </div>
          {pending.map((item) => (
            <div key={item.filename} className="card" style={{ marginBottom: 10 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 8 }}>
                <div>
                  <div style={{ fontFamily: 'var(--mono)', fontSize: 12, color: 'var(--text-2)' }}>{item.filename}</div>
                  <div style={{ fontSize: 11, color: 'var(--text-3)', marginTop: 2 }}>
                    Saved {new Date(item.saved_at * 1000).toLocaleString()}
                  </div>
                </div>
                <button
                  className="btn-primary"
                  style={{ fontSize: 12, padding: '6px 14px' }}
                  disabled={!chainOnline || submitting === item.filename}
                  onClick={() => retrySubmit(item)}
                  title={chainOnline ? 'Submit to network' : 'Chain is offline'}
                >
                  {submitting === item.filename ? 'Submitting...' : 'Submit'}
                </button>
              </div>
              {retryError && submitting === null && (
                <div style={{ marginTop: 8, fontSize: 11, color: 'var(--red)' }}>{retryError}</div>
              )}
            </div>
          ))}
        </div>
      )}

      {chainOnline === false && pending.length === 0 && (
        <div className="card" style={{ marginTop: 20, background: 'rgba(124,58,237,0.06)', borderColor: 'rgba(124,58,237,0.2)' }}>
          <div style={{ fontSize: 13, color: 'var(--text-2)', lineHeight: 1.7 }}>
            <strong style={{ color: 'var(--purple-light)' }}>Getting started</strong><br />
            Use the <strong>New Training Run</strong> wizard to upload your model architecture,
            connect a dataset, and train locally. At the end, sign your manifest.
            It will be saved here and submitted once the network is live.
          </div>
        </div>
      )}
    </div>
  );
}

function StatusBadge({ label, ok, okText, failText, offlineNote }) {
  const color = ok === null ? 'var(--text-3)' : ok ? 'var(--green)' : 'var(--orange)';
  const text = ok === null ? 'Checking...' : ok ? okText : failText;
  return (
    <div className="card" style={{ marginBottom: 10, display: 'flex', flexDirection: 'column', gap: 6 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
        <div
          style={{
            width: 8,
            height: 8,
            borderRadius: '50%',
            background: color,
            boxShadow: `0 0 6px ${color}`,
            flexShrink: 0,
          }}
        />
        <div style={{ display: 'flex', justifyContent: 'space-between', width: '100%', flexWrap: 'wrap', gap: 4 }}>
          <span style={{ fontSize: 13, color: 'var(--text-2)' }}>{label}</span>
          <span style={{ fontSize: 13, color, fontWeight: 600 }}>{text}</span>
        </div>
      </div>
      {ok === false && offlineNote && (
        <div style={{ fontSize: 11, color: 'var(--text-3)', paddingLeft: 18, lineHeight: 1.5 }}>
          {offlineNote}
        </div>
      )}
    </div>
  );
}
