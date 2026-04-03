import React, { useEffect, useState } from 'react';
import './LandingPage.css';
import { chain as chainApi, dashboard } from '../api/client';

const INNOVATIONS = [
  {
    icon: '◈',
    color: 'purple',
    title: 'Quality of Inference Consensus',
    subtitle: 'QoI — PBFT adapted for DNN',
    body: `Validators score each other's DNN outputs using cosine similarity. The network only commits an inference result when a 2f+1 quorum of validators produce mathematically aligned predictions — not just vote agreement.`,
    tags: ['PBFT', 'Cosine Similarity', 'Byzantine Fault Tolerant'],
  },
  {
    icon: '◎',
    color: 'blue',
    title: 'Proof of Quality of Inference',
    subtitle: 'PoQI — On-chain reputation',
    body: `Every DNN validator builds a cryptographic reputation score on-chain. High-quality validators earn more block rewards and proposal weight. Byzantine nodes are automatically penalised and slashed — without human intervention.`,
    tags: ['Reputation', 'Stake Slashing', 'Incentive Alignment'],
  },
  {
    icon: '⬡',
    color: 'cyan',
    title: 'Sharded BFT Architecture',
    subtitle: 'S-BFT — Horizontal scaling',
    body: `The validator set is partitioned into independent committees, each running QoI consensus in parallel on separate inference requests. Throughput scales linearly with the number of committees — without sacrificing BFT guarantees.`,
    tags: ['Sharding', 'Parallel Consensus', 'Linear Scalability'],
  },
];

function AnimatedCounter({ target, duration = 1400 }) {
  const [val, setVal] = useState(0);
  useEffect(() => {
    if (!target) return;
    let start = null;
    const step = (ts) => {
      if (!start) start = ts;
      const p = Math.min((ts - start) / duration, 1);
      setVal(Math.floor(p * target));
      if (p < 1) requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
  }, [target, duration]);
  return <>{val.toLocaleString()}</>;
}

export default function LandingPage({ navigate }) {
  const [stats, setStats] = useState(null);

  useEffect(() => {
    const load = () =>
      chainApi.stats().then(setStats).catch(() => {});
    load();
    const id = setInterval(load, 8000);
    return () => clearInterval(id);
  }, []);

  return (
    <div className="landing">

      {/* ── Hero ─────────────────────────────────────────────────────────── */}
      <section className="hero">
        <div className="hero-bg">
          <div className="hero-glow hero-glow-1" />
          <div className="hero-glow hero-glow-2" />
          <div className="hero-grid" />
        </div>

        <div className="hero-content">
          <div className="hero-badge">Research Preview · Testnet v0.1</div>
          <h1 className="hero-title">
            The Blockchain
            <br />
            <span className="hero-gradient">Native to AI Inference</span>
          </h1>
          <p className="hero-subtitle">
            InferenceChain is a decentralised network where DNN validators reach
            consensus on the <em>quality</em> of AI inference results — not just
            on transaction order.
          </p>

          <div className="hero-actions">
            <button className="btn btn-primary btn-lg" onClick={() => navigate('explorer')}>
              Open Explorer →
            </button>
            <button className="btn btn-ghost btn-lg" onClick={() => navigate('inference')}>
              Submit Inference
            </button>
          </div>

          {/* Live mini-stats */}
          {stats && (
            <div className="hero-stats">
              {[
                { label: 'Chain Height',    val: stats.chain_height,   unit: '' },
                { label: 'Total Txs',       val: stats.total_txs,      unit: '' },
                { label: 'QoI Blocks',      val: stats.qoi_blocks,     unit: '' },
                { label: 'DNN Validators',  val: stats.dnn_validators, unit: '' },
                { label: 'TPS (60 s)',      val: stats.tps,            unit: '' },
              ].map(s => (
                <div key={s.label} className="hero-stat">
                  <span className="hero-stat-val">
                    <AnimatedCounter target={s.val} />
                    {s.unit}
                  </span>
                  <span className="hero-stat-label">{s.label}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      </section>

      {/* ── Key Innovations ──────────────────────────────────────────────── */}
      <section className="innovations">
        <div className="page-wrap">
          <div className="innovations-header">
            <p className="section-title">Architecture</p>
            <h2>Built different.<br />By design.</h2>
            <p className="innovations-lead">
              Three novel primitives combine to create the first blockchain where
              inference quality is a first-class consensus property.
            </p>
          </div>

          <div className="innovations-grid">
            {INNOVATIONS.map((inn, i) => (
              <div key={i} className={`inn-card inn-card-${inn.color}`}>
                <div className="inn-icon">{inn.icon}</div>
                <div className="inn-header">
                  <h3>{inn.title}</h3>
                  <span className="inn-subtitle">{inn.subtitle}</span>
                </div>
                <p className="inn-body">{inn.body}</p>
                <div className="inn-tags">
                  {inn.tags.map(t => (
                    <span key={t} className="inn-tag">{t}</span>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── How it works ─────────────────────────────────────────────────── */}
      <section className="how-it-works">
        <div className="page-wrap">
          <p className="section-title">Protocol Flow</p>
          <h2>From inference request to committed block</h2>

          <div className="flow-steps">
            {[
              { n: '01', title: 'Submit Request',    body: 'Client uploads an image and submits an INFERENCE_REQUEST transaction to the mempool.',        color: 'purple' },
              { n: '02', title: 'QoI Round Starts',  body: 'ConsensusEngine detects pending inference tx. Primary DNN node runs the image through the DNN and broadcasts PRE_PREPARE.',   color: 'blue' },
              { n: '03', title: 'Validators Score',  body: 'Each DNN validator runs its own inference and sends PREPARE with its output vector. Cosine similarity is computed pairwise.',  color: 'cyan' },
              { n: '04', title: 'Commit & Record',   body: 'When 2f+1 validators agree, the COMMIT phase finalises. The result and reputation deltas are written to a QoI block on-chain.', color: 'green' },
            ].map(s => (
              <div key={s.n} className={`flow-step flow-step-${s.color}`}>
                <div className="flow-num">{s.n}</div>
                <div className="flow-content">
                  <h4>{s.title}</h4>
                  <p>{s.body}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── CTA ──────────────────────────────────────────────────────────── */}
      <section className="cta-section">
        <div className="page-wrap">
          <div className="cta-card">
            <div className="cta-glow" />
            <h2>Start exploring the network</h2>
            <p>View live blocks, inspect validator reputations, or submit your first inference request.</p>
            <div className="cta-actions">
              <button className="btn btn-primary btn-lg" onClick={() => navigate('explorer')}>
                Chain Explorer →
              </button>
              <button className="btn btn-ghost btn-lg" onClick={() => navigate('validators')}>
                View Validators
              </button>
            </div>
          </div>
        </div>
      </section>

    </div>
  );
}
