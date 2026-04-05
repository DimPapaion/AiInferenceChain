import React, { useState } from 'react';
import '../WizardPage.css';

export default function StepDataset({
  apiBase, next, back,
  archInfo, datasetInfo, setDatasetInfo,
}) {
  const [url, setUrl] = useState(datasetInfo?.dataset_name || datasetInfo?.url || '');
  const [loading, setLoading] = useState(false);
  const [status, setStatus] = useState(null);

  const validate = async () => {
    if (!url.trim()) {
      setStatus({ type: 'error', message: 'Please enter a dataset URL or HuggingFace name.' });
      return;
    }
    setLoading(true);
    setStatus(null);
    try {
      const resp = await fetch(`${apiBase}/validate/dataset`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          url: url.trim(),
          num_classes: archInfo?.output_shape?.[1] ?? null,
        }),
      });
      const data = await resp.json();
      if (data.ok) {
        setDatasetInfo({ ...data, url: url.trim() });
        const cls = data.num_classes ? `${data.num_classes} classes` : '';
        const src = data.source === 'huggingface' ? '(HuggingFace)' : '(URL archive)';
        setStatus({ type: 'ok', message: `✓ Dataset validated ${src} — ${cls}` });
      } else {
        setStatus({ type: 'error', message: data.error });
        setDatasetInfo(null);
      }
    } catch (e) {
      setStatus({ type: 'error', message: `Sidecar not reachable: ${e.message}` });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="wstep-card">
      <div className="wstep-kicker">Step 2 of 5</div>
      <div className="wstep-title">Connect Your Dataset</div>
      <div className="wstep-subtitle">
        Enter a HuggingFace dataset name (e.g. <code>cifar10</code>) or a direct
        URL to a <code>.zip</code> / <code>.tar.gz</code> archive with
        ImageFolder layout (<code>train/&lt;class&gt;/</code>,{' '}
        <code>val/&lt;class&gt;/</code>).
      </div>

      <div className="wstep-field">
        <label>Dataset</label>
        <input
          type="text"
          placeholder="cifar10 or https://…/dataset.zip"
          value={url}
          onChange={(e) => { setUrl(e.target.value); setDatasetInfo(null); setStatus(null); }}
          onKeyDown={(e) => e.key === 'Enter' && validate()}
        />
        <span className="hint">
          HuggingFace name → checked via datasets library.
          URL → downloaded, extracted, and structure-validated locally.
        </span>
      </div>

      <button className="btn-ghost" onClick={validate} disabled={!url.trim() || loading}>
        {loading ? 'Validating…' : 'Validate Dataset'}
      </button>

      {status && <div className={`wstep-status ${status.type}`}>{status.message}</div>}

      {datasetInfo?.class_names?.length > 0 && (
        <div style={{ marginTop: 16 }}>
          <div style={{ fontSize: 12, color: 'var(--text-3)', marginBottom: 6, textTransform: 'uppercase', letterSpacing: '0.04em' }}>
            Class preview
          </div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
            {datasetInfo.class_names.map((c) => (
              <span key={c} className="badge" style={{ background: 'var(--bg-3)', color: 'var(--text-2)', border: '1px solid var(--border-md)' }}>
                {c}
              </span>
            ))}
          </div>
        </div>
      )}

      <div className="wstep-actions">
        <button className="btn-ghost" onClick={back}>← Back</button>
        <button className="btn-primary" disabled={!datasetInfo} onClick={next}>
          Continue →
        </button>
      </div>
    </div>
  );
}
