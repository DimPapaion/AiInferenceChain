import React from 'react';
import './AppShell.css';

/**
 * Minimal chrome — title bar + content area.
 * On macOS the traffic lights sit in the inset area;
 * on Windows/Linux we get the native frame.
 */
export default function AppShell({ children }) {
  return (
    <div className="shell-root">
      <header className="shell-titlebar">
        <span className="shell-wordmark">
          <span className="shell-wordmark-ic">Inference</span>Chain
        </span>
        <span className="shell-version">Desktop · v0.1</span>
      </header>
      <main className="shell-content">{children}</main>
    </div>
  );
}
