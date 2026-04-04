import React, { useEffect, useRef, useState, useCallback } from 'react';
import './WalletPanel.css';
import {
  generateWallet, walletFromPrivateKey,
  saveWallet, loadWallet, clearWallet,
  buildTransferTx, shortAddr, formatInfer,
} from '../utils/wallet';
import { state as stateApi, tx as txApi, wallet as walletApi } from '../api/client';

// ── Tab IDs ───────────────────────────────────────────────────────────────────
const TAB_ACCOUNT = 'account';
const TAB_SEND    = 'send';
const TAB_HISTORY = 'history';
const TAB_KEYS    = 'keys';

// ── Small components ──────────────────────────────────────────────────────────

function CopyBtn({ text }) {
  const [copied, setCopied] = useState(false);
  const copy = () => {
    navigator.clipboard.writeText(text).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    });
  };
  return (
    <button className="wp-copy-btn" onClick={copy} title="Copy">
      {copied ? '✓' : '⎘'}
    </button>
  );
}

function RevealField({ label, value }) {
  const [show, setShow] = useState(false);
  return (
    <div className="wp-reveal-row">
      <span className="wp-reveal-label">{label}</span>
      <div className="wp-reveal-field">
        <span className={`wp-reveal-value ${show ? '' : 'blurred'}`}>{value}</span>
        <button className="wp-icon-btn" onClick={() => setShow(s => !s)} title={show ? 'Hide' : 'Show'}>
          {show ? '🙈' : '👁'}
        </button>
        {show && <CopyBtn text={value} />}
      </div>
    </div>
  );
}

function TxRow({ tx, myAddress }) {
  const isSend = tx.sender === myAddress;
  const amount = tx.payload?.amount ?? 0;
  const peer   = isSend ? tx.recipient : tx.sender;
  const sign   = isSend ? '-' : '+';
  const cls    = isSend ? 'tx-out' : 'tx-in';
  const typeLabel = tx.tx_type?.replace(/_/g, ' ') ?? '';
  return (
    <div className={`wp-tx-row ${cls}`}>
      <div className="wp-tx-left">
        <span className="wp-tx-type">{typeLabel}</span>
        <span className="wp-tx-peer">{peer ? shortAddr(peer) : '—'}</span>
      </div>
      <div className="wp-tx-right">
        <span className="wp-tx-amount">{sign}{formatInfer(amount)} INFER</span>
        {tx.block_height != null && (
          <span className="wp-tx-block">block #{tx.block_height}</span>
        )}
      </div>
    </div>
  );
}

// ── Main panel ────────────────────────────────────────────────────────────────

