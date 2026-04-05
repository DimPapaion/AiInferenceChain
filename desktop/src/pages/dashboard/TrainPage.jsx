import React, { useEffect, useState } from 'react';
import '../DashboardPage.css';
import WizardPage from '../WizardPage';
import { loadStoredWallet } from '../../utils/wallet';
import RegisterModelForm from './RegisterModelForm';

export default function TrainPage({ apiBase, initialMode = 'new' }) {
  const [mode, setMode] = useState(initialMode);
  const [pubKey, setPubKey] = useState('');

  useEffect(() => {
    setMode(initialMode);
  }, [initialMode]);

  useEffect(() => {
    const wallet = loadStoredWallet();
    if (wallet?.publicKey) setPubKey(wallet.publicKey);
  }, []);

  return (
    <div>
      <div className="dash-panel-title">Train & Register</div>
      <div className="dash-panel-sub">Train a new model or register a pre-trained model to become a DNN node.</div>

      <div className="train-switch">
        <button className={`dash-nav-btn-lite ${mode === 'new' ? 'active' : ''}`} onClick={() => setMode('new')}>
          Train New Model
        </button>
        <button className={`dash-nav-btn-lite ${mode === 'register' ? 'active' : ''}`} onClick={() => setMode('register')}>
          Register Existing Model
        </button>
      </div>

      {mode === 'new' ? (
        <WizardPage apiBase={apiBase} onComplete={() => localStorage.setItem('ic_onboarded', 'true')} />
      ) : (
        <RegisterModelForm defaultPublicKey={pubKey} />
      )}
    </div>
  );
}
