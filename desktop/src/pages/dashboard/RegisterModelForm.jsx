import React, { useRef, useState } from 'react';
import './RegisterModelForm.css';

const STEPS = ['Identity', 'Model File', 'Architecture', 'Validate & Register'];

const DATASETS = [
  { value: 'cifar10', label: 'CIFAR-10 (32x32, 10 classes)' },
  { value: 'cifar100', label: 'CIFAR-100 (32x32, 100 classes)' },
  { value: 'imagenet_subset', label: 'ImageNet Subset' },
  { value: 'mnist', label: 'MNIST (28x28, 10 classes)' },
  { value: 'custom', label: 'Custom Dataset' },
];

const FRAMEWORKS = [
  { value: 'pytorch', label: 'PyTorch (.pt / .pth)' },
  { value: 'tensorflow', label: 'TensorFlow / Keras (.h5)' },
  { value: 'onnx', label: 'ONNX (.onnx)' },
];

const DATASET_DEFAULTS = {
  cifar10: { mean: '0.4914, 0.4822, 0.4465', std: '0.2023, 0.1994, 0.2010', inputShape: '3, 32, 32', outputShape: '10' },
  cifar100: { mean: '0.5071, 0.4865, 0.4409', std: '0.2673, 0.2564, 0.2762', inputShape: '3, 32, 32', outputShape: '100' },
  mnist: { mean: '0.1307', std: '0.3081', inputShape: '1, 28, 28', outputShape: '10' },
};

function Field({ label, hint, required, children }) {
  return (
    <div className="rmf-field">
      <label className="rmf-label">
        {label}
        {required && <span className="rmf-required">*</span>}
        {hint && <span className="rmf-hint">{hint}</span>}
      </label>
      {children}
    </div>
  );
}

function Input({ value, onChange, placeholder, mono, type = 'text' }) {
  return (
    <input
      className={`rmf-input ${mono ? 'mono' : ''}`}
      type={type}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      placeholder={placeholder}
    />
  );
}

function Select({ value, onChange, options }) {
  return (
    <select className="rmf-input" value={value} onChange={(e) => onChange(e.target.value)}>
      <option value="">Select...</option>
      {options.map((o) => (
        <option key={o.value} value={o.value}>{o.label}</option>
      ))}
    </select>
  );
}

function StepIdentity({ data, set }) {
  return (
    <div className="rmf-step-body">
      <Field label="Wallet Address" required hint="Becomes your node_id on-chain">
        <Input mono value={data.address} onChange={(v) => set('address', v)} placeholder="0x0000..." />
      </Field>

      <Field label="Node Endpoint URL" required hint="Public URL peers call for inference">
        <Input value={data.endpoint} onChange={(v) => set('endpoint', v)} placeholder="https://your-node.example.com:8000" />
      </Field>

      <Field label="Public Key (hex)" required hint="Ed25519 or secp256k1 public key">
        <Input mono value={data.publicKey} onChange={(v) => set('publicKey', v)} placeholder="04a1b2..." />
      </Field>

      <Field label="Initial Stake (tokens)" hint="Submitted as separate STAKE tx after registration">
        <Input value={data.stake} onChange={(v) => set('stake', v)} placeholder="100" />
      </Field>
    </div>
  );
}

function StepModel({ data, set }) {
  const fileRef = useRef(null);

  const handleFile = (e) => {
    const f = e.target.files?.[0];
    if (f) set('file', f);
  };

  return (
    <div className="rmf-step-body">
      <div className={`rmf-dropzone ${data.file ? 'has-file' : ''}`} onClick={() => fileRef.current?.click()}>
        {data.file ? (
          <div className="rmf-file-chosen">
            <div>
              <div className="rmf-file-name">{data.file.name}</div>
              <div className="rmf-file-size">{(data.file.size / 1024 / 1024).toFixed(2)} MB</div>
            </div>
            <button className="btn-ghost" onClick={(e) => { e.stopPropagation(); set('file', null); }}>Remove</button>
          </div>
        ) : (
          <div className="rmf-dz-inner">
            <span>Drop your model file or click to browse</span>
            <small>.pt .pth .h5 .onnx</small>
          </div>
        )}
        <input ref={fileRef} type="file" accept=".pt,.pth,.h5,.hdf5,.onnx" onChange={handleFile} style={{ display: 'none' }} />
      </div>

      <div className="rmf-row-2">
        <Field label="Model Name" required>
          <Input value={data.name} onChange={(v) => set('name', v)} placeholder="resnet20-cifar10" />
        </Field>
        <Field label="Version" required>
          <Input value={data.version} onChange={(v) => set('version', v)} placeholder="1.0.0" />
        </Field>
      </div>

      <Field label="Framework" required>
        <Select value={data.framework} onChange={(v) => set('framework', v)} options={FRAMEWORKS} />
      </Field>

      <Field label="Description">
        <textarea className="rmf-input" value={data.description} onChange={(e) => set('description', e.target.value)} rows={3} placeholder="Training details..." />
      </Field>
    </div>
  );
}

