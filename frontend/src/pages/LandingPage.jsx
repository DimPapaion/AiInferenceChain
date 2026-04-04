import React, { useEffect, useState, useRef } from 'react';
import './LandingPage.css';
import { chain as chainApi } from '../api/client';

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

const NODE_CLUSTERS = {
  left: [
    { x: '6%',  y: '18%', label: 'Validator-α', delay: 0 },
    { x: '14%', y: '42%', label: 'DNN-Node-01',  delay: 0.9 },
    { x: '4%',  y: '62%', label: 'Validator-β', delay: 1.6 },
    { x: '20%', y: '73%', label: 'PoS-Node-7',  delay: 0.4 },
  ],
  right: [
    { x: '6%',  y: '22%', label: 'Validator-γ', delay: 0.6 },
    { x: '16%', y: '48%', label: 'DNN-Node-08', delay: 1.2 },
    { x: '4%',  y: '68%', label: 'Node-12',     delay: 0.8 },
    { x: '22%', y: '33%', label: 'Validator-δ', delay: 1.7 },
  ],
};

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
  const [stats,   setStats]   = useState(null);
  const canvasRef             = useRef(null);
  const heroRef               = useRef(null);
  const animFrameRef          = useRef(null);

  // Live stats
  useEffect(() => {
    const load = () => chainApi.stats().then(setStats).catch(() => {});
    load();
    const id = setInterval(load, 8000);
    return () => clearInterval(id);
  }, []);

  // Canvas particle system
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');

    const resize = () => {
      canvas.width  = canvas.offsetWidth;
      canvas.height = canvas.offsetHeight;
    };
    resize();
    window.addEventListener('resize', resize);

    // 42 particles spread to left and right sides
    const particles = Array.from({ length: 42 }, (_, i) => {
      const left = i < 21;
      return {
        x: left
          ? Math.random() * (canvas.width * 0.35)
          : canvas.width * 0.65 + Math.random() * (canvas.width * 0.35),
        y:      Math.random() * canvas.height,
        r:      Math.random() * 1.4 + 0.4,
        vx:     (Math.random() - 0.5) * 0.28,
        vy:     (Math.random() - 0.5) * 0.28,
        alpha:  Math.random(),
        dalpha: (Math.random() * 0.008 + 0.002) * (Math.random() > 0.5 ? 1 : -1),
      };
    });

    const draw = () => {
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      ctx.shadowBlur  = 0;
      particles.forEach(p => {
        p.x += p.vx;  p.y += p.vy;
        p.alpha += p.dalpha;
        if (p.alpha <= 0 || p.alpha >= 1) p.dalpha *= -1;
        p.alpha = Math.max(0, Math.min(1, p.alpha));
        if (p.x < 0)            p.x = canvas.width;
        if (p.x > canvas.width) p.x = 0;
        if (p.y < 0)            p.y = canvas.height;
        if (p.y > canvas.height) p.y = 0;

        ctx.beginPath();
        ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
        ctx.fillStyle = `rgba(97,196,255,${p.alpha * 0.75})`;
        ctx.shadowColor = `rgba(97,196,255,${p.alpha * 0.5})`;
        ctx.shadowBlur  = 8;
        ctx.fill();
        ctx.shadowBlur = 0;
      });
      animFrameRef.current = requestAnimationFrame(draw);
    };
    draw();

    return () => {
      window.removeEventListener('resize', resize);
      if (animFrameRef.current) cancelAnimationFrame(animFrameRef.current);
    };
  }, []);

  // Parallax on mousemove
  useEffect(() => {
    const hero = heroRef.current;
    if (!hero) return;
    const onMove = (e) => {
      const rect = hero.getBoundingClientRect();
      const x = ((e.clientX - rect.left)  / rect.width  - 0.5) * 22;
      const y = ((e.clientY - rect.top)   / rect.height - 0.5) * 22;
      hero.style.setProperty('--parallaxX', `${x}px`);
      hero.style.setProperty('--parallaxY', `${y}px`);
    };
    hero.addEventListener('mousemove', onMove);
    return () => hero.removeEventListener('mousemove', onMove);
  }, []);

  return (
    <div className="landing">

      {/* ── Hero ─────────────────────────────────────────────────────────── */}
      <section className="hero" ref={heroRef}>

        {/* Canvas particles */}
        <canvas ref={canvasRef} className="hero-canvas" />

        {/* Ambient glow orb */}
        <div className="hero-ambient" />

        {/* Grid / circuit overlay */}
        <div className="hero-grid-fade" />

        {/* Left node cluster */}
        <div className="node-cluster node-cluster-left">
          {NODE_CLUSTERS.left.map((n, i) => (
            <div
              key={i}
              className="nc-node"
              style={{ top: n.y, left: n.x, animationDelay: `${n.delay}s` }}
            >
              <span className="nc-dot" />
              <span className="nc-label">{n.label}</span>
            </div>
          ))}
        </div>

        {/* Right node cluster */}
        <div className="node-cluster node-cluster-right">
          {NODE_CLUSTERS.right.map((n, i) => (
            <div
              key={i}
              className="nc-node"
              style={{ top: n.y, right: n.x, animationDelay: `${n.delay}s` }}
            >
              <span className="nc-dot" />
              <span className="nc-label">{n.label}</span>
            </div>
          ))}
        </div>

        {/* Circuit horizon SVG */}
        <svg
          className="circuit-horizon"
          viewBox="0 0 1200 220"
          preserveAspectRatio="none"
          aria-hidden="true"
        >
          <defs>
            <linearGradient id="lineGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#61c4ff" stopOpacity="0.25" />
              <stop offset="100%" stopColor="#61c4ff" stopOpacity="0" />
            </linearGradient>
            <filter id="glow">
              <feGaussianBlur stdDeviation="2" result="coloredBlur"/>
              <feMerge>
                <feMergeNode in="coloredBlur"/>
                <feMergeNode in="SourceGraphic"/>
              </feMerge>
            </filter>
          </defs>

          {/* Perspective radiating lines from vanishing point */}
          {[0, 120, 240, 360, 480, 600, 720, 840, 960, 1080, 1200].map((x, i) => (
            <line
              key={i}
              x1={x} y1="0"
              x2="600" y2="220"
              stroke="url(#lineGrad)"
              strokeWidth="0.8"
            />
          ))}

          {/* Horizontal circuit cross-lines */}
          {[40, 80, 130, 175].map((y, i) => {
            const t = y / 220;
            const x1 = 600 - (600 * (1 - t) * 1.05);
            const x2 = 600 + (600 * (1 - t) * 1.05);
            return (
              <line
                key={i}
                x1={Math.max(0, x1)} y1={y}
                x2={Math.min(1200, x2)} y2={y}
                stroke="#61c4ff"
                strokeOpacity={0.08 + i * 0.04}
                strokeWidth="0.7"
              />
            );
          })}

          {/* Glowing dot nodes at intersections */}
          {[
            [600, 220], [480, 175], [720, 175],
            [360, 130], [840, 130], [240, 80],
            [960, 80],  [120, 40],  [1080, 40],
          ].map(([cx, cy], i) => (
            <circle
              key={i}
              cx={cx} cy={cy}
              r={cy === 220 ? 4 : 2.5}
              fill="#61c4ff"
              fillOpacity={cy === 220 ? 0.9 : 0.55}
              filter="url(#glow)"
            />
          ))}
        </svg>

        {/* Hero content — parallax shift applied */}
        <div
          className="hero-content"
          style={{
            transform: 'translate(calc(var(--parallaxX,0px)*-0.25), calc(var(--parallaxY,0px)*-0.25))',
          }}
        >
          <div className="hero-eyebrow">
            <span className="eyebrow-dot" />
            Research Preview · Testnet v0.1
          </div>

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
            <button className="btn hero-btn-primary btn-lg" onClick={() => navigate('explorer')}>
              Open Explorer →
            </button>
            <button className="btn hero-btn-ghost btn-lg" onClick={() => navigate('inference')}>
              Submit Inference
            </button>
          </div>

          {/* Live mini-stats */}
          {stats && (
            <div className="hero-stats">
              {[
                { label: 'Chain Height',   val: stats.chain_height },
                { label: 'Total Txs',      val: stats.total_txs },
                { label: 'QoI Blocks',     val: stats.qoi_blocks },
                { label: 'DNN Validators', val: stats.dnn_validators },
                { label: 'TPS (60 s)',     val: stats.tps },
              ].map(s => (
                <div key={s.label} className="hero-stat">
                  <span className="hero-stat-val">
                    <AnimatedCounter target={s.val} />
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
