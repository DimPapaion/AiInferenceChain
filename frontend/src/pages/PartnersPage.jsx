import React from 'react';
import './AboutSectionPage.css';

export default function PartnersPage({ navigate }) {
  return (
    <div className="about-page-root">
      <section className="about-hero page-wrap">
        <div className="about-hero-shell">
          <div className="about-kicker">Partners</div>
          <h1>Future collaborators and ecosystem partners</h1>
          <p>
            This is a deliberate placeholder for labs, research groups, infrastructure collaborators,
            node operators, and other ecosystem partners once those relationships are ready to be shown.
          </p>
          <div className="about-hero-actions">
            <button className="btn btn-primary btn-lg" onClick={() => navigate('about')}>
              Back to About
            </button>
          </div>
        </div>
      </section>

      <section className="about-section page-wrap">
        <div className="about-placeholder-card">
          <div className="about-placeholder-badge">Placeholder</div>
          <h2>No partner list published yet</h2>
          <p>
            The section exists now so the site architecture is ready. Later you can drop in logos,
            collaborator blurbs, or categories like research, infrastructure, and validator partners.
          </p>
        </div>
      </section>
    </div>
  );
}