export default function WalletPanel({ open, onClose }) {
  const panelRef = useRef();
  const [wallet,  setWallet]  = useState(() => loadWallet());
  const [tab,     setTab]     = useState(TAB_ACCOUNT);
  const [account, setAccount] = useState(null);
  const [loading, setLoading] = useState(false);

  // Send state
  const [sendTo,     setSendTo]     = useState('');
  const [sendAmt,    setSendAmt]    = useState('');
  const [sendFee,    setSendFee]    = useState('0.1');
  const [sendStatus, setSendStatus] = useState(null); // null | {ok, msg}

  // History state
  const [history, setHistory] = useState([]);
  const [histLoad, setHistLoad] = useState(false);

  // Keys state
  const [importKey,    setImportKey]    = useState('');
  const [importErr,    setImportErr]    = useState('');
  const [showNewWarn,  setShowNewWarn]  = useState(false);
  const [faucetStatus, setFaucetStatus] = useState(null); // null | {ok, msg}

  // ── Fetch account info ──────────────────────────────────────────────────────
  const refreshAccount = useCallback(async () => {
    if (!wallet) return;
    setLoading(true);
    try {
      const data = await stateApi.balance(wallet.address);
      setAccount(data);
    } catch {
      setAccount(null);
    } finally {
      setLoading(false);
    }
  }, [wallet]);

  useEffect(() => {
    if (open && wallet) {
      refreshAccount();
    }
  }, [open, wallet, refreshAccount]);

  // Refresh account when switching to account tab
  useEffect(() => {
    if (tab === TAB_ACCOUNT && wallet) refreshAccount();
  }, [tab, wallet, refreshAccount]);

  // ── Fetch history ───────────────────────────────────────────────────────────
  const refreshHistory = useCallback(async () => {
    if (!wallet) return;
    setHistLoad(true);
    try {
      const data = await walletApi.history(wallet.address);
      setHistory(data);
    } catch {
      setHistory([]);
    } finally {
      setHistLoad(false);
    }
  }, [wallet]);

  useEffect(() => {
    if (tab === TAB_HISTORY && wallet) refreshHistory();
  }, [tab, wallet, refreshHistory]);

  // ── Close on outside click ──────────────────────────────────────────────────
  useEffect(() => {
    if (!open) return;
    const handler = (e) => {
      if (panelRef.current && !panelRef.current.contains(e.target)) onClose();
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [open, onClose]);

  // ── Wallet actions ──────────────────────────────────────────────────────────
  const handleGenerate = () => {
    const w = generateWallet();
    saveWallet(w);
    setWallet(w);
    setAccount(null);
    setShowNewWarn(false);
    setFaucetStatus(null);
    setTab(TAB_ACCOUNT);
  };

  const handleImport = () => {
    setImportErr('');
    try {
      const w = walletFromPrivateKey(importKey);
      saveWallet(w);
      setWallet(w);
      setAccount(null);
      setImportKey('');
      setFaucetStatus(null);
      setTab(TAB_ACCOUNT);
    } catch (e) {
      setImportErr(e.message);
    }
  };

  // ── Faucet ──────────────────────────────────────────────────────────────────
  const handleFaucet = async () => {
    if (!wallet) return;
    setFaucetStatus({ ok: null, msg: 'Requesting tokens…' });
    try {
      const res = await walletApi.faucet(wallet.address);
      if (res.success) {
        setFaucetStatus({ ok: true, msg: `Received ${formatInfer(res.amount)} INFER` });
        refreshAccount();
      } else {
        setFaucetStatus({ ok: false, msg: res.message });
      }
    } catch (e) {
      setFaucetStatus({ ok: false, msg: e.message });
    }
  };

  // ── Send ────────────────────────────────────────────────────────────────────
  const handleSend = async () => {
    setSendStatus(null);
    if (!wallet) return;
    const to  = sendTo.trim().toLowerCase();
    const amt = parseFloat(sendAmt);
    const fee = parseFloat(sendFee) || 0;

    if (to.length !== 40 || !/^[0-9a-f]+$/.test(to)) {
      setSendStatus({ ok: false, msg: 'Invalid recipient address (expected 40-char hex)' });
      return;
    }
    if (!amt || amt <= 0) {
      setSendStatus({ ok: false, msg: 'Enter a valid amount' });
      return;
    }
    if (!account) {
      setSendStatus({ ok: false, msg: 'Account info not loaded — refresh and retry' });
      return;
    }
    if (account.balance < amt + fee) {
      setSendStatus({ ok: false, msg: `Insufficient balance (have ${formatInfer(account.balance)} INFER)` });
      return;
    }

    setSendStatus({ ok: null, msg: 'Submitting…' });
    try {
      const nonce = (account.nonce || 0) + 1;
      const built = buildTransferTx(wallet, to, amt, fee, nonce);
      const res   = await txApi.submit(built);
      if (res.accepted) {
        setSendStatus({ ok: true, msg: `Submitted — tx ${res.tx_id.slice(0, 12)}…` });
        setSendTo(''); setSendAmt('');
        // Optimistically update balance
        setAccount(a => a ? { ...a, balance: a.balance - amt - fee, nonce } : a);
      } else {
        setSendStatus({ ok: false, msg: res.reason || 'Rejected by node' });
      }
    } catch (e) {
      setSendStatus({ ok: false, msg: e.message });
    }
  };

  // ── Render: no wallet ───────────────────────────────────────────────────────
  const renderNoWallet = () => (
    <div className="wp-no-wallet">
      <div className="wp-no-wallet-icon">⬡</div>
      <h3>No Wallet</h3>
      <p>Generate a new wallet or import an existing private key to get started.</p>
      <button className="btn wp-btn-primary btn-lg" onClick={handleGenerate}>
        Generate New Wallet
      </button>
      <div className="wp-import-section">
        <p className="wp-import-label">or import from private key</p>
        <textarea
          className="wp-import-input"
          placeholder="Paste 64-char hex private key…"
          value={importKey}
          onChange={e => setImportKey(e.target.value)}
          rows={2}
        />
        {importErr && <div className="wp-error">{importErr}</div>}
        <button
          className="btn wp-btn-ghost"
          onClick={handleImport}
          disabled={!importKey.trim()}
        >
          Import Wallet
        </button>
      </div>
    </div>
  );

  // ── Render: account tab ─────────────────────────────────────────────────────
  const renderAccount = () => (
    <div className="wp-account">
      <div className="wp-addr-row">
        <span className="wp-addr-icon">◈</span>
        <span className="wp-addr-text">{shortAddr(wallet.address)}</span>
        <CopyBtn text={wallet.address} />
      </div>
      <div className="wp-addr-full">{wallet.address}</div>

      {loading && <div className="wp-loading">Loading…</div>}

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
        <button className="btn wp-btn-ghost wp-refresh-btn" onClick={refreshAccount}>
          ↺ Refresh
        </button>
        <button className="btn wp-btn-faucet" onClick={handleFaucet}>
          ⛽ Faucet
        </button>
      </div>

      {faucetStatus && (
        <div className={`wp-status ${faucetStatus.ok === true ? 'ok' : faucetStatus.ok === false ? 'err' : 'pending'}`}>
          {faucetStatus.msg}
        </div>
      )}
    </div>
  );

  // ── Render: send tab ────────────────────────────────────────────────────────
  const renderSend = () => (
    <div className="wp-send">
      <div className="wp-field">
        <label className="wp-label">Recipient Address</label>
        <input
          className="wp-input"
          type="text"
          placeholder="40-char hex address…"
          value={sendTo}
          onChange={e => setSendTo(e.target.value)}
          spellCheck={false}
        />
      </div>
      <div className="wp-row-2">
        <div className="wp-field">
          <label className="wp-label">Amount (INFER)</label>
          <input
            className="wp-input"
            type="number"
            min="0"
            step="any"
            placeholder="0.00"
            value={sendAmt}
            onChange={e => setSendAmt(e.target.value)}
          />
        </div>
        <div className="wp-field">
          <label className="wp-label">Fee</label>
          <input
            className="wp-input"
            type="number"
            min="0"
            step="0.01"
            placeholder="0.1"
            value={sendFee}
            onChange={e => setSendFee(e.target.value)}
          />
        </div>
      </div>

      {account && (
        <div className="wp-send-bal">
          Available: <strong>{formatInfer(account.balance)} INFER</strong>
        </div>
      )}

      <button
        className="btn wp-btn-primary"
        onClick={handleSend}
        disabled={!sendTo || !sendAmt || sendStatus?.ok === null}
      >
        Send Transaction →
      </button>

      {sendStatus && (
        <div className={`wp-status ${sendStatus.ok === true ? 'ok' : sendStatus.ok === false ? 'err' : 'pending'}`}>
          {sendStatus.msg}
        </div>
      )}
    </div>
  );

  // ── Render: history tab ─────────────────────────────────────────────────────
  const renderHistory = () => (
    <div className="wp-history">
      <div className="wp-history-header">
        <span>{history.length} transaction{history.length !== 1 ? 's' : ''}</span>
        <button className="btn wp-btn-ghost wp-sm-btn" onClick={refreshHistory}>↺</button>
      </div>
      {histLoad && <div className="wp-loading">Loading…</div>}
      {!histLoad && history.length === 0 && (
        <div className="wp-empty">No confirmed transactions yet.</div>
      )}
      {history.map((tx, i) => (
        <TxRow key={tx.tx_id || i} tx={tx} myAddress={wallet.address} />
      ))}
    </div>
  );

  // ── Render: keys tab ────────────────────────────────────────────────────────
  const renderKeys = () => (
    <div className="wp-keys">
      <RevealField label="Private Key" value={wallet.privateKey} />
      <RevealField label="Public Key"  value={wallet.publicKey} />
      <div className="wp-key-note">
        Store your private key in a safe place. Anyone with this key controls your funds.
      </div>

      <div className="wp-divider" />

      <div className="wp-import-section">
        <p className="wp-import-label">Import from private key</p>
        <textarea
          className="wp-import-input"
          placeholder="64-char hex private key…"
          value={importKey}
          onChange={e => setImportKey(e.target.value)}
          rows={2}
        />
        {importErr && <div className="wp-error">{importErr}</div>}
        <button
          className="btn wp-btn-ghost"
          onClick={handleImport}
          disabled={!importKey.trim()}
        >
          Import
        </button>
      </div>

      <div className="wp-divider" />

      {!showNewWarn ? (
        <button
          className="btn wp-btn-danger"
          onClick={() => setShowNewWarn(true)}
        >
          Generate New Wallet
        </button>
      ) : (
        <div className="wp-warn-box">
          <p>This will replace your current wallet. Make sure you've saved your private key!</p>
          <div className="wp-warn-actions">
            <button className="btn wp-btn-danger" onClick={handleGenerate}>Yes, generate new</button>
            <button className="btn wp-btn-ghost" onClick={() => setShowNewWarn(false)}>Cancel</button>
          </div>
        </div>
      )}
    </div>
  );

  // ── Root render ─────────────────────────────────────────────────────────────
  return (
    <>
      {open && <div className="wp-backdrop" />}
      <div className={`wallet-panel ${open ? 'open' : ''}`} ref={panelRef}>
        <div className="wp-header">
          <div className="wp-header-left">
            <span className="wp-header-icon">⬡</span>
            <span className="wp-header-title">Wallet</span>
            {wallet && (
              <span className="wp-header-addr">{shortAddr(wallet.address)}</span>
            )}
          </div>
          <button className="wp-close-btn" onClick={onClose} aria-label="Close wallet">✕</button>
        </div>

        {!wallet ? renderNoWallet() : (
          <>
            <div className="wp-tabs">
              {[
                { id: TAB_ACCOUNT, label: 'Account' },
                { id: TAB_SEND,    label: 'Send' },
                { id: TAB_HISTORY, label: 'History' },
                { id: TAB_KEYS,    label: 'Keys' },
              ].map(t => (
                <button
                  key={t.id}
                  className={`wp-tab ${tab === t.id ? 'active' : ''}`}
                  onClick={() => setTab(t.id)}
                >
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
        )}
      </div>
    </>
  );
}
