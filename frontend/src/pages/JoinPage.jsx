import React, { useState, useRef } from 'react';
import './JoinPage.css';
import { uploadModel } from '../api/client';

// ─────────────────────────────────────────────────────────────────────────────
// DESKTOP APP DOWNLOAD — Portable exe built with PyInstaller + Electron
// Point to deployment guide for download instructions and portable app
// ─────────────────────────────────────────────────────────────────────────────
const RELEASES_URL = 'https://github.com/DimPapaion/AiInferenceChain/blob/main/DEPLOYMENT_GUIDE.md';

const HOW_IT_WORKS = [
  {
    n: '01',
    icon: '↓',
    title: 'Download & install the app',
    body: 'A single installer (Windows .exe, macOS .dmg, Linux .AppImage). No Python or CUDA installation needed — everything is bundled.',
  },
  {
    n: '02',
    icon: '◈',
    title: 'Upload an architecture and train',
    body: 'Supply a PyTorch nn.Module file and a dataset URL. Configure optimizer, learning rate, augmentation, and loss from the hyperparameter panel — no code needed.',
  },
  {
    n: '03',
    icon: '⬡',
    title: 'Sign the checkpoint and join',
    body: 'Once training is done, sign the training manifest with your node key and submit it to the network. Validators issue inference challenges; on pass, your node goes live.',
  },
];

const APP_FEATURES = [
  {
    icon: '◫',
    title: 'Architecture validator',
    body: 'Upload any architecture.py. The app performs an AST safety scan then runs a dry forward pass to verify output shape before any training starts.',
  },
  {
    icon: '⌁',
    title: 'Dataset connector',
    body: 'Point to any HuggingFace dataset name or a direct .zip / .tar.gz archive with ImageFolder layout. Auto-detection, class preview, sample counts.',
  },
  {
    icon: '▦',
    title: 'Hyperparameter panel',
    body: 'Optimizer (Adam / AdamW / SGD), learning rate, scheduler, batch size, weight decay, augmentation presets, and loss function — all from a clean UI.',
  },
  {
    icon: '◌',
    title: 'Live training dashboard',
    body: 'Watch loss and accuracy curves update in real time as epochs complete. Training runs locally on your GPU (CPU fallback). Checkpoints saved every 5 epochs.',
  },
  {
    icon: '▲',
    title: 'OOD profiling & knowledge scoring',
    body: 'The app automatically fits class-conditional Out-of-Distribution profiles using a shared ViT-B/16 encoder. These determine your node\'s knowledge (familiarity) with each request domain.',
  },
  {
    icon: '⬢',
    title: 'Anti-gaming infrastructure',
    body: 'Your reliability is tracked on-chain with dual EMA updates. Hidden challenges (15% rate) verify honest participation. Multi-factor quorum weighting (stake × knowledge × reliability) ensures fair selection.'
  },
  {
    icon: '✦',
    title: 'Signed manifest submission',
    body: 'Training results are hashed and signed with your Ed25519 node key. The manifest is submitted to the chain. Validators verify your model through QoI challenge rounds and OOD profiling.',
  },
  {
    icon: '◇',
    title: 'Node & wallet dashboard',
    body: 'After admission, monitor your node status, reliability score, challenge audit trail, QoI participation, OOD familiarity scores, and on-chain reputation from the dashboard.'
  },
];

const SYSREQS = [
  { label: 'OS',     value: 'Windows 10/11 · macOS 13+ · Ubuntu 22.04+' },
  { label: 'RAM',    value: '8 GB minimum, 16 GB recommended' },
  { label: 'GPU',    value: 'Optional but strongly recommended — NVIDIA CUDA 11.8+, AMD ROCm 6+ (CPU fallback available)' },
  { label: 'Disk',   value: '4 GB free for app + model checkpoints' },
  { label: 'Python', value: 'Bundled — no separate installation needed' },
];

const STEPS = ['Identity', 'Model File', 'Architecture', 'Validate & Register'];

