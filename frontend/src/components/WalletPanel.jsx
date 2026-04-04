import React, { useEffect, useRef, useState, useCallback } from 'react';
import './WalletPanel.css';
import {
  generateMnemonic, validateMnemonic,
  createWalletFromMnemonic, createWalletFromPrivKey, recoverWalletFromMnemonic,
  unlockWallet,
  saveStoredWallet, loadStoredWallet, clearStoredWallet,
  buildTransferTx, passwordStrength, isPasswordAcceptable,
  shortAddr, formatInfer,
} from '../utils/wallet';
import { state as stateApi, tx as txApi, wallet as walletApi } from '../api/client';

// ── Panel states ──────────────────────────────────────────────────────────────
const S_NO_WALLET   = 'no_wallet';
const S_MNEMONIC    = 'mnemonic';    // show mnemonic to user before setting password
const S_SET_PASS    = 'set_pass';    // choose password (after mnemonic backup)
const S_LOCKED      = 'locked';      // wallet exists, needs password
const S_UNLOCKED    = 'unlocked';    // decrypted, full UI
const S_RECOVER     = 'recover';     // enter mnemonic to recover
const S_IMPORT_KEY  = 'import_key';  // import from raw private key

const TAB_ACCOUNT = 'account';
const TAB_SEND    = 'send';
const TAB_HISTORY = 'history';
const TAB_KEYS    = 'keys';

// ── Small shared components ───────────────────────────────────────────────────

function CopyBtn({ text }) {
  const [copied, setCopied] = useState(false);
  const copy = () => {
    navigator.clipboard.writeText(text).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    });
  };
  return (
    <button className="wp-copy-btn" onClick={copy} title="Copy">{copied ? '✓' : '⎘'}</button>
  );
}

function PasswordInput({ value, onChange, placeholder = 'Password…', showStrength = false }) {
  const [show, setShow] = useState(false);
  const str = showStrength ? passwordStrength(value) : null;
  return (
    <div className="wp-pass-wrap">
      <div className="wp-pass-row">
        <input
          className="wp-input"
          type={show ? 'text' : 'password'}
          placeholder={placeholder}
          value={value}
          onChange={e => onChange(e.target.value)}
          autoComplete="new-password"
        />
        <button className="wp-icon-btn" onClick={() => setShow(s => !s)} type="button">
          {show ? '🙈' : '👁'}
        </button>
      </div>
      {showStrength && value && (
        <div className="wp-strength">
          <div className="wp-strength-bar">
            {[1,2,3,4,5].map(i => (
              <div
                key={i}
                className="wp-strength-seg"
                style={{ background: str.score >= i ? str.color : 'var(--border-md)' }}
              />
            ))}
          </div>
          <span className="wp-strength-label" style={{ color: str.color }}>{str.label}</span>
        </div>
      )}
    </div>
  );
}

