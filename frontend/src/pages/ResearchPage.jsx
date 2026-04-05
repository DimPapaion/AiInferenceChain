import React from 'react';
import './AboutSectionPage.css';

const RESEARCH_AREAS = [
  {
    title: 'QoI and PoQI',
    body: 'The research core of the project is making inference quality measurable and then tying rewards, slashing, and reputation updates to that quality signal.',
  },
  {
    title: 'S-BFT and OOD bias',
    body: 'Scalable quorum selection reduces the active validator set per request, while OOD scoring makes that subset more domain-appropriate without breaking determinism.',
  },
  {
    title: 'Optional orchestration layer',
    body: 'The LLM orchestration work is deliberately outside consensus. It adds utility for routing and explainability without making the base protocol nondeterministic.',
  },
];

export default function ResearchPage({ navigate }) {
  return (
    <div className="about-page-root">
      <section className="about-hero page-wrap">
        <div className="about-hero-shell">
          <div className="about-kicker">Research</div>
          <h1>Protocol research and current implementation themes</h1>
          <p>
            This page is for the research framing around the project: what ideas are already
            implemented, what is still exploratory, and how the codebase relates to the whitepaper.
          </p>
          <div className="about-hero-actions">
            <button className="btn btn-primary btn-lg" onClick={() => navigate('whitepaper')}>
              Open Whitepaper
            </button>
            <button className="btn btn-ghost btn-lg" onClick={() => navigate('about')}>
              Back to About
            </button>
          </div>
        </div>
      </section>

      <section className="about-section page-wrap">
        <div className="about-card-grid">
          {RESEARCH_AREAS.map((area) => (
            <div key={area.title} className="about-card">
              <h3>{area.title}</h3>
              <p>{area.body}</p>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}