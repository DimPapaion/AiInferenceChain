import React, { useState } from 'react';
import '../DashboardPage.css';

export default function WalletPanel() {
  const [address] = useState(localStorage.getItem('ic_pubkey') || '—');

  return (
    <div>
      <div className="dash-panel-title">Wallet</div>
      <div className="dash-panel-sub">Node identity and on-chain balance.</div>
      <div className="card">
        <div style={{ marginBottom: 20 }}>
          <div style={{ fontSize: 11, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 4 }}>
            Public Key / Address
          </div>
          <div style={{ fontFamily: 'var(--mono)', fontSize: 13, color: 'var(--text-1)', wordBreak: 'break-all' }} data-selectable>
            {address}
          </div>
        </div>
        <div style={{ display: 'flex', gap: 24 }}>
          <BalanceBox label="INC Balance" value="—" />
          <BalanceBox label="Staked" value="—" />
          <BalanceBox label="Rewards" value="—" />
        </div>
      </div>
      <div className="card" style={{ marginTop: 12, fontSize: 12, color: 'var(--text-3)', lineHeight: 1.6 }}>
        Wallet integration with the on-chain balance API is coming in a future release.
        Your node public key is your on-chain identity.
      </div>
    </div>
  );
}

function BalanceBox({ label, value }) {
  return (
    <div>
      <div style={{ fontSize: 11, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 4 }}>{label}</div>
      <div style={{ fontSize: 22, fontWeight: 700, color: 'var(--text-1)', fontFamily: 'var(--mono)' }}>{value}</div>
    </div>
  );
}
