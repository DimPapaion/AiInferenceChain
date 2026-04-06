import React from 'react';
import './AboutSectionPage.css';

const PILLARS = [
  {
    title: 'Verified inference',
    body: 'InferenceChain makes model execution verifiable at the network level. Validators do not just relay outputs; they reach consensus on the quality of those outputs.',
  },
  {
    title: 'Adaptive validator choice',
    body: 'Model compatibility, quorum selection, and OOD-aware bias combine with multi-factor weighting (stake × knowledge × reliability) to ensure the active validator set is optimized for each request. Hidden challenges prevent gaming.',
  },
  {
    title: 'Operator-friendly architecture',
    body: 'The network is structured for three roles: users who want inference, researchers who want observability, and operators who want to run PoS or DNN validators.',
  },
];

const PATHS = [
  { label: 'Use the network', target: 'get-started', action: 'Open Get Started' },
  { label: 'Read the technical layer', target: 'whitepaper', action: 'Open Whitepaper' },
  { label: 'Run infrastructure', target: 'join', action: 'Run a Node' },
];

export default function AboutPage({ navigate }) {
  return (
    <div className="about-page-root">
      <section className="about-hero page-wrap">
        <div className="about-hero-shell">
          <div className="about-kicker">About InferenceChain</div>
          <h1>A product overview before the protocol deep dive</h1>
          <p>
            This section explains what InferenceChain is, who it is for, and how the
            main parts fit together. It is intentionally less formal than the whitepaper
            and better suited for first contact.
          </p>
          <div className="about-hero-actions">
            <button className="btn btn-primary btn-lg" onClick={() => navigate('get-started')}>
              Get Started
            </button>
            <button className="btn btn-ghost btn-lg" onClick={() => navigate('whitepaper')}>
              Read Whitepaper
            </button>
          </div>
        </div>
      </section>

      <section className="about-section page-wrap">
        <div className="about-head">
          <p className="section-title">Core idea</p>
          <h2>Why the project exists</h2>
          <p>
            Most chains can verify that computation ran. InferenceChain is designed to
            verify that AI inference was produced honestly and agreed upon by a Byzantine-resistant set of validators.
          </p>
        </div>

        <div className="about-card-grid">
          {PILLARS.map((pillar) => (
            <div key={pillar.title} className="about-card">
              <h3>{pillar.title}</h3>
              <p>{pillar.body}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="about-section about-section-alt">
        <div className="page-wrap">
          <div className="about-head">
            <p className="section-title">Where to go next</p>
            <h2>Choose the right depth</h2>
            <p>
              The site now separates product overview, technical whitepaper, research context,
              and future ecosystem sections so the navigation stays coherent as the project grows.
            </p>
          </div>

          <div className="about-link-grid">
            {PATHS.map((path) => (
              <div key={path.label} className="about-link-card">
                <h3>{path.label}</h3>
                <button className="btn btn-ghost" onClick={() => navigate(path.target)}>
                  {path.action}
                </button>
              </div>
            ))}
          </div>
        </div>
      </section>
    </div>
  );
}