import React, { useEffect, useRef, useState } from 'react';
import './WhitepaperPage.css';

const SECTIONS = [
  {
    id: 'qoi',
    icon: '◈',
    color: 'purple',
    label: 'QoI Consensus',
    title: 'Quality of Inference Consensus',
    subtitle: 'Byzantine-fault-tolerant agreement on DNN output quality',
    body: `Validators don't just agree on transaction order — they agree on the correctness
of AI inference results. Each validator independently runs the same image through its
local DNN model and broadcasts its output probability vector. Consensus is reached when
a 2f+1 quorum of validators produce mathematically aligned predictions, measured by
cosine similarity.`,
    stats: [
      { label: 'Fault tolerance', value: '2f+1 quorum' },
      { label: 'Similarity metric', value: 'Cosine' },
      { label: 'Phases', value: '3 (PRE-PREPARE → PREPARE → COMMIT)' },
    ],
  },
  {
    id: 'poqi',
    icon: '◎',
    color: 'blue',
    label: 'PoQI Reputation',
    title: 'Proof of Quality of Inference',
    subtitle: 'On-chain reputation that rewards consistent model quality',
    body: `Every DNN validator builds a cryptographic reputation score on-chain, updated
deterministically at the end of every consensus round. High-quality validators earn
more block rewards and have higher proposer weight. Byzantine nodes are slashed
automatically — no human intervention required.`,
    stats: [
      { label: 'Max gain / round', value: '0.5 rep' },
      { label: 'Byzantine penalty', value: '−0.3 rep + 100 INFER slashed' },
      { label: 'Leader bonus', value: '+0.1 rep + 2.0 INFER' },
    ],
  },
  {
    id: 'pom',
    icon: '⬡',
    color: 'cyan',
    label: 'Proof of Model',
    title: 'Proof of Model Admission',
    subtitle: 'Cryptographic proof of model capability before admission',
    body: `Before joining QoI rounds, every DNN validator must pass PoM. The protocol
issues 50 deterministically selected CIFAR-10 challenge samples (seed = SHA-256 of
prev block hash + node address). The node must score ≥ 80% accuracy. Existing validators
verify and vote — fail means rejection, pass means admission.`,
    stats: [
      { label: 'Challenge size', value: '50 samples' },
      { label: 'Min accuracy', value: '≥ 80%' },
      { label: 'Verify timeout', value: '30 seconds' },
    ],
  },
  {
    id: 'sbft',
    icon: '⬡',
    color: 'green',
    label: 'S-BFT Sharding',
    title: 'Sharded BFT Architecture',
    subtitle: 'Linear throughput scaling without sacrificing BFT safety',
    body: `Standard PBFT has O(n²) message complexity — unscalable beyond ~100 nodes.
S-BFT partitions the validator set into independent committees, each running QoI
consensus in parallel on separate inference requests. Throughput scales linearly
with committee count. Committee assignment is deterministic and verifiable.`,
    stats: [
      { label: 'Complexity', value: 'O(n) with sharding' },
      { label: 'Safety', value: 'Full BFT per committee' },
      { label: 'Routing', value: 'SHA-256(request) deterministic' },
    ],
  },
  {
    id: 'ood',
    icon: '◉',
    color: 'orange',
    label: 'OOD-Biased Quorum',
    title: 'Knowledge Self-Assessment (KSA)',
    subtitle: 'Quorum biased toward the most domain-familiar validators',
    body: `Every admitted DNN node auto-calibrates an Out-of-Distribution scorer the
moment its NODE_ADMITTED transaction is committed. At inference time, validators are
ranked by their OOD score for the specific input image. A top-2K shortlist of the
most in-distribution nodes is built; K are then sampled deterministically. BFT
determinism is fully preserved — any peer can reproduce the quorum.`,
    stats: [
      { label: 'Primary scorer', value: 'Mahalanobis (penultimate features)' },
      { label: 'Fallback scorer', value: 'Energy (free-energy of logits)' },
      { label: 'Shortlist size', value: 'top-2K eligible nodes' },
    ],
  },
  {
    id: 'llm',
    icon: '✦',
    color: 'purple',
    label: 'LLM Orchestration',
    title: 'LLM Orchestration Layer',
    subtitle: 'Optional AI coordination above the consensus layer',
    body: `An opt-in InferenceOrchestrator sits above the blockchain and provides four
high-level coordination endpoints: intelligent request routing, validator anomaly
detection, multi-task decomposition, and natural-language chain Q&A. It supports
OpenAI, local Ollama, and a deterministic mock provider. The consensus layer remains
fully deterministic regardless of LLM availability.`,
    stats: [
      { label: 'Providers', value: 'OpenAI / Ollama / Mock' },
      { label: 'Endpoints', value: '/llm/route · /llm/analyse · /llm/decompose · /llm/explain' },
      { label: 'Consensus impact', value: 'None — read-only' },
    ],
  },
];

