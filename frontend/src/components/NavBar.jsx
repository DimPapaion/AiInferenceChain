import React, { useEffect, useState } from 'react';
import './NavBar.css';
import { chain as chainApi } from '../api/client';

const NAV = [
  { id: 'home',       label: 'Home' },
  { id: 'explorer',   label: 'Explorer' },
  { id: 'validators', label: 'Validators' },
  { id: 'inference',  label: 'Inference' },
  { id: 'network',    label: 'Network' },
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
