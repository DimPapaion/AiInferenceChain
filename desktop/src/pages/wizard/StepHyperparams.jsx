import React from 'react';
import '../WizardPage.css';
import './StepHyperparams.css';

const FIELDS = [
  {
    key: 'optimizer', label: 'Optimizer', type: 'select',
    options: ['adam', 'adamw', 'sgd'],
    hint: 'AdamW is a good default; SGD with momentum works well for image classification.',
  },
  {
    key: 'lr', label: 'Learning Rate', type: 'number',
    placeholder: '0.001',
    hint: 'Typical range: 1e-4 to 1e-2. Lower is safer with small datasets.',
  },
  {
    key: 'scheduler', label: 'LR Scheduler', type: 'select',
    options: ['none', 'cosine', 'step'],
    hint: 'Cosine annealing gradually reduces LR and usually improves final accuracy.',
  },
  {
    key: 'epochs', label: 'Epochs', type: 'number',
    placeholder: '30',
    hint: 'More epochs = more training time. 30–50 is typical for CIFAR-scale tasks.',
  },
  {
    key: 'batch_size', label: 'Batch Size', type: 'number',
    placeholder: '64',
    hint: 'Larger batches use more GPU memory but train faster per epoch.',
  },
  {
    key: 'weight_decay', label: 'Weight Decay', type: 'number',
    placeholder: '0.0001',
    hint: 'L2 regularisation. Ignored for plain SGD. Keep small (1e-4 to 1e-2).',
  },
  {
    key: 'augmentation', label: 'Data Augmentation', type: 'select',
    options: ['none', 'light', 'heavy'],
    hint: 'Light: crop + flip. Heavy: crop + flip + colour jitter + rotation.',
  },
  {
    key: 'loss', label: 'Loss Function', type: 'select',
    options: ['crossentropy', 'labelsmoothing', 'focalloss'],
    hint: 'CrossEntropy is standard. Label Smoothing reduces overconfidence. Focal Loss helps class imbalance.',
  },
];

export default function StepHyperparams({ next, back, config, setConfig, datasetInfo }) {
  const set = (key, value) => setConfig((c) => ({ ...c, [key]: value }));

  return (
    <div className="wstep-card">
      <div className="wstep-kicker">Step 3 of 5</div>
      <div className="wstep-title">Configure Training</div>
      <div className="wstep-subtitle">
        Set the hyperparameters for your training run. Hover any field hint for
        guidance. Everything can be changed and retrained later.
      </div>

      <div className="hp-grid">
        {FIELDS.map((f) => (
          <div className="wstep-field" key={f.key}>
            <label>{f.label}</label>
            {f.type === 'select' ? (
              <select value={config[f.key]} onChange={(e) => set(f.key, e.target.value)}>
                {f.options.map((o) => (
                  <option key={o} value={o}>{o}</option>
                ))}
              </select>
            ) : (
              <input
                type="text"
                inputMode="decimal"
                placeholder={f.placeholder}
                value={config[f.key]}
                onChange={(e) => set(f.key, e.target.value)}
              />
            )}
            <span className="hint">{f.hint}</span>
          </div>
        ))}
      </div>

      {datasetInfo?.num_classes && (
        <div className="wstep-status info" style={{ marginTop: 0 }}>
          Dataset has <strong>{datasetInfo.num_classes}</strong> classes — make sure
          your architecture's final layer outputs the same number of logits.
        </div>
      )}

      <div className="wstep-actions">
        <button className="btn-ghost" onClick={back}>← Back</button>
        <button className="btn-primary" onClick={next}>Start Training →</button>
      </div>
    </div>
  );
}