const TOKEN_STATS = [
  { label: 'Token', value: 'INFER' },
  { label: 'Max Supply', value: '100,000,000' },
  { label: 'Genesis Mint', value: '10,000,000' },
  { label: 'Block Reward', value: '10 INFER / QoI round' },
  { label: 'Leader Bonus', value: '+2 INFER' },
  { label: 'Slash Penalty', value: '100 INFER' },
  { label: 'Min Stake DNN', value: '1,000 INFER' },
  { label: 'Min Stake PoS', value: '500 INFER' },
];

const FLOW_STEPS = [
  { n: '01', title: 'Submit Request', body: 'Client hashes image client-side (SHA-256) and submits INFERENCE_REQUEST to the mempool.', color: 'purple' },
  { n: '02', title: 'PRE-PREPARE', body: 'Primary DNN validator runs inference, broadcasts output probability vector to all peers.', color: 'blue' },
  { n: '03', title: 'PREPARE', body: 'Each DNN validator runs the same image locally, broadcasts its vector. Cosine similarity is computed pairwise.', color: 'cyan' },
  { n: '04', title: 'COMMIT', body: 'When 2f+1 PREPAREs agree, COMMIT phase finalises. QoI block is written on-chain with result + reputation deltas.', color: 'green' },
];

// ── Animated counter ──────────────────────────────────────────────────────────
function Counter({ value, suffix = '' }) {
  const [display, setDisplay] = useState(0);
  const ref = useRef();
  useEffect(() => {
    const obs = new IntersectionObserver(([e]) => {
      if (!e.isIntersecting) return;
      obs.disconnect();
      let start = null;
      const num = parseFloat(value.replace(/[^0-9.]/g, '')) || 0;
      const step = (ts) => {
        if (!start) start = ts;
        const p = Math.min((ts - start) / 1200, 1);
        setDisplay((p * num).toFixed(num % 1 ? 1 : 0));
        if (p < 1) requestAnimationFrame(step);
      };
      requestAnimationFrame(step);
    }, { threshold: 0.3 });
    if (ref.current) obs.observe(ref.current);
    return () => obs.disconnect();
  }, [value]);
  return <span ref={ref}>{Number(display).toLocaleString()}{suffix}</span>;
}

