import React, { useEffect, useState } from 'react';
import './NavBar.css';
import { chain as chainApi } from '../api/client';
import WalletPanel from './WalletPanel';
import { loadStoredWallet, shortAddr } from '../utils/wallet';

const NAV = [
  { id: 'home', label: 'Home' },
  { id: 'explorer', label: 'Explorer' },
  { id: 'validators', label: 'Validators' },
  { id: 'inference', label: 'Inference' },
  { id: 'network', label: 'Network' },
  { id: 'join', label: 'Become a Node' },
  { id: 'whitepaper', label: 'Whitepaper' },
];

export default function NavBar({ current, navigate }) {
  const [height,       setHeight]       = useState(null);
  const [open,         setOpen]         = useState(false);
  const [walletOpen,   setWalletOpen]   = useState(false);
  const [walletAddr,   setWalletAddr]   = useState(() => loadStoredWallet()?.address ?? null);
  const year = new Date().getFullYear();

  // Refresh wallet address label whenever panel closes (user may have imported/generated)
  const handleWalletClose = () => {
    setWalletOpen(false);
    setWalletAddr(loadStoredWallet()?.address ?? null);
  };

  useEffect(() => {
    const fetch = () =>
      chainApi.height().then(d => setHeight(d.height)).catch(() => {});
    fetch();
    const id = setInterval(fetch, 5000);
    return () => clearInterval(id);
  }, []);

  // Prevent body scroll when menu is open
  useEffect(() => {
    document.body.style.overflow = open ? 'hidden' : '';
    return () => {
      document.body.style.overflow = '';
    };
  }, [open]);

  const go = (id) => {
    navigate(id);
    setOpen(false);
  };

  return (
    <>
      <nav className="navbar">
        <div className="navbar-inner">
          <button className="navbar-logo" onClick={() => go('home')}>
            <span className="logo-icon">⬡</span>
            <span className="logo-text">InferenceChain</span>
          </button>

          <ul className="navbar-links">
            {NAV.map(n => (
              <li key={n.id}>
                <button
                  className={`nav-link ${current === n.id ? 'active' : ''}`}
                  onClick={() => go(n.id)}
                >
                  {n.label}
                </button>
              </li>
            ))}
          </ul>

          <div className="navbar-right">
            {height !== null && (
              <span className="height-pill">
                <span className="height-dot" />
                Block #{height}
              </span>
            )}
            <a className="btn btn-ghost nav-github" href="https://github.com/DimPapaion/AiInferenceChain" target="_blank" rel="noreferrer">
              <svg className="github-icon" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
                <path d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.531 1.032 1.531 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.019 10.019 0 0022 12.017C22 6.484 17.522 2 12 2z" />
              </svg>
              Github
            </a>
            <a className="btn btn-ghost nav-docs" href="http://localhost:8000/docs" target="_blank" rel="noreferrer">
              API Docs ↗
            </a>

            <button
              className={`btn nav-wallet-btn ${walletAddr ? 'connected' : ''}`}
              onClick={() => setWalletOpen(true)}
              title="Open wallet"
            >
              <span className="wallet-btn-icon">⬡</span>
              <span className="wallet-btn-label">
                {walletAddr ? shortAddr(walletAddr) : 'Wallet'}
              </span>
            </button>

            <button className="hamburger" onClick={() => setOpen(true)} aria-label="Open menu">
              <span /><span /><span />
            </button>
          </div>
        </div>
      </nav>

      {open && (
        <div className="mobile-overlay">
          <div className="mobile-overlay-header">
            <button className="mobile-overlay-logo" onClick={() => go('home')}>
              <span className="logo-icon">⬡</span>
              <span className="logo-text">InferenceChain</span>
            </button>
            <button className="mobile-close" onClick={() => setOpen(false)} aria-label="Close menu">
              ✕
            </button>
          </div>

          <nav className="mobile-nav-links">
            {NAV.map(n => (
              <button
                key={n.id}
                className={`mobile-link ${current === n.id ? 'active' : ''}`}
                onClick={() => go(n.id)}
              >
                {n.label}
              </button>
            ))}
          </nav>

          <div className="mobile-footer-links">
            <a className="mobile-footer-link" href="https://github.com/DimPapaion/AiInferenceChain" target="_blank" rel="noreferrer">
              <svg style={{ width: 18, height: 18, flexShrink: 0 }} viewBox="0 0 24 24" fill="currentColor">
                <path d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.531 1.032 1.531 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.019 10.019 0 0022 12.017C22 6.484 17.522 2 12 2z" />
              </svg>
              Github Code
            </a>
            <a className="mobile-footer-link" href="http://localhost:8000/docs" target="_blank" rel="noreferrer">
              ↗ API Docs
            </a>
            <button
              className="mobile-footer-link mobile-wallet-link"
              onClick={() => { setOpen(false); setWalletOpen(true); }}
            >
              ⬡ {walletAddr ? shortAddr(walletAddr) : 'Wallet'}
            </button>
            <div className="mobile-brand-mark">© {year} InferenceChain</div>
          </div>
        </div>
      )}

      <WalletPanel open={walletOpen} onClose={handleWalletClose} />
    </>
  );
}
