import React, { useState } from 'react';
import './WizardPage.css';
import StepArchitecture from './wizard/StepArchitecture';
import StepDataset from './wizard/StepDataset';
import StepHyperparams from './wizard/StepHyperparams';
import StepTraining from './wizard/StepTraining';
import StepSubmit from './wizard/StepSubmit';

const STEPS = [
  { id: 'arch',        label: 'Architecture' },
  { id: 'dataset',     label: 'Dataset'      },
  { id: 'hyperparams', label: 'Configure'    },
  { id: 'training',    label: 'Train'        },
  { id: 'submit',      label: 'Join Network' },
];

export default function WizardPage({ apiBase, onComplete }) {
  const [step, setStep] = useState(0);

  // Shared state passed through the wizard
  const [archSource, setArchSource]     = useState('');
  const [archInfo, setArchInfo]         = useState(null);   // { model_name, output_shape }
  const [datasetInfo, setDatasetInfo]   = useState(null);   // validated dataset descriptor
  const [config, setConfig]             = useState({
    optimizer:    'adamw',
    lr:           '0.001',
    scheduler:    'cosine',
    epochs:       '30',
    batch_size:   '64',
    weight_decay: '0.0001',
    augmentation: 'light',
    loss:         'crossentropy',
  });
  const [trainingResult, setTrainingResult] = useState(null); // { checkpoint, metrics }

  const next = () => setStep((s) => Math.min(s + 1, STEPS.length - 1));
  const back = () => setStep((s) => Math.max(s - 1, 0));

  const stepProps = { apiBase, next, back };

  return (
    <div className="wizard-root">
      {/* Progress bar */}
      <div className="wizard-progress">
        {STEPS.map((s, i) => (
          <div
            key={s.id}
            className={`wizard-step-dot ${i < step ? 'done' : ''} ${i === step ? 'active' : ''}`}
          >
            <div className="wizard-dot-circle">
              {i < step ? '✓' : i + 1}
            </div>
            <span className="wizard-dot-label">{s.label}</span>
          </div>
        ))}
        <div
          className="wizard-progress-bar"
          style={{ width: `${(step / (STEPS.length - 1)) * 100}%` }}
        />
      </div>

      {/* Step content */}
      <div className="wizard-body">
        {step === 0 && (
          <StepArchitecture
            {...stepProps}
            archSource={archSource}
            setArchSource={setArchSource}
            archInfo={archInfo}
            setArchInfo={setArchInfo}
          />
        )}
        {step === 1 && (
          <StepDataset
            {...stepProps}
            archInfo={archInfo}
            datasetInfo={datasetInfo}
            setDatasetInfo={setDatasetInfo}
          />
        )}
        {step === 2 && (
          <StepHyperparams
            {...stepProps}
            config={config}
            setConfig={setConfig}
            datasetInfo={datasetInfo}
          />
        )}
        {step === 3 && (
          <StepTraining
            {...stepProps}
            archSource={archSource}
            archInfo={archInfo}
            datasetInfo={datasetInfo}
            config={config}
            trainingResult={trainingResult}
            setTrainingResult={setTrainingResult}
          />
        )}
        {step === 4 && (
          <StepSubmit
            {...stepProps}
            archSource={archSource}
            datasetInfo={datasetInfo}
            config={config}
            trainingResult={trainingResult}
            onComplete={onComplete}
          />
        )}
      </div>
    </div>
  );
}
