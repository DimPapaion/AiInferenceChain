import React, { useState, useEffect } from 'react';
import './App.css';
import AppShell from './components/AppShell';
import DashboardPage from './pages/DashboardPage';
import WalletGatePage from './pages/WalletGatePage';
import { getUnlockedPriv } from './utils/wallet';

export default function App() {
  const [walletUnlocked, setWalletUnlocked] = useState(() => !!getUnlockedPriv());
  const [sidecarPort, setSidecarPort] = useState(47291);

  useEffect(() => {
    if (window.electronAPI) {
      window.electronAPI.getSidecarPort().then(setSidecarPort);
    }
  }, []);

  const apiBase = `http://127.0.0.1:${sidecarPort}`;

  return (
    <AppShell>
      {!walletUnlocked
        ? <WalletGatePage onUnlocked={() => setWalletUnlocked(true)} />
        : <DashboardPage apiBase={apiBase} />
      }
    </AppShell>
  );
}