function StepArch({ data, set }) {
  const fillDefaults = (datasetId) => {
    set('datasetId', datasetId);
    const d = DATASET_DEFAULTS[datasetId];
    if (d) {
      set('normMean', d.mean);
      set('normStd', d.std);
      set('inputShape', d.inputShape);
      set('outputShape', d.outputShape);
    }
  };

  return (
    <div className="rmf-step-body">
      <Field label="Dataset" required>
        <Select value={data.datasetId} onChange={fillDefaults} options={DATASETS} />
      </Field>
      {data.datasetId === 'custom' && (
        <Field label="Custom Dataset Name" required>
          <Input value={data.customDataset} onChange={(v) => set('customDataset', v)} placeholder="my-dataset-v1" />
        </Field>
      )}

      <div className="rmf-row-2">
        <Field label="Input Shape" required hint="C, H, W">
          <Input mono value={data.inputShape} onChange={(v) => set('inputShape', v)} placeholder="3, 32, 32" />
        </Field>
        <Field label="Output Classes" required>
          <Input mono value={data.outputShape} onChange={(v) => set('outputShape', v)} placeholder="10" />
        </Field>
      </div>

      <div className="rmf-row-2">
        <Field label="Normalization Mean" required>
          <Input mono value={data.normMean} onChange={(v) => set('normMean', v)} placeholder="0.4914, 0.4822, 0.4465" />
        </Field>
        <Field label="Normalization Std" required>
          <Input mono value={data.normStd} onChange={(v) => set('normStd', v)} placeholder="0.2023, 0.1994, 0.2010" />
        </Field>
      </div>

      <div className="rmf-row-2">
        <Field label="Min Accuracy Threshold">
          <Input value={data.minAccuracy} onChange={(v) => set('minAccuracy', v)} placeholder="0.80" />
        </Field>
        <Field label="Max Latency (ms)">
          <Input value={data.maxLatency} onChange={(v) => set('maxLatency', v)} placeholder="500" />
        </Field>
      </div>

      <Field label="Architecture Notes">
        <textarea className="rmf-input" value={data.archNotes} onChange={(e) => set('archNotes', e.target.value)} rows={3} placeholder='{"layers": 20, "block": "BasicBlock"}' />
      </Field>
    </div>
  );
}

