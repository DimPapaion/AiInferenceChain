import React from 'react';
import '../DashboardPage.css';

export default function TrainingHistory() {
  // In production: load from app data directory / sidecar
  const runs = JSON.parse(localStorage.getItem('ic_training_runs') || '[]');

  return (
    <div>
      <div className="dash-panel-title">Training History</div>
      <div className="dash-panel-sub">Past training runs stored on this device.</div>

      {runs.length === 0 ? (
        <div className="card" style={{ color: 'var(--text-3)', textAlign: 'center', padding: '48px 24px' }}>
          No training runs recorded yet.<br />
          Complete the setup wizard to train and register a model.
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          {runs.map((run, i) => (
            <div key={i} className="card">
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <div>
                  <div style={{ fontWeight: 700 }}>{run.model_name || 'Unknown model'}</div>
                  <div style={{ fontSize: 12, color: 'var(--text-3)' }}>
                    {new Date(run.timestamp * 1000).toLocaleString()}
                  </div>
                </div>
                <div style={{ textAlign: 'right' }}>
                  <div style={{ fontSize: 13, color: 'var(--green)' }}>
                    {run.val_acc ? `Val acc: ${(run.val_acc * 100).toFixed(1)}%` : ''}
                  </div>
                  <div style={{ fontSize: 12, color: 'var(--text-3)' }}>
                    {run.epochs} epochs
                  </div>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
