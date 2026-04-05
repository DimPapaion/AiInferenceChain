import React, { useState, useEffect } from 'react';
import '../DashboardPage.css';

export default function NetworkView({ apiBase }) {
  const [peers, setPeers] = useState(null);

  useEffect(() => {
    // Placeholder — will query chain REST API once network endpoint is configured
    setPeers([
      { id: '0x3a9f…1b2c', role: 'Validator', status: 'active', stake: '500 INC' },
      { id: '0xf01d…8e44', role: 'Inference', status: 'active', stake: '200 INC' },
      { id: '0xc22b…0073', role: 'Inference', status: 'pending', stake: '200 INC' },
    ]);
  }, [apiBase]);

  return (
    <div>
      <div className="dash-panel-title">Network</div>
      <div className="dash-panel-sub">Known peers and validators on the InferenceChain network.</div>
      <div className="card" style={{ marginBottom: 12, fontSize: 12, color: 'var(--orange)' }}>
        Network view requires a running node endpoint. Showing placeholder data.
      </div>
      {peers && (
        <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr style={{ background: 'var(--bg-3)' }}>
                {['Node ID', 'Role', 'Status', 'Stake'].map((h) => (
                  <th key={h} style={{ padding: '10px 16px', textAlign: 'left', fontSize: 11, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.05em', fontWeight: 600 }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {peers.map((p) => (
                <tr key={p.id} style={{ borderTop: '1px solid var(--border)' }}>
                  <td style={{ padding: '10px 16px', fontFamily: 'var(--mono)', fontSize: 13 }}>{p.id}</td>
                  <td style={{ padding: '10px 16px', fontSize: 13 }}>{p.role}</td>
                  <td style={{ padding: '10px 16px' }}>
                    <span className="badge" style={{
                      background: p.status === 'active' ? 'rgba(16,185,129,0.1)' : 'rgba(245,158,11,0.1)',
                      color: p.status === 'active' ? 'var(--green)' : 'var(--orange)',
                    }}>{p.status}</span>
                  </td>
                  <td style={{ padding: '10px 16px', fontSize: 13, color: 'var(--text-2)' }}>{p.stake}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