const DATASETS = [
  { value: 'cifar10',          label: 'CIFAR-10 (32×32, 10 classes)' },
  { value: 'cifar100',         label: 'CIFAR-100 (32×32, 100 classes)' },
  { value: 'imagenet_subset',  label: 'ImageNet Subset' },
  { value: 'mnist',            label: 'MNIST (28×28, 10 classes)' },
  { value: 'custom',           label: 'Custom Dataset' },
];

const FRAMEWORKS = [
  { value: 'pytorch',     label: 'PyTorch (.pt / .pth)' },
  { value: 'tensorflow',  label: 'TensorFlow / Keras (.h5)' },
  { value: 'onnx',        label: 'ONNX (.onnx)' },
];

const DATASET_DEFAULTS = {
  cifar10:  { mean: '0.4914, 0.4822, 0.4465', std: '0.2023, 0.1994, 0.2010', inputShape: '3, 32, 32', outputShape: '10' },
  cifar100: { mean: '0.5071, 0.4865, 0.4409', std: '0.2673, 0.2564, 0.2762', inputShape: '3, 32, 32', outputShape: '100' },
  mnist:    { mean: '0.1307',                  std: '0.3081',                  inputShape: '1, 28, 28', outputShape: '10' },
};

const API_BASE = process.env.REACT_APP_API_URL !== undefined
  ? process.env.REACT_APP_API_URL
  : 'http://localhost:8000';

// ── Field components ──────────────────────────────────────────────────────────
function Field({ label, hint, required, children }) {
  return (
    <div className="jp-field">
      <label className="jp-label">
        {label}
        {required && <span className="jp-required">*</span>}
        {hint && <span className="jp-hint">{hint}</span>}
      </label>
      {children}
    </div>
  );
}

function Input({ value, onChange, placeholder, mono }) {
  return (
    <input
      className={`jp-input ${mono ? 'mono' : ''}`}
      value={value}
      onChange={e => onChange(e.target.value)}
      placeholder={placeholder}
    />
  );
}

function Select({ value, onChange, options }) {
  return (
    <select className="jp-input jp-select" value={value} onChange={e => onChange(e.target.value)}>
      <option value="">Select…</option>
      {options.map(o => (
        <option key={o.value} value={o.value}>{o.label}</option>
      ))}
    </select>
  );
}

// ── Step 1: Identity ──────────────────────────────────────────────────────────
function StepIdentity({ data, set }) {
  return (
    <div className="jp-step-body">
      <p className="jp-step-intro">
        Provide your node's on-chain identity. The <em>address</em> becomes your
        node ID on-chain. The <em>endpoint</em> is where other nodes will call
        your <code>/predict</code> during QoI rounds.
      </p>

      <Field label="Wallet Address" required hint="Becomes your node_id on-chain">
        <Input mono value={data.address} onChange={v => set('address', v)}
          placeholder="0x0000000000000000000000000000000000000000" />
      </Field>

      <Field label="Node Endpoint URL" required hint="Public URL peers will call for inference">
        <Input value={data.endpoint} onChange={v => set('endpoint', v)}
          placeholder="https://your-node.example.com:8000" />
      </Field>

      <Field label="Public Key (hex)" required hint="Ed25519 or secp256k1 public key">
        <Input mono value={data.publicKey} onChange={v => set('publicKey', v)}
          placeholder="04a1b2c3d4..." />
      </Field>

      <Field label="Initial Stake (tokens)" hint="Submitted as a separate STAKE tx after registration">
        <Input value={data.stake} onChange={v => set('stake', v)} placeholder="100" />
      </Field>
    </div>
  );
}

