import React, { useEffect, useState } from 'react';
import './NavBar.css';
import { chain as chainApi } from '../api/client';

const NAV = [
  { id: 'home',       label: 'Home' },
  { id: 'explorer',   label: 'Explorer' },
  { id: 'validators', label: 'Validators' },
  { id: 'inference',  label: 'Inference' },
  { id: 'network',    label: 'Network' },
  { id: 'join',       label: 'Become a Node' },
];

export default function NavBar({ current, navigate }) {
  const [height, setHeight] = useState(null);
  const [open,   setOpen]   = useState(false);

  useEffect(() => {
    const fetch = () =>
      chainApi.height().then(d => setHeight(d.height)).catch(() => {});
    fetch();
    const id = setInterval(fetch, 5000);
    return () => clearInterval(id);
  }, []);

  return (
    <nav className="navbar">
      <div className="navbar-inner">
        {/* Logo */}
        <button className="navbar-logo" onClick={() => navigate('home')}>
          <span className="logo-icon">⬡</span>
          <span className="logo-text">InferenceChain</span>
        </button>

        {/* Desktop links */}
        <ul className="navbar-links">
          {NAV.map(n => (
            <li key={n.id}>
              <button
                className={`nav-link ${current === n.id ? 'active' : ''}`}
                onClick={() => navigate(n.id)}
              >
                {n.label}
              </button>
            </li>
          ))}
        </ul>

        {/* Right: chain height pill + API docs */}
        <div className="navbar-right">
          {height !== null && (
            <span className="height-pill">
              <span className="height-dot" />
              Block #{height}
            </span>
          )}
          <a
            className="btn btn-ghost nav-github"
            href="https://github.com/DimPapaion/InferenceChain"
            target="_blank"
            rel="noreferrer"
          >
            <svg className="github-icon" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
              <path d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.531 1.032 1.531 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.019 10.019 0 0022 12.017C22 6.484 17.522 2 12 2z" />
            </svg>
            Github Code
          </a>
          <a
            className="btn btn-ghost nav-docs"
            href="http://localhost:8000/docs"
            target="_blank"
            rel="noreferrer"
          >
            API Docs ↗
          </a>

          {/* Mobile hamburger */}
          <button className="hamburger" onClick={() => setOpen(o => !o)}>
            <span /><span /><span />
          </button>
        </div>
      </div>

      {/* Mobile menu */}
      {open && (
        <div className="mobile-menu">
          {NAV.map(n => (
            <button
              key={n.id}
              className={`mobile-link ${current === n.id ? 'active' : ''}`}
              onClick={() => { navigate(n.id); setOpen(false); }}
            >
              {n.label}
            </button>
          ))}
        </div>
      )}
    </nav>
  );
}