function StepValidate({ chainEndpoint, identity, model, arch, result, setResult, onRegister, regState }) {
  const [validating, setValidating] = useState(false);
  const [error, setError] = useState('');

  const runValidation = async () => {
    setValidating(true);
    setError('');
    setResult(null);

    const form = new FormData();
    form.append('file', model.file);
    form.append('name', model.name);
    form.append('version', model.version);
    form.append('framework', model.framework);
    form.append('description', model.description || '');
    form.append('input_shape', arch.inputShape);
    form.append('output_shape', arch.outputShape);
    form.append('min_accuracy', arch.minAccuracy || '0');
    form.append('max_latency_ms', arch.maxLatency || '1000');
    form.append('max_size_mb', '1000');
    form.append('dataset_id', arch.datasetId === 'custom' ? arch.customDataset : arch.datasetId);
    form.append('normalization_mean', arch.normMean || '');
    form.append('normalization_std', arch.normStd || '');
    form.append('architecture_notes', arch.archNotes || '');

    try {
      const res = await fetch(`${chainEndpoint}/dashboard/models/upload`, {
        method: 'POST',
        headers: { 'ngrok-skip-browser-warning': 'true' },
        body: form,
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || `Upload failed: HTTP ${res.status}`);
      setResult(data);
    } catch (e) {
      setError(e.message || 'Validation failed');
    } finally {
      setValidating(false);
    }
  };

  const canRegister = result?.status === 'approved';

  return (
    <div className="rmf-step-body">
      <div className="rmf-summary">
        <div className="rmf-sum-row"><span>Address</span><span className="mono">{identity.address || '—'}</span></div>
        <div className="rmf-sum-row"><span>Endpoint</span><span className="mono">{identity.endpoint || '—'}</span></div>
        <div className="rmf-sum-row"><span>Model</span><span>{model.name} v{model.version} ({model.framework})</span></div>
        <div className="rmf-sum-row"><span>Dataset</span><span>{arch.datasetId}</span></div>
      </div>

      {!result && (
        <button className="btn-primary" onClick={runValidation} disabled={validating}>
          {validating ? 'Validating model...' : 'Run Validation'}
        </button>
      )}

      {error && <div className="train-status-err">{error}</div>}

      {result && (
        <>
          <div className={result.status === 'approved' ? 'train-status-ok' : 'train-status-err'}>
            {result.status === 'approved' ? 'Validation passed' : 'Validation failed'}: {result.message}
          </div>

          {result.checks?.length > 0 && (
            <div className="rmf-checks">
              {result.checks.map((c, i) => (
                <div key={i} className="rmf-check">{c}</div>
              ))}
            </div>
          )}

          {result.weights_hash && (
            <div className="rmf-hash-row">
              <span>SHA-256</span>
              <span className="mono" data-selectable>{result.weights_hash}</span>
            </div>
          )}

          <div className="rmf-actions">
            <button className="btn-ghost" onClick={() => setResult(null)}>Re-validate</button>
            {canRegister && (
              <button className="btn-primary" onClick={() => onRegister(result.weights_hash)} disabled={regState === 'submitting'}>
                {regState === 'submitting' ? 'Submitting...' : 'Register on Chain'}
              </button>
            )}
          </div>

          {regState === 'done' && <div className="train-status-ok">NODE_REGISTER_DNN submitted. Node is pending PoM verification.</div>}
          {regState === 'error' && <div className="train-status-err">Registration failed. Check node endpoint and chain status.</div>}
        </>
      )}
    </div>
  );
}

export default function RegisterModelForm({ defaultPublicKey = '' }) {
  const [step, setStep] = useState(0);
  const [chainEndpoint, setChainEndpoint] = useState('http://localhost:8000');

  const [identity, setIdentityRaw] = useState({
    address: localStorage.getItem('ic_pubkey') || '',
    endpoint: '',
    publicKey: defaultPublicKey,
    stake: '100',
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

  const [valResult, setValResult] = useState(null);
  const [regState, setRegState] = useState('idle');

  const setIdentity = (k, v) => setIdentityRaw((p) => ({ ...p, [k]: v }));
  const setModel = (k, v) => setModelRaw((p) => ({ ...p, [k]: v }));
  const setArch = (k, v) => setArchRaw((p) => ({ ...p, [k]: v }));

  const canAdvance = () => {
    if (step === 0) return identity.address && identity.endpoint && identity.publicKey;
    if (step === 1) return model.file && model.name && model.version && model.framework;
    if (step === 2) {
      const customOk = arch.datasetId !== 'custom' || !!arch.customDataset;
      return arch.inputShape && arch.outputShape && arch.normMean && arch.normStd && customOk;
    }
    return true;
  };

  const handleRegister = async (weightsHash) => {
    setRegState('submitting');
    try {
      const datasetId = arch.datasetId === 'custom' ? arch.customDataset : arch.datasetId;
      const body = {
        tx_type: 'NODE_REGISTER_DNN',
        sender: identity.address,
        nonce: 1,
        fee: 1.0,
        signature: 'dev',
        payload: {
          model_name: model.name,
          architecture: {
            framework: model.framework,
            input_shape: arch.inputShape,
            num_classes: parseInt(arch.outputShape, 10) || 10,
            notes: arch.archNotes || '',
            norm_mean: arch.normMean,
            norm_std: arch.normStd,
          },
          weights_hash: weightsHash,
          endpoint: identity.endpoint,
          dataset_id: datasetId,
          public_key: identity.publicKey,
        },
      };

      const res = await fetch(`${chainEndpoint}/tx/submit`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
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
    <div className="card train-register-card">
      <div className="train-register-title">Register Model as DNN Node</div>
      <div className="train-register-sub">This is the same flow as the website Run a Node advanced registration.</div>

      <Field label="Chain API Endpoint" required hint="Node REST endpoint hosting /dashboard and /tx routes">
        <Input value={chainEndpoint} onChange={setChainEndpoint} placeholder="http://localhost:8000" />
      </Field>

      <div className="rmf-stepper">
        {STEPS.map((s, i) => (
          <div key={s} className={`rmf-step-pill ${i === step ? 'active' : i < step ? 'done' : ''}`}>
            {i < step ? '✓' : i + 1} {s}
          </div>
        ))}
      </div>

      {step === 0 && <StepIdentity data={identity} set={setIdentity} />}
      {step === 1 && <StepModel data={model} set={setModel} />}
      {step === 2 && <StepArch data={arch} set={setArch} />}
      {step === 3 && (
        <StepValidate
          chainEndpoint={chainEndpoint}
          identity={identity}
          model={model}
          arch={arch}
          result={valResult}
          setResult={setValResult}
          onRegister={handleRegister}
          regState={regState}
        />
      )}

      <div className="rmf-nav">
        {step > 0 && <button className="btn-ghost" onClick={() => setStep((s) => s - 1)}>Back</button>}
        {step < STEPS.length - 1 && (
          <button className="btn-primary" onClick={() => setStep((s) => s + 1)} disabled={!canAdvance()}>
            Next
          </button>
        )}
      </div>
    </div>
  );
}