// ── Step 2: Model File ────────────────────────────────────────────────────────
function StepModel({ data, set }) {
  const fileRef = useRef();

  const handleFile = (e) => {
    const f = e.target.files?.[0];
    if (f) set('file', f);
  };

  return (
    <div className="jp-step-body">
      <p className="jp-step-intro">
        Upload your trained model checkpoint. The file is validated locally
        (size, loadability, latency benchmark). Only the SHA-256 hash goes on-chain.
      </p>

      {/* Drop zone */}
      <div
        className={`jp-dropzone ${data.file ? 'has-file' : ''}`}
        onClick={() => fileRef.current?.click()}
        onDragOver={e => e.preventDefault()}
        onDrop={e => {
          e.preventDefault();
          const f = e.dataTransfer.files?.[0];
          if (f) set('file', f);
        }}
      >
        {data.file ? (
          <div className="jp-file-chosen">
            <span className="jp-file-icon">◈</span>
            <div>
              <div className="jp-file-name">{data.file.name}</div>
              <div className="jp-file-size">{(data.file.size / 1024 / 1024).toFixed(2)} MB</div>
            </div>
            <button className="btn btn-ghost btn-sm" onClick={e => { e.stopPropagation(); set('file', null); }}>
              ✕
            </button>
          </div>
        ) : (
          <div className="jp-dropzone-inner">
            <span className="jp-dz-icon">◈</span>
            <span className="jp-dz-label">Drop your model file or click to browse</span>
            <span className="jp-dz-hint">.pt · .pth · .h5 · .onnx</span>
          </div>
        )}
        <input ref={fileRef} type="file"
          accept=".pt,.pth,.h5,.hdf5,.onnx"
          onChange={handleFile}
          style={{ display: 'none' }} />
      </div>

      <div className="jp-row-2">
        <Field label="Model Name" required>
          <Input value={data.name} onChange={v => set('name', v)} placeholder="resnet20-cifar10" />
        </Field>
        <Field label="Version" required>
          <Input value={data.version} onChange={v => set('version', v)} placeholder="1.0.0" />
        </Field>
      </div>

      <Field label="Framework" required>
        <Select value={data.framework} onChange={v => set('framework', v)} options={FRAMEWORKS} />
      </Field>

      <Field label="Description" hint="Optional — architecture notes, training details">
        <textarea
          className="jp-input jp-textarea"
          value={data.description}
          onChange={e => set('description', e.target.value)}
          placeholder="ResNet-20 trained on CIFAR-10 for 200 epochs, SGD with momentum…"
          rows={3}
        />
      </Field>
    </div>
  );
}

// ── Step 3: Architecture & Preprocessing ─────────────────────────────────────
function StepArch({ data, set }) {
  const fillDatasetDefaults = (datasetId) => {
    set('datasetId', datasetId);
    const d = DATASET_DEFAULTS[datasetId];
    if (d) {
      set('normMean',    d.mean);
      set('normStd',     d.std);
      set('inputShape',  d.inputShape);
      set('outputShape', d.outputShape);
    }
  };

  return (
    <div className="jp-step-body">
      <p className="jp-step-intro">
        These parameters are committed on-chain and used by other validators to
        reproduce your preprocessing exactly during QoI comparison rounds.
      </p>

      <Field label="Dataset" required>
        <Select
          value={data.datasetId}
          onChange={fillDatasetDefaults}
          options={DATASETS}
        />
      </Field>
      {data.datasetId === 'custom' && (
        <Field label="Custom Dataset Name" required>
          <Input value={data.customDataset} onChange={v => set('customDataset', v)}
            placeholder="my-dataset-v1" />
        </Field>
      )}

      <div className="jp-row-2">
        <Field label="Input Shape" required hint="C, H, W — e.g. 3, 32, 32">
          <Input mono value={data.inputShape} onChange={v => set('inputShape', v)}
            placeholder="3, 32, 32" />
        </Field>
        <Field label="Output Classes" required hint="Number of output neurons">
          <Input mono value={data.outputShape} onChange={v => set('outputShape', v)}
            placeholder="10" />
        </Field>
      </div>

      <div className="jp-norm-section">
        <div className="jp-norm-header">
          <span className="jp-norm-title">Normalization</span>
          <span className="jp-norm-hint">Per-channel values applied before inference</span>
        </div>
        <div className="jp-row-2">
          <Field label="Mean" required hint="Comma-separated per channel">
            <Input mono value={data.normMean} onChange={v => set('normMean', v)}
              placeholder="0.4914, 0.4822, 0.4465" />
          </Field>
          <Field label="Std" required hint="Comma-separated per channel">
            <Input mono value={data.normStd} onChange={v => set('normStd', v)}
              placeholder="0.2023, 0.1994, 0.2010" />
          </Field>
        </div>
      </div>

      <div className="jp-row-2">
        <Field label="Min Accuracy Threshold" hint="0.0 – 1.0">
          <Input value={data.minAccuracy} onChange={v => set('minAccuracy', v)} placeholder="0.80" />
        </Field>
        <Field label="Max Latency (ms)" hint="Per-sample inference limit">
          <Input value={data.maxLatency} onChange={v => set('maxLatency', v)} placeholder="500" />
        </Field>
      </div>

      <Field label="Architecture Notes" hint="Optional — layers, block types, depth">
        <textarea
          className="jp-input jp-textarea"
          value={data.archNotes}
          onChange={e => set('archNotes', e.target.value)}
          placeholder='{"layers": 20, "block": "BasicBlock", "num_classes": 10}'
          rows={3}
        />
      </Field>
    </div>
  );
}