function TxRow({ tx, myAddress }) {
  const isSend  = tx.sender === myAddress;
  const amount  = tx.payload?.amount ?? 0;
  const peer    = isSend ? tx.recipient : tx.sender;
  const sign    = isSend ? '-' : '+';
  const typeLabel = (tx.tx_type || '').replace(/_/g, ' ');
  return (
    <div className={`wp-tx-row ${isSend ? 'tx-out' : 'tx-in'}`}>
      <div className="wp-tx-left">
        <span className="wp-tx-type">{typeLabel}</span>
        <span className="wp-tx-peer">{peer ? shortAddr(peer) : '—'}</span>
      </div>
      <div className="wp-tx-right">
        <span className="wp-tx-amount">{sign}{formatInfer(amount)} INFER</span>
        {tx.block_height != null && <span className="wp-tx-block">block #{tx.block_height}</span>}
      </div>
    </div>
  );
}

// ── Main panel ────────────────────────────────────────────────────────────────

export default function WalletPanel({ open, onClose }) {
  const panelRef = useRef();

  // Panel state machine
  const stored = loadStoredWallet();
  const [panelState, setPanelState] = useState(stored ? S_LOCKED : S_NO_WALLET);

  // In-memory only (never persisted)
  const [privateKeyHex, setPrivateKeyHex] = useState(null);

  // Stored wallet metadata (address, publicKey)
  const [walletMeta, setWalletMeta] = useState(stored);

  // Setup flow state
  const [mnemonic,      setMnemonic]      = useState('');
  const [mnemonicWords, setMnemonicWords] = useState([]);
  const [mnemonicConfirmed, setMnemonicConfirmed] = useState(false);
  const [password,      setPassword]      = useState('');
  const [password2,     setPassword2]     = useState('');
  const [passError,     setPassError]     = useState('');

  // Unlock state
  const [unlockPass,  setUnlockPass]  = useState('');
  const [unlockError, setUnlockError] = useState('');
  const [unlocking,   setUnlocking]   = useState(false);

  // Recovery state
  const [recoverPhrase, setRecoverPhrase] = useState('');
  const [recoverPass,   setRecoverPass]   = useState('');
  const [recoverPass2,  setRecoverPass2]  = useState('');
  const [recoverError,  setRecoverError]  = useState('');
  const [recovering,    setRecovering]    = useState(false);

  // Import key state
  const [importKey,   setImportKey]   = useState('');
  const [importPass,  setImportPass]  = useState('');
  const [importPass2, setImportPass2] = useState('');
  const [importError, setImportError] = useState('');
  const [importing,   setImporting]   = useState(false);

  // Unlocked tab state
  const [tab,     setTab]     = useState(TAB_ACCOUNT);
  const [account, setAccount] = useState(null);
  const [acctLoad, setAcctLoad] = useState(false);

  // Send
  const [sendTo,     setSendTo]     = useState('');
  const [sendAmt,    setSendAmt]    = useState('');
  const [sendFee,    setSendFee]    = useState('0.1');
  const [sendStatus, setSendStatus] = useState(null);

  // History
  const [history,  setHistory]  = useState([]);
  const [histLoad, setHistLoad] = useState(false);

  // Faucet
  const [faucetStatus, setFaucetStatus] = useState(null);

  // ── Re-sync panel state when opened ────────────────────────────────────────
  useEffect(() => {
    if (open) {
      const s = loadStoredWallet();
      if (!s) {
        setPanelState(S_NO_WALLET);
        setWalletMeta(null);
      } else if (panelState === S_NO_WALLET) {
        setPanelState(S_LOCKED);
        setWalletMeta(s);
      }
    }
  }, [open, panelState]);

  // ── Close on outside click ──────────────────────────────────────────────────
  useEffect(() => {
    if (!open) return;
    const handler = e => {
      if (panelRef.current && !panelRef.current.contains(e.target)) onClose();
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [open, onClose]);

  // ── Account refresh ─────────────────────────────────────────────────────────
  const refreshAccount = useCallback(async () => {
    if (!walletMeta) return;
    setAcctLoad(true);
    try {
      const data = await stateApi.balance(walletMeta.address);
      setAccount(data);
    } catch { setAccount(null); }
    finally  { setAcctLoad(false); }
  }, [walletMeta]);

  useEffect(() => {
    if (panelState === S_UNLOCKED && tab === TAB_ACCOUNT) refreshAccount();
  }, [panelState, tab, refreshAccount]);

  // ── History refresh ─────────────────────────────────────────────────────────
  const refreshHistory = useCallback(async () => {
    if (!walletMeta) return;
    setHistLoad(true);
    try {
      const data = await walletApi.history(walletMeta.address);
      setHistory(data);
    } catch { setHistory([]); }
    finally  { setHistLoad(false); }
  }, [walletMeta]);

  useEffect(() => {
    if (panelState === S_UNLOCKED && tab === TAB_HISTORY) refreshHistory();
  }, [panelState, tab, refreshHistory]);

  // ── Setup: generate mnemonic ────────────────────────────────────────────────
  const handleStartGenerate = () => {
    const m = generateMnemonic();
    setMnemonic(m);
    setMnemonicWords(m.split(' '));
    setMnemonicConfirmed(false);
    setPassword(''); setPassword2(''); setPassError('');
    setPanelState(S_MNEMONIC);
  };

  const handleMnemonicNext = () => {
    setPanelState(S_SET_PASS);
  };

  // ── Setup: set password ─────────────────────────────────────────────────────
  const handleCreateWallet = async () => {
    setPassError('');
    if (!isPasswordAcceptable(password)) {
      setPassError('Password is too weak (min 8 chars, use mixed characters)');
      return;
    }
    if (password !== password2) {
      setPassError('Passwords do not match');
      return;
    }
    try {
      const record = await createWalletFromMnemonic(mnemonic, password);
      saveStoredWallet(record);
      setWalletMeta(record);
      setPrivateKeyHex(await unlockWallet(password)); // decrypt immediately into memory
      setPassword(''); setPassword2('');
      setMnemonic(''); setMnemonicWords([]);
      setPanelState(S_UNLOCKED);
      setTab(TAB_ACCOUNT);
      onClose(); // trigger NavBar to re-read address
      setTimeout(onClose, 0); // ensure close callback fires
    } catch (e) {
      setPassError(e.message);
    }
  };

  // ── Unlock ──────────────────────────────────────────────────────────────────
  const handleUnlock = async () => {
    setUnlockError('');
    setUnlocking(true);
    try {
      const privKey = await unlockWallet(unlockPass);
      setPrivateKeyHex(privKey);
      setUnlockPass('');
      setPanelState(S_UNLOCKED);
      setTab(TAB_ACCOUNT);
    } catch (e) {
      setUnlockError(e.message);
    } finally {
      setUnlocking(false);
    }
  };

  // ── Lock ────────────────────────────────────────────────────────────────────
  const handleLock = () => {
    setPrivateKeyHex(null);
    setAccount(null);
    setHistory([]);
    setFaucetStatus(null);
    setPanelState(S_LOCKED);
  };

  // ── Recovery ────────────────────────────────────────────────────────────────
  const handleRecover = async () => {
    setRecoverError('');
    setRecovering(true);
    try {
      if (!validateMnemonic(recoverPhrase)) throw new Error('Invalid recovery phrase');
      if (!isPasswordAcceptable(recoverPass)) throw new Error('Password too weak');
      if (recoverPass !== recoverPass2) throw new Error('Passwords do not match');
      const record = await recoverWalletFromMnemonic(recoverPhrase.trim().toLowerCase(), recoverPass);
      saveStoredWallet(record);
      setWalletMeta(record);
      const privKey = await unlockWallet(recoverPass);
      setPrivateKeyHex(privKey);
      setRecoverPhrase(''); setRecoverPass(''); setRecoverPass2('');
      setPanelState(S_UNLOCKED);
      setTab(TAB_ACCOUNT);
    } catch (e) {
      setRecoverError(e.message);
    } finally {
      setRecovering(false);
    }
  };

  // ── Import raw key ──────────────────────────────────────────────────────────
  const handleImportKey = async () => {
    setImportError('');
    setImporting(true);
    try {
      if (!isPasswordAcceptable(importPass)) throw new Error('Password too weak (min 8 chars)');
      if (importPass !== importPass2) throw new Error('Passwords do not match');
      const record = await createWalletFromPrivKey(importKey, importPass);
      saveStoredWallet(record);
      setWalletMeta(record);
      const privKey = await unlockWallet(importPass);
      setPrivateKeyHex(privKey);
      setImportKey(''); setImportPass(''); setImportPass2('');
      setPanelState(S_UNLOCKED);
      setTab(TAB_ACCOUNT);
    } catch (e) {
      setImportError(e.message);
    } finally {
      setImporting(false);
    }
  };

  // ── Faucet ──────────────────────────────────────────────────────────────────
  const handleFaucet = async () => {
    if (!walletMeta) return;
    setFaucetStatus({ ok: null, msg: 'Requesting…' });
    try {
      const res = await walletApi.faucet(walletMeta.address);
      setFaucetStatus({ ok: res.success, msg: res.message });
      if (res.success) refreshAccount();
    } catch (e) {
      setFaucetStatus({ ok: false, msg: e.message });
    }
  };

  // ── Send ────────────────────────────────────────────────────────────────────
  const handleSend = async () => {
    setSendStatus(null);
    const to  = sendTo.trim().toLowerCase();
    const amt = parseFloat(sendAmt);
    const fee = parseFloat(sendFee) || 0;
    if (to.length !== 40 || !/^[0-9a-f]+$/.test(to)) {
      setSendStatus({ ok: false, msg: 'Invalid recipient address (40 hex chars)' }); return;
    }
    if (!amt || amt <= 0) {
      setSendStatus({ ok: false, msg: 'Enter a valid amount' }); return;
    }
    if (!account || account.balance < amt + fee) {
      setSendStatus({ ok: false, msg: `Insufficient balance` }); return;
    }
    setSendStatus({ ok: null, msg: 'Submitting…' });
    try {
      const nonce = (account.nonce || 0) + 1;
      const built = buildTransferTx(walletMeta.address, privateKeyHex, to, amt, fee, nonce);
      const res   = await txApi.submit(built);
      if (res.accepted) {
        setSendStatus({ ok: true, msg: `Submitted — ${res.tx_id.slice(0,12)}…` });
        setSendTo(''); setSendAmt('');
        setAccount(a => a ? { ...a, balance: a.balance - amt - fee, nonce } : a);
      } else {
        setSendStatus({ ok: false, msg: res.reason || 'Rejected by node' });
      }
    } catch (e) {
      setSendStatus({ ok: false, msg: e.message });
    }
  };

  // ── Render helpers ──────────────────────────────────────────────────────────

  const renderHeader = (title, showLock = false) => (
    <div className="wp-header">
      <div className="wp-header-left">
        <span className="wp-header-icon">⬡</span>
        <span className="wp-header-title">{title}</span>
        {walletMeta && panelState === S_UNLOCKED && (
          <span className="wp-header-addr">{shortAddr(walletMeta.address)}</span>
        )}
      </div>
      <div className="wp-header-right">
        {showLock && (
          <button className="wp-icon-btn" onClick={handleLock} title="Lock wallet">🔒</button>
        )}
        <button className="wp-close-btn" onClick={onClose} aria-label="Close">✕</button>
      </div>
    </div>
  );

  // ── S_NO_WALLET ─────────────────────────────────────────────────────────────
  const renderNoWallet = () => (
    <>
      {renderHeader('Create Wallet')}
      <div className="wp-body wp-center">
        <div className="wp-hero-icon">⬡</div>
        <h3 className="wp-section-title">Your InferenceChain Wallet</h3>
        <p className="wp-muted">Generate a new wallet with a 12-word recovery phrase, or restore an existing one.</p>
        <button className="btn wp-btn-primary" onClick={handleStartGenerate}>
          Generate New Wallet
        </button>
        <div className="wp-or-divider"><span>or</span></div>
        <button className="btn wp-btn-ghost" onClick={() => { setRecoverPhrase(''); setRecoverError(''); setPanelState(S_RECOVER); }}>
          Recover from Phrase
        </button>
        <button className="btn wp-btn-ghost wp-ghost-sm" onClick={() => { setImportKey(''); setImportError(''); setPanelState(S_IMPORT_KEY); }}>
          Import Private Key
        </button>
      </div>
    </>
  );

  // ── S_MNEMONIC ──────────────────────────────────────────────────────────────
  const renderMnemonic = () => (
    <>
      {renderHeader('Backup Phrase')}
      <div className="wp-body">
        <div className="wp-alert-box">
          <span className="wp-alert-icon">⚠</span>
          Write down these 12 words in order. This is the <strong>only way</strong> to recover your wallet if you forget your password. Never share it with anyone.
        </div>
        <div className="wp-mnemonic-grid">
          {mnemonicWords.map((w, i) => (
            <div key={i} className="wp-word-cell">
              <span className="wp-word-num">{i+1}</span>
              <span className="wp-word">{w}</span>
            </div>
          ))}
        </div>
        <div className="wp-mnemonic-copy">
          <CopyBtn text={mnemonic} /> <span className="wp-muted-sm">Copy all words</span>
        </div>
        <label className="wp-confirm-check">
          <input
            type="checkbox"
            checked={mnemonicConfirmed}
            onChange={e => setMnemonicConfirmed(e.target.checked)}
          />
          <span>I have written down my recovery phrase</span>
        </label>
        <button
          className="btn wp-btn-primary"
          onClick={handleMnemonicNext}
          disabled={!mnemonicConfirmed}
        >
          Continue →
        </button>
        <button className="btn wp-btn-ghost wp-ghost-sm" onClick={() => setPanelState(S_NO_WALLET)}>
          ← Back
        </button>
      </div>
    </>
  );

  // ── S_SET_PASS ──────────────────────────────────────────────────────────────
  const renderSetPassword = () => (
    <>
      {renderHeader('Set Password')}
      <div className="wp-body">
        <p className="wp-muted" style={{ marginBottom: 20 }}>
          Choose a strong password to protect your wallet. You will need this every time you open it.
        </p>
        <div className="wp-field">
          <label className="wp-label">Password</label>
          <PasswordInput value={password} onChange={setPassword} showStrength placeholder="Choose a strong password…" />
        </div>
        <div className="wp-field">
          <label className="wp-label">Confirm Password</label>
          <PasswordInput value={password2} onChange={setPassword2} placeholder="Repeat password…" />
        </div>
        {passError && <div className="wp-error">{passError}</div>}
        <button
          className="btn wp-btn-primary"
          onClick={handleCreateWallet}
          disabled={!password || !password2}
        >
          Create Wallet
        </button>
        <button className="btn wp-btn-ghost wp-ghost-sm" onClick={() => setPanelState(S_MNEMONIC)}>
          ← Back
        </button>
      </div>
    </>
  );

  // ── S_LOCKED ────────────────────────────────────────────────────────────────
  const renderLocked = () => (
    <>
      {renderHeader('Wallet Locked')}
      <div className="wp-body wp-center">
        <div className="wp-lock-icon">🔒</div>
        {walletMeta && (
          <div className="wp-locked-addr">{shortAddr(walletMeta.address)}</div>
        )}
        <div className="wp-field wp-field-full">
          <label className="wp-label">Password</label>
          <PasswordInput
            value={unlockPass}
            onChange={setUnlockPass}
            placeholder="Enter password…"
          />
        </div>
        {unlockError && <div className="wp-error">{unlockError}</div>}
        <button
          className="btn wp-btn-primary"
          onClick={handleUnlock}
          disabled={!unlockPass || unlocking}
        >
          {unlocking ? 'Unlocking…' : 'Unlock Wallet'}
        </button>
        <div className="wp-or-divider"><span>or</span></div>
        <button className="btn wp-btn-ghost wp-ghost-sm"
          onClick={() => { setRecoverPhrase(''); setRecoverError(''); setPanelState(S_RECOVER); }}>
          Recover from phrase
        </button>
      </div>
    </>
  );

  // ── S_RECOVER ───────────────────────────────────────────────────────────────
  const renderRecover = () => (
    <>
      {renderHeader('Recover Wallet')}
      <div className="wp-body">
        <p className="wp-muted" style={{ marginBottom: 16 }}>
          Enter your 12-word recovery phrase to restore your wallet, then set a new password.
        </p>
        <div className="wp-field">
          <label className="wp-label">Recovery Phrase</label>
          <textarea
            className="wp-import-input"
            rows={4}
            placeholder="word1 word2 word3 … word12"
            value={recoverPhrase}
            onChange={e => setRecoverPhrase(e.target.value)}
            spellCheck={false}
          />
        </div>
        <div className="wp-field">
          <label className="wp-label">New Password</label>
          <PasswordInput value={recoverPass} onChange={setRecoverPass} showStrength placeholder="New password…" />
        </div>
        <div className="wp-field">
          <label className="wp-label">Confirm Password</label>
          <PasswordInput value={recoverPass2} onChange={setRecoverPass2} placeholder="Confirm password…" />
        </div>
        {recoverError && <div className="wp-error">{recoverError}</div>}
        <button
          className="btn wp-btn-primary"
          onClick={handleRecover}
          disabled={!recoverPhrase || !recoverPass || !recoverPass2 || recovering}
        >
          {recovering ? 'Recovering…' : 'Recover Wallet'}
        </button>
        <button className="btn wp-btn-ghost wp-ghost-sm"
          onClick={() => setPanelState(stored ? S_LOCKED : S_NO_WALLET)}>
          ← Back
        </button>
      </div>
    </>
  );

  // ── S_IMPORT_KEY ────────────────────────────────────────────────────────────
  const renderImportKey = () => (
    <>
      {renderHeader('Import Private Key')}
      <div className="wp-body">
        <div className="wp-field">
          <label className="wp-label">Private Key (hex)</label>
          <textarea
            className="wp-import-input"
            rows={2}
            placeholder="64-char hex private key…"
            value={importKey}
            onChange={e => setImportKey(e.target.value)}
            spellCheck={false}
          />
        </div>
        <div className="wp-field">
          <label className="wp-label">Password</label>
          <PasswordInput value={importPass} onChange={setImportPass} showStrength placeholder="Choose a password…" />
        </div>
        <div className="wp-field">
          <label className="wp-label">Confirm Password</label>
          <PasswordInput value={importPass2} onChange={setImportPass2} placeholder="Confirm password…" />
        </div>
        {importError && <div className="wp-error">{importError}</div>}
        <button
          className="btn wp-btn-primary"
          onClick={handleImportKey}
          disabled={!importKey || !importPass || !importPass2 || importing}
        >
          {importing ? 'Importing…' : 'Import Wallet'}
        </button>
        <button className="btn wp-btn-ghost wp-ghost-sm"
          onClick={() => setPanelState(stored ? S_LOCKED : S_NO_WALLET)}>
          ← Back
        </button>
      </div>
    </>
  );

  // ── S_UNLOCKED tabs ─────────────────────────────────────────────────────────

  const renderAccount = () => (
    <div className="wp-account">
      <div className="wp-addr-row">
        <span className="wp-addr-icon">◈</span>
        <span className="wp-addr-text">{shortAddr(walletMeta.address)}</span>
        <CopyBtn text={walletMeta.address} />
      </div>
      <div className="wp-addr-full">{walletMeta.address}</div>

      {acctLoad && <div className="wp-loading">Loading…</div>}
      {account && (
        <div className="wp-balance-grid">
          <div className="wp-balance-card main">
            <div className="wp-balance-val">{formatInfer(account.balance)}</div>
            <div className="wp-balance-label">INFER Balance</div>
          </div>
          <div className="wp-balance-card">
            <div className="wp-balance-val stake">{formatInfer(account.stake)}</div>
            <div className="wp-balance-label">Staked</div>
          </div>
          <div className="wp-balance-card">
            <div className="wp-balance-val rep">{Number(account.reputation).toFixed(2)}</div>
            <div className="wp-balance-label">Reputation</div>
          </div>
          <div className="wp-balance-card">
            <div className="wp-balance-val nonce">#{account.nonce}</div>
            <div className="wp-balance-label">Nonce</div>
          </div>
        </div>
      )}

      <div className="wp-account-actions">
        <button className="btn wp-btn-ghost wp-refresh-btn" onClick={refreshAccount}>↺ Refresh</button>
        <button className="btn wp-btn-faucet" onClick={handleFaucet}>⛽ Faucet</button>
      </div>
      {faucetStatus && (
        <div className={`wp-status ${faucetStatus.ok === true ? 'ok' : faucetStatus.ok === false ? 'err' : 'pending'}`}>
          {faucetStatus.msg}
        </div>
      )}
    </div>
  );

  const renderSend = () => (
    <div className="wp-send">
      <div className="wp-field">
        <label className="wp-label">Recipient Address</label>
        <input className="wp-input" type="text" placeholder="40-char hex…"
          value={sendTo} onChange={e => setSendTo(e.target.value)} spellCheck={false} />
      </div>
      <div className="wp-row-2">
        <div className="wp-field">
          <label className="wp-label">Amount (INFER)</label>
          <input className="wp-input" type="number" min="0" step="any" placeholder="0.00"
            value={sendAmt} onChange={e => setSendAmt(e.target.value)} />
        </div>
        <div className="wp-field">
          <label className="wp-label">Fee</label>
          <input className="wp-input" type="number" min="0" step="0.01" placeholder="0.1"
            value={sendFee} onChange={e => setSendFee(e.target.value)} />
        </div>
      </div>
      {account && <div className="wp-send-bal">Available: <strong>{formatInfer(account.balance)} INFER</strong></div>}
      <button className="btn wp-btn-primary" onClick={handleSend}
        disabled={!sendTo || !sendAmt || sendStatus?.ok === null}>
        Send Transaction →
      </button>
      {sendStatus && (
        <div className={`wp-status ${sendStatus.ok === true ? 'ok' : sendStatus.ok === false ? 'err' : 'pending'}`}>
          {sendStatus.msg}
        </div>
      )}
    </div>
  );

  const renderHistory = () => (
    <div className="wp-history">
      <div className="wp-history-header">
        <span>{history.length} transaction{history.length !== 1 ? 's' : ''}</span>
        <button className="btn wp-btn-ghost wp-sm-btn" onClick={refreshHistory}>↺</button>
      </div>
      {histLoad && <div className="wp-loading">Loading…</div>}
      {!histLoad && history.length === 0 && <div className="wp-empty">No confirmed transactions yet.</div>}
      {history.map((t, i) => <TxRow key={t.tx_id || i} tx={t} myAddress={walletMeta.address} />)}
    </div>
  );

  const renderKeys = () => (
    <div className="wp-keys">
      <div className="wp-key-note">
        ⚠ Your private key is stored encrypted. It is decrypted only in memory when your wallet is unlocked.
      </div>
      <div className="wp-field">
        <label className="wp-label">Address</label>
        <div className="wp-reveal-field">
          <span className="wp-reveal-value" style={{ fontSize: 11, wordBreak: 'break-all' }}>{walletMeta.address}</span>
          <CopyBtn text={walletMeta.address} />
        </div>
      </div>
      <div className="wp-field">
        <label className="wp-label">Public Key</label>
        <div className="wp-reveal-field">
          <span className="wp-reveal-value" style={{ fontSize: 11, wordBreak: 'break-all' }}>{walletMeta.publicKey}</span>
          <CopyBtn text={walletMeta.publicKey} />
        </div>
      </div>
      <div className="wp-divider" />
      <div className="wp-danger-zone">
        <p className="wp-label" style={{ marginBottom: 8 }}>Danger Zone</p>
        <button className="btn wp-btn-danger"
          onClick={() => { clearStoredWallet(); setPrivateKeyHex(null); setWalletMeta(null); setAccount(null); setPanelState(S_NO_WALLET); }}>
          Delete Wallet
        </button>
        <p className="wp-muted-sm" style={{ marginTop: 6 }}>This removes your wallet from this browser. Make sure you have your recovery phrase first.</p>
      </div>
    </div>
  );

  const renderUnlocked = () => (
    <>
      {renderHeader('Wallet', true)}
      <div className="wp-tabs">
        {[
          { id: TAB_ACCOUNT, label: 'Account' },
          { id: TAB_SEND,    label: 'Send' },
          { id: TAB_HISTORY, label: 'History' },
          { id: TAB_KEYS,    label: 'Keys' },
        ].map(t => (
          <button key={t.id} className={`wp-tab ${tab === t.id ? 'active' : ''}`} onClick={() => setTab(t.id)}>
            {t.label}
          </button>
        ))}
      </div>
      <div className="wp-body">
        {tab === TAB_ACCOUNT && renderAccount()}
        {tab === TAB_SEND    && renderSend()}
        {tab === TAB_HISTORY && renderHistory()}
        {tab === TAB_KEYS    && renderKeys()}
      </div>
    </>
  );

  // ── Root ────────────────────────────────────────────────────────────────────
  return (
    <>
      {open && <div className="wp-backdrop" />}
      <div className={`wallet-panel ${open ? 'open' : ''}`} ref={panelRef}>
        {panelState === S_NO_WALLET  && renderNoWallet()}
        {panelState === S_MNEMONIC   && renderMnemonic()}
        {panelState === S_SET_PASS   && renderSetPassword()}
        {panelState === S_LOCKED     && renderLocked()}
        {panelState === S_RECOVER    && renderRecover()}
        {panelState === S_IMPORT_KEY && renderImportKey()}
        {panelState === S_UNLOCKED   && renderUnlocked()}
      </div>
    </>
  );
}
