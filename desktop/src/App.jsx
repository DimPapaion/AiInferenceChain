import React, { useState, useEffect } from 'react';
import './App.css';
import AppShell from './components/AppShell';
import WizardPage from './pages/WizardPage';
import DashboardPage from './pages/DashboardPage';
import WalletGatePage from './pages/WalletGatePage';
import { getUnlockedPriv } from './utils/wallet';

/**
 * Persistence key — once the user completes onboarding we remember it.
 * You can clear localStorage to reset to the wizard.
 */
const ONBOARDED_KEY = 'ic_onboarded';

export default function App() {
  const [onboarded, setOnboarded] = useState(
    () => localStorage.getItem(ONBOARDED_KEY) === 'true'
  );
  const [walletUnlocked, setWalletUnlocked] = useState(() => !!getUnlockedPriv());
  const [sidecarPort, setSidecarPort] = useState(47291);

  useEffect(() => {
    if (window.electronAPI) {
      window.electronAPI.getSidecarPort().then(setSidecarPort);
    }
  }, []);

  const handleOnboardingComplete = () => {
    localStorage.setItem(ONBOARDED_KEY, 'true');
    setOnboarded(true);
  };

  const apiBase = `http://127.0.0.1:${sidecarPort}`;

  return (
    <AppShell>
      {!walletUnlocked
        ? <WalletGatePage onUnlocked={() => setWalletUnlocked(true)} />
        : onboarded
          ? <DashboardPage apiBase={apiBase} />
          : <WizardPage apiBase={apiBase} onComplete={handleOnboardingComplete} />
      }
    </AppShell>
  );
}