// ── Section card with scroll-in animation ─────────────────────────────────────
function SectionCard({ section, idx }) {
  const ref = useRef();
  const [vis, setVis] = useState(false);
  useEffect(() => {
    const obs = new IntersectionObserver(([e]) => {
      if (e.isIntersecting) { setVis(true); obs.disconnect(); }
    }, { threshold: 0.15 });
    if (ref.current) obs.observe(ref.current);
    return () => obs.disconnect();
  }, []);

  return (
    <div
      ref={ref}
      className={`wp-section-card wp-card-${section.color} ${vis ? 'wp-visible' : ''}`}
      style={{ transitionDelay: `${idx * 0.1}s` }}
    >
      <div className="wp-card-header">
        <span className={`wp-card-icon wp-icon-${section.color}`}>{section.icon}</span>
        <div>
          <div className="wp-card-label">{section.label}</div>
          <h3 className="wp-card-title">{section.title}</h3>
          <div className="wp-card-subtitle">{section.subtitle}</div>
        </div>
      </div>
      <p className="wp-card-body">{section.body}</p>
      <div className="wp-card-stats">
        {section.stats.map(s => (
          <div key={s.label} className="wp-stat">
            <span className="wp-stat-label">{s.label}</span>
            <span className={`wp-stat-value wp-val-${section.color}`}>{s.value}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Main ──────────────────────────────────────────────────────────────────────
export default function WhitepaperPage({ navigate }) {
  const heroRef = useRef();

  // Parallax
  useEffect(() => {
    const el = heroRef.current;
    if (!el) return;
    const onMove = (e) => {
      const r = el.getBoundingClientRect();
      el.style.setProperty('--px', `${((e.clientX - r.left) / r.width - 0.5) * 18}px`);
      el.style.setProperty('--py', `${((e.clientY - r.top) / r.height - 0.5) * 18}px`);
    };
    el.addEventListener('mousemove', onMove);
    return () => el.removeEventListener('mousemove', onMove);
  }, []);

  const download = () => {
    const a = document.createElement('a');
    a.href = '/InferenceChain_Whitepaper.pdf';
    a.download = 'InferenceChain_Whitepaper.pdf';
    a.click();
  };

  return (
    <div className="wp-root">

      {/* ── Hero ──────────────────────────────────────────────────────────── */}
      <section className="wp-hero" ref={heroRef}>
        <div className="wp-hero-glow" />
        <div className="wp-hero-grid" />

        <div className="wp-hero-content" style={{
          transform: 'translate(calc(var(--px,0px)*-0.2), calc(var(--py,0px)*-0.2))'
        }}>
          <div className="wp-eyebrow">
            <span className="wp-eyebrow-dot" />
            Technical Whitepaper · v0.5
          </div>

          <div className="wp-hero-logo">⬡</div>

          <h1 className="wp-hero-title">
            InferenceChain
            <br />
            <span className="wp-hero-gradient">Whitepaper</span>
          </h1>

          <p className="wp-hero-sub">
            A decentralised blockchain where DNN validators reach consensus on the
            <em> quality</em> of AI inference results — not just on transaction order.
          </p>

          <div className="wp-hero-actions">
            <button className="btn wp-btn-primary btn-lg" onClick={download}>
              ↓ Download PDF
            </button>
            <a
              className="btn wp-btn-ghost btn-lg"
              href="https://github.com/DimPapaion/AiInferenceChain"
              target="_blank" rel="noreferrer"
            >
              View on GitHub ↗
            </a>
          </div>

          {/* Token quick stats */}
          <div className="wp-token-strip">
            {[
              { label: 'Max Supply',    raw: '100000000', suffix: '' },
              { label: 'Block Reward',  raw: '10',        suffix: ' INFER' },
              { label: 'Min Stake',     raw: '1000',      suffix: ' INFER' },
              { label: 'Slash Penalty', raw: '100',       suffix: ' INFER' },
            ].map(s => (
              <div key={s.label} className="wp-token-stat">
                <span className="wp-token-val">
                  <Counter value={s.raw} suffix={s.suffix} />
                </span>
                <span className="wp-token-label">{s.label}</span>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── Core primitives ───────────────────────────────────────────────── */}
      <section className="wp-primitives page-wrap">
        <div className="wp-sec-header">
          <p className="section-title">Core Innovations</p>
          <h2 className="wp-sec-title">Three primitives. One protocol.</h2>
          <p className="wp-sec-lead">
            Each component solves a specific failure mode of existing approaches.
            Together they form the first blockchain where inference quality is a
            first-class consensus property.
          </p>
        </div>
        <div className="wp-cards-grid">
          {SECTIONS.map((s, i) => <SectionCard key={s.id} section={s} idx={i} />)}
        </div>
      </section>

      {/* ── Consensus flow ────────────────────────────────────────────────── */}
      <section className="wp-flow">
        <div className="page-wrap">
          <p className="section-title">Protocol Flow</p>
          <h2 className="wp-sec-title">From image to committed block</h2>
          <div className="wp-flow-steps">
            {FLOW_STEPS.map((s, i) => (
              <div key={s.n} className={`wp-flow-step wp-flow-${s.color}`}>
                <div className="wp-flow-num">{s.n}</div>
                <div className="wp-flow-connector">
                  <div className="wp-flow-dot" />
                  {i < FLOW_STEPS.length - 1 && <div className="wp-flow-line" />}
                </div>
                <div className="wp-flow-body">
                  <h4>{s.title}</h4>
                  <p>{s.body}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── Tokenomics ────────────────────────────────────────────────────── */}
      <section className="wp-tokenomics page-wrap">
        <p className="section-title">Tokenomics</p>
        <h2 className="wp-sec-title">INFER Token</h2>
        <p className="wp-sec-lead">
          A self-sustaining economic system where quality incentives and security
          incentives are aligned. Stake secures the network; reputation amplifies reward.
        </p>

        <div className="wp-token-grid">
          {TOKEN_STATS.map(s => (
            <div key={s.label} className="wp-token-card">
              <div className="wp-token-card-val">{s.value}</div>
              <div className="wp-token-card-label">{s.label}</div>
            </div>
          ))}
        </div>

        <div className="wp-reward-formula">
          <p className="wp-formula-label">Reward share formula</p>
          <div className="wp-formula-box">
            reward_share(i) = (stake(i) × reputation(i)) / Σ (stake(j) × reputation(j))
          </div>
          <p className="wp-formula-note">
            Quality and capital are equally weighted — pure stake dominance is impossible.
            A node with no reputation earns nothing regardless of stake.
          </p>
        </div>
      </section>

      {/* ── Download CTA ──────────────────────────────────────────────────── */}
      <section className="wp-cta-section page-wrap">
        <div className="wp-cta-card">
          <div className="wp-cta-glow" />
          <div className="wp-cta-icon">⬡</div>
          <h2>Read the full whitepaper</h2>
          <p>
            Complete protocol specification, formal definitions, security proofs,
            tokenomics model, and implementation details.
          </p>
          <div className="wp-cta-actions">
            <button className="btn wp-btn-primary btn-lg" onClick={download}>
              ↓ Download PDF
            </button>
            <button className="btn wp-btn-ghost btn-lg" onClick={() => navigate('join')}>
              Become a Validator →
            </button>
          </div>
        </div>
      </section>

    </div>
  );
}
