import React, { useMemo, useState } from 'react';
import './WalletGatePage.css';
import {
  createWalletFromMnemonic,
  createWalletFromPrivKey,
  generateMnemonic,
  isPasswordAcceptable,
  loadStoredWallet,
  setUnlockedPriv,
  shortAddress,
  unlockWallet,
  validateMnemonic,
  saveStoredWallet,
} from '../utils/wallet';

export default function WalletGatePage({ onUnlocked }) {
  const stored = useMemo(() => loadStoredWallet(), []);
  const [mode, setMode] = useState(stored ? 'unlock' : 'create');
  const [showMnemonic, setShowMnemonic] = useState(false);
  const [password, setPassword] = useState('');
  const [password2, setPassword2] = useState('');
  const [mnemonic, setMnemonic] = useState(() => generateMnemonic());
  const [privHex, setPrivHex] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const onCreate = async () => {
    if (!validateMnemonic(mnemonic)) return setError('Mnemonic is invalid.');
    if (!isPasswordAcceptable(password)) return setError('Password must be at least 8 characters.');
    if (password !== password2) return setError('Passwords do not match.');

    setBusy(true);
    setError('');
    try {
      const wallet = await createWalletFromMnemonic(mnemonic, password);
      saveStoredWallet(wallet);
      const unlocked = await unlockWallet(password);
      setUnlockedPriv(unlocked);
      onUnlocked();
    } catch (e) {
      setError(e.message || 'Failed to create wallet.');
    } finally {
      setBusy(false);
    }
  };

  const onImport = async () => {
    if (!isPasswordAcceptable(password)) return setError('Password must be at least 8 characters.');
    if (password !== password2) return setError('Passwords do not match.');

    setBusy(true);
    setError('');
    try {
      const wallet = await createWalletFromPrivKey(privHex, password);
      saveStoredWallet(wallet);
      const unlocked = await unlockWallet(password);
      setUnlockedPriv(unlocked);
      onUnlocked();
    } catch (e) {
      setError(e.message || 'Failed to import wallet.');
    } finally {
      setBusy(false);
    }
  };

  const onUnlock = async () => {
    setBusy(true);
    setError('');
    try {
      const unlocked = await unlockWallet(password);
      setUnlockedPriv(unlocked);
      onUnlocked();
    } catch (e) {
      setError(e.message || 'Unlock failed.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="wg-root">
      <div className="wg-brand-bg">InferenceChain</div>
      <div className="wg-card">
        <div className="wg-title">Welcome to InferenceChain Desktop</div>
        <div className="wg-sub">Secure your node identity first, then continue to onboarding and training.</div>

        {stored && (
          <div className="wg-stored">
            Existing wallet: <span data-selectable>{shortAddress(stored.address)}</span>
          </div>
        )}

        <div className="wg-tabs">
          {stored && (
            <button className={`wg-tab ${mode === 'unlock' ? 'active' : ''}`} onClick={() => { setMode('unlock'); setError(''); }}>
              Unlock
            </button>
          )}
          <button className={`wg-tab ${mode === 'create' ? 'active' : ''}`} onClick={() => { setMode('create'); setError(''); }}>
            Create Wallet
          </button>
          <button className={`wg-tab ${mode === 'import' ? 'active' : ''}`} onClick={() => { setMode('import'); setError(''); }}>
            Import Key
          </button>
        </div>

        {mode === 'unlock' && (
          <div className="wg-body">
            <label>Password</label>
            <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder="Enter wallet password" />
            <button className="wg-primary" disabled={busy || !password} onClick={onUnlock}>
              {busy ? 'Unlocking...' : 'Unlock and Continue'}
            </button>
          </div>
        )}

        {mode === 'create' && (
          <div className="wg-body">
            <label>Mnemonic (12 words)</label>
            <textarea
              className={showMnemonic ? '' : 'wg-secret'}
              value={mnemonic}
              onChange={(e) => setMnemonic(e.target.value)}
              rows={3}
            />
            <div className="wg-row">
              <button className="wg-ghost" onClick={() => setMnemonic(generateMnemonic())}>Regenerate</button>
              <button className="wg-ghost" onClick={() => setShowMnemonic((v) => !v)}>
                {showMnemonic ? 'Hide phrase' : 'Reveal phrase'}
              </button>
            </div>
            <div className="wg-hint">By default the phrase is blurred. Reveal only when you are ready to back it up.</div>

            <label>New Password</label>
            <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder="At least 8 characters" />
            <label>Confirm Password</label>
            <input type="password" value={password2} onChange={(e) => setPassword2(e.target.value)} placeholder="Repeat password" />

            <button className="wg-primary" disabled={busy} onClick={onCreate}>
              {busy ? 'Creating...' : 'Create Wallet and Continue'}
            </button>
          </div>
        )}

        {mode === 'import' && (
          <div className="wg-body">
            <label>Private Key (hex, 64 chars)</label>
            <input value={privHex} onChange={(e) => setPrivHex(e.target.value)} placeholder="e.g. 5f2a..." />
            <label>New Password</label>
            <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder="At least 8 characters" />
            <label>Confirm Password</label>
            <input type="password" value={password2} onChange={(e) => setPassword2(e.target.value)} placeholder="Repeat password" />

            <button className="wg-primary" disabled={busy} onClick={onImport}>
              {busy ? 'Importing...' : 'Import Wallet and Continue'}
            </button>
          </div>
        )}

        {error && <div className="wg-error">{error}</div>}
      </div>
    </div>
  );
}
