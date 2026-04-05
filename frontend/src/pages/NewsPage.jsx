import React from 'react';
import './AboutSectionPage.css';

export default function NewsPage({ navigate }) {
  return (
    <div className="about-page-root">
      <section className="about-hero page-wrap">
        <div className="about-hero-shell">
          <div className="about-kicker">News</div>
          <h1>Release notes and updates will live here</h1>
          <p>
            This is intentionally a placeholder section for future testnet releases, milestone updates,
            benchmarking notes, and validator onboarding announcements.
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
          <h2>No news feed yet</h2>
          <p>
            When you are ready, this page can hold release entries, changelog highlights,
            network milestones, and blog-style announcements without requiring another navigation redesign.
          </p>
        </div>
      </section>
    </div>
  );
}