// ── Step 4: Validate & Register ───────────────────────────────────────────────
function StepValidate({ identity, model, arch, result, setResult, onRegister, regState }) {
  const [validating, setValidating] = useState(false);
  const [error,      setError]      = useState('');

  const runValidation = async () => {
    setValidating(true);
    setError('');
    setResult(null);

    const form = new FormData();
    form.append('file',               model.file);
    form.append('name',               model.name);
    form.append('version',            model.version);
    form.append('framework',          model.framework);
    form.append('description',        model.description || '');
    form.append('input_shape',        arch.inputShape);
    form.append('output_shape',       arch.outputShape);
    form.append('min_accuracy',       arch.minAccuracy   || '0');
    form.append('max_latency_ms',     arch.maxLatency    || '1000');
    form.append('max_size_mb',        '1000');
    form.append('dataset_id',         arch.datasetId === 'custom' ? arch.customDataset : arch.datasetId);
    form.append('normalization_mean', arch.normMean  || '');
    form.append('normalization_std',  arch.normStd   || '');
    form.append('architecture_notes', arch.archNotes || '');

    try {
      const data = await uploadModel(form);
      setResult(data);
    } catch (e) {
      setError(e.message);
    } finally {
      setValidating(false);
    }
  };

  const canRegister = result?.status === 'approved';

  return (
    <div className="jp-step-body">
      <p className="jp-step-intro">
        The model is validated <em>locally</em> first (size, loadability, latency).
        If it passes, the SHA-256 commitment hash is ready and you can submit a
        <code>NODE_REGISTER_DNN</code> transaction to the chain.
      </p>

      {/* Summary card */}
      <div className="jp-summary">
        <div className="jp-sum-row"><span>Address</span><span className="mono">{identity.address || '—'}</span></div>
        <div className="jp-sum-row"><span>Endpoint</span><span className="mono">{identity.endpoint || '—'}</span></div>
        <div className="jp-sum-row"><span>Model</span><span>{model.name} v{model.version} ({model.framework})</span></div>
        <div className="jp-sum-row"><span>Dataset</span><span>{arch.datasetId}</span></div>
        <div className="jp-sum-row"><span>Input Shape</span><span className="mono">{arch.inputShape}</span></div>
        <div className="jp-sum-row"><span>Norm Mean</span><span className="mono">{arch.normMean}</span></div>
        <div className="jp-sum-row"><span>Norm Std</span><span className="mono">{arch.normStd}</span></div>
      </div>

      {/* Validate button */}
      {!result && (
        <button
          className="btn btn-primary"
          onClick={runValidation}
          disabled={validating}
          style={{ width: '100%', justifyContent: 'center' }}
        >
          {validating ? <><div className="spinner" /> Validating model…</> : 'Run Validation ▶'}
        </button>
      )}

      {error && (
        <div className="jp-result-box jp-result-err">
          <span className="jp-result-icon">✗</span>
          <div>
            <div className="jp-result-title">Validation error</div>
            <div className="jp-result-sub">{error}</div>
          </div>
        </div>
      )}

      {/* Validation result */}
      {result && (
        <>
          <div className={`jp-result-box ${result.status === 'approved' ? 'jp-result-ok' : 'jp-result-err'}`}>
            <span className="jp-result-icon">{result.status === 'approved' ? '✓' : '✗'}</span>
            <div>
              <div className="jp-result-title">
                {result.status === 'approved' ? 'Validation passed' : 'Validation failed'}
              </div>
              <div className="jp-result-sub">{result.message}</div>
            </div>
          </div>

          {/* Check list */}
          {result.checks?.length > 0 && (
            <div className="jp-checks">
              {result.checks.map((c, i) => (
                <div key={i} className={`jp-check ${c.startsWith('✓') ? 'jp-check-ok' : 'jp-check-fail'}`}>
                  {c}
                </div>
              ))}
            </div>
          )}

          {/* Weights hash */}
          {result.weights_hash && (
            <div className="jp-hash-row">
              <span className="jp-hash-label">SHA-256</span>
              <span className="hash mono">{result.weights_hash}</span>
            </div>
          )}

          {/* Re-validate / Register */}
          <div className="jp-validate-actions">
            <button className="btn btn-ghost" onClick={() => setResult(null)}>
              Re-validate
            </button>
            {canRegister && (
              <button
                className="btn btn-primary"
                onClick={() => onRegister(result.weights_hash)}
                disabled={regState === 'submitting'}
              >
                {regState === 'submitting'
                  ? <><div className="spinner" /> Submitting…</>
                  : 'Register on Chain →'}
              </button>
            )}
          </div>

          {/* Registration result */}
          {regState === 'done' && (
            <div className="jp-result-box jp-result-ok" style={{ marginTop: 12 }}>
              <span className="jp-result-icon">✓</span>
              <div>
                <div className="jp-result-title">NODE_REGISTER_DNN submitted</div>
                <div className="jp-result-sub">
                  Your node is pending PoM verification. Watch the Validators page
                  — once validators confirm your model quality through hidden challenges and QoI rounds, your node becomes active.
                </div>
              </div>
            </div>
          )}
          {regState === 'error' && (
            <div className="jp-result-box jp-result-err" style={{ marginTop: 12 }}>
              <span className="jp-result-icon">✗</span>
              <div>
                <div className="jp-result-title">Registration failed</div>
                <div className="jp-result-sub">Check that your node is running and reachable.</div>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}

// ── Advanced manual registration form (unchanged, hidden by default) ──────────
function AdvancedRegistrationForm({ navigate }) {
  const [step, setStep] = useState(0);

  // Form state split by section
  const [identity, setIdentityRaw] = useState({
    address: '', endpoint: '', publicKey: '', stake: '100',
  });
  const [model, setModelRaw] = useState({
    file: null, name: '', version: '1.0.0', framework: 'pytorch', description: '',
  });
  const [arch, setArchRaw] = useState({
    datasetId: 'cifar10', customDataset: '',
    inputShape: '3, 32, 32', outputShape: '10',
    normMean: '0.4914, 0.4822, 0.4465', normStd: '0.2023, 0.1994, 0.2010',
    minAccuracy: '0.80', maxLatency: '500', archNotes: '',
  });

  const [valResult,  setValResult]  = useState(null);
  const [regState,   setRegState]   = useState('idle'); // idle | submitting | done | error

  const setIdentity = (k, v) => setIdentityRaw(p => ({ ...p, [k]: v }));
  const setModel    = (k, v) => setModelRaw(p => ({ ...p, [k]: v }));
  const setArch     = (k, v) => setArchRaw(p => ({ ...p, [k]: v }));

  // Validate required fields per step before advancing
  const canAdvance = () => {
    if (step === 0) return identity.address && identity.endpoint && identity.publicKey;
    if (step === 1) return model.file && model.name && model.version && model.framework;
    if (step === 2) return arch.inputShape && arch.outputShape && arch.normMean && arch.normStd
                          && (arch.datasetId && arch.datasetId !== 'custom' || arch.customDataset);
    return true;
  };

  const handleRegister = async (weightsHash) => {
    setRegState('submitting');
    try {
      const datasetId = arch.datasetId === 'custom' ? arch.customDataset : arch.datasetId;
      const body = {
        tx_type:   'NODE_REGISTER_DNN',
        sender:    identity.address,
        nonce:     1,
        fee:       1.0,
        signature: 'dev',
        payload: {
          model_name:   model.name,
          architecture: {
            framework:   model.framework,
            input_shape: arch.inputShape,
            num_classes: parseInt(arch.outputShape, 10) || 10,
            notes:       arch.archNotes || '',
            norm_mean:   arch.normMean,
            norm_std:    arch.normStd,
          },
          weights_hash: weightsHash,
          endpoint:     identity.endpoint,
          dataset_id:   datasetId,
          public_key:   identity.publicKey,
        },
      };
      const res = await fetch(`${API_BASE}/tx/submit`, {
        method:  'POST',
        headers: {
          'Content-Type':             'application/json',
          'ngrok-skip-browser-warning': 'true',
        },
        body: JSON.stringify(body),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok || data.accepted === false) {
        setRegState('error');
      } else {
        setRegState('done');
      }
    } catch {
      setRegState('error');
    }
  };

  return (
    <div className="page-wrap">
      {/* Header */}
      <div className="jp-header">
        <div>
          <h2 className="page-title">Become a DNN Validator</h2>
          <p className="page-subtitle">
            Register your node and model checkpoint to join QoI consensus rounds
          </p>
        </div>
        <button className="btn btn-ghost" onClick={() => navigate('validators')}>
          ← View Validators
        </button>
      </div>

      {/* Progress stepper */}
      <div className="jp-stepper">
        {STEPS.map((s, i) => (
          <React.Fragment key={s}>
            <div className={`jp-step-dot-wrap ${i < step ? 'done' : i === step ? 'active' : 'pending'}`}>
              <div className="jp-step-dot">
                {i < step ? '✓' : i + 1}
              </div>
              <span className="jp-step-label">{s}</span>
            </div>
            {i < STEPS.length - 1 && (
              <div className={`jp-step-line ${i < step ? 'done' : ''}`} />
            )}
          </React.Fragment>
        ))}
      </div>

      {/* Step content */}
      <div className="jp-card card">
        <p className="section-title" style={{ marginBottom: 20 }}>{STEPS[step]}</p>

        {step === 0 && <StepIdentity data={identity} set={setIdentity} />}
        {step === 1 && <StepModel    data={model}    set={setModel} />}
        {step === 2 && <StepArch     data={arch}     set={setArch} />}
        {step === 3 && (
          <StepValidate
            identity={identity}
            model={model}
            arch={arch}
            result={valResult}
            setResult={setValResult}
            onRegister={handleRegister}
            regState={regState}
          />
        )}

        {/* Navigation */}
        <div className="jp-nav">
          {step > 0 && (
            <button className="btn btn-ghost" onClick={() => setStep(s => s - 1)}>
              ← Back
            </button>
          )}
          {step < STEPS.length - 1 && (
            <button
              className="btn btn-primary"
              onClick={() => setStep(s => s + 1)}
              disabled={!canAdvance()}
              style={{ marginLeft: 'auto' }}
            >
              Next →
            </button>
          )}
        </div>
      </div>

      {/* Info panel */}
      <div className="jp-info-grid">
        <div className="card jp-info-card">
          <p className="section-title">Registration Flow</p>
          <ol className="jp-info-list">
            <li>Fill in your node identity and endpoint.</li>
            <li>Upload your trained model checkpoint file.</li>
            <li>Specify input shape and normalization — used by peers to reproduce your preprocessing.</li>
            <li>Validation runs locally: size, loadability, latency benchmark.</li>
            <li>If approved, a <code>NODE_REGISTER_DNN</code> transaction is broadcast to the chain.</li>
            <li>Existing validators issue <code>MODEL_CHALLENGE</code> transactions — your node must respond correctly to pass PoM.</li>
            <li>Once PoM passes, your node becomes an active DNN validator earning rewards.</li>
          </ol>
        </div>

        <div className="card jp-info-card">
          <p className="section-title">Requirements</p>
          <div className="jp-req-list">
            {[
              ['Model format',    '.pt / .pth / .h5 / .onnx'],
              ['Task',           'CIFAR-10 compatible (or custom)'],
              ['Min accuracy',   '≥ 80% on validation split'],
              ['Max latency',    '< 500 ms per sample'],
              ['Endpoint',       'Must be publicly reachable'],
              ['Stake',          'Minimum stake required for proposal weight'],
            ].map(([k, v]) => (
              <div key={k} className="jp-req-row">
                <span className="jp-req-key">{k}</span>
                <span className="jp-req-val">{v}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────
export default function JoinPage({ navigate }) {
  const [advancedOpen, setAdvancedOpen] = useState(false);

  return (
    <div className="jp-root">
      {/* ── Hero ── */}
      <section className="jp-hero page-wrap">
        <div className="jp-hero-shell">
          <div className="jp-hero-kicker">Run a Node</div>
          <h1 className="jp-hero-title">
            Become a DNN Inference Node
          </h1>
          <p className="jp-hero-sub">
            Download the InferenceChain desktop app, train a model through a guided
            wizard, and submit your node to the network — no command line required.
          </p>
          <div className="jp-hero-actions">
            <a
              className="btn btn-primary btn-lg jp-download-btn"
              href={RELEASES_URL}
              target="_blank"
              rel="noreferrer"
            >
              <span className="jp-dl-icon">↓</span>
              Download for Windows
              <span className="jp-dl-sub">.exe installer · v0.1 preview</span>
            </a>
            <div className="jp-other-os">
              <a href={RELEASES_URL} target="_blank" rel="noreferrer" className="jp-os-link">macOS</a>
              <span className="jp-os-sep">·</span>
              <a href={RELEASES_URL} target="_blank" rel="noreferrer" className="jp-os-link">Linux</a>
              <span className="jp-os-sep jp-os-note">— coming soon</span>
            </div>
          </div>
        </div>
      </section>

      {/* ── How it works ── */}
      <section className="jp-section page-wrap">
        <div className="jp-section-head">
          <p className="section-title">How it works</p>
          <h2>From download to active node in three steps</h2>
        </div>
        <div className="jp-how-grid">
          {HOW_IT_WORKS.map((step) => (
            <div key={step.n} className="jp-how-card">
              <div className="jp-how-num">{step.n}</div>
              <div className="jp-how-icon">{step.icon}</div>
              <h3 className="jp-how-title">{step.title}</h3>
              <p className="jp-how-body">{step.body}</p>
            </div>
          ))}
        </div>
      </section>

      {/* ── App features ── */}
      <section className="jp-section jp-section-alt">
        <div className="page-wrap">
          <div className="jp-section-head">
            <p className="section-title">What's in the app</p>
            <h2>Everything handled for you — no ML engineering required</h2>
            <p className="jp-section-sub">
              The desktop app bundles a fully sandboxed Python training backend.
              You supply the architecture and dataset; the app takes care of the rest.
            </p>
          </div>
          <div className="jp-feat-grid">
            {APP_FEATURES.map((f) => (
              <div key={f.title} className="jp-feat-card card">
                <div className="jp-feat-icon">{f.icon}</div>
                <h3 className="jp-feat-title">{f.title}</h3>
                <p className="jp-feat-body">{f.body}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── System requirements ── */}
      <section className="jp-section page-wrap">
        <div className="jp-section-head">
          <p className="section-title">System requirements</p>
          <h2>What you need to run a node</h2>
        </div>
        <div className="jp-sysreq card">
          {SYSREQS.map((r) => (
            <div key={r.label} className="jp-sysreq-row">
              <span className="jp-sysreq-label">{r.label}</span>
              <span className="jp-sysreq-val">{r.value}</span>
            </div>
          ))}
        </div>
        <div className="jp-sysreq-note">
          Training runs entirely offline on your machine. Only the signed manifest
          (metadata + checkpoint hash, no raw weights) is ever sent to the network.
        </div>
      </section>

      {/* ── Advanced: manual registration ── */}
      <section className="jp-section page-wrap">
        <button
          className="jp-advanced-toggle"
          onClick={() => setAdvancedOpen((o) => !o)}
        >
          <span>Advanced: manual node registration</span>
          <span className="jp-adv-caret">{advancedOpen ? '▴' : '▾'}</span>
        </button>
        <p className="jp-advanced-hint">
          Already have a trained checkpoint and want to register directly via the
          chain API — without using the desktop app?
        </p>
        {advancedOpen && <AdvancedRegistrationForm navigate={navigate} />}
      </section>
    </div>
  );
}
