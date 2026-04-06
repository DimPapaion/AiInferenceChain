import React, { useEffect, useRef, useState } from 'react';
import './LandingPage.css';
import { chain as chainApi } from '../api/client';

const OVERVIEW_CARDS = [
  {
    icon: '◈',
    color: 'purple',
    title: 'Verified AI results',
    subtitle: 'Consensus is about correctness, not just ordering',
    body: `InferenceChain turns inference into a verifiable network action. Multiple DNN validators run the same request independently, compare outputs by cosine similarity, and reach Byzantine-fault-tolerant consensus on quality. Results are committed to an immutable on-chain log.`,
    tags: ['Verified Inference', 'QoI Consensus', 'Byzantine Safety'],
  },
  {
    icon: '◉',
    color: 'blue',
    title: 'Adaptive validator selection',
    subtitle: 'OOD-aware weighting, reliability tracking, hidden challenges',
    body: `InferenceChain uses multi-factor weighting (stake × knowledge × reliability) to select optimal quorums. Out-of-Distribution scoring provides domain familiarity. Per-node reliability is tracked on-chain. Deterministic hidden challenges (15% rate) prevent gaming.`,
    tags: ['S-BFT', 'OOD Bias', 'Reliability Tracking', 'Anti-Gaming'],
  },
  {
    icon: '⬡',
    color: 'cyan',
    title: 'Clear participation paths',
    subtitle: 'Use it, inspect it, or run it',
    body: `The site makes three paths clear: users who submit inference requests and inspect results, researchers who observe protocol mechanics and validator performance, and operators who run consensus nodes. Desktop app included.`,
    tags: ['Wallet', 'Explorer', 'Desktop App', 'Node Operations'],
  },
  {
    icon: '✦',
    color: 'green',
    title: 'Optional AI coordination layer',
    subtitle: 'LLM orchestration is additive, not consensus-critical',
    body: `Optional: OpenAI, Ollama, or mock providers enable advanced features like smart routing, anomaly detection, and chain analysis. The core consensus and OOD-aware validator selection work identically with or without LLM coordination.`,
    tags: ['LLM Orchestration', 'Ollama', 'OpenAI', 'Optional'],
  },
];

const PATHWAYS = [
  {
    id: 'user',
    color: 'purple',
    label: 'For users',
    title: 'Create a wallet and submit inference',
    body: 'Generate or import a wallet, request faucet funds on testnet, send a first transaction, and inspect inference results from the UI.',
    points: ['Open the encrypted wallet panel', 'Fund a testnet address and send a first transaction', 'Submit inference and inspect the committed result'],
    action: { label: 'Open Get Started', target: 'get-started' },
  },
  {
    id: 'operator',
    color: 'blue',
    label: 'For operators',
    title: 'Run a local PoS or DNN node',
    body: 'Boot a local node, connect it to peers, configure a model, and register as a validator. DNN nodes complete Proof of Model before joining inference rounds.',
    points: ['Run a local node from Python', 'Choose PoS-only or DNN validator mode', 'Register stake and complete node admission'],
    action: { label: 'Run a Node', target: 'join' },
  },
  {
    id: 'researcher',
    color: 'green',
    label: 'For researchers',
    title: 'Inspect the protocol and live network state',
    points: ['Use the explorer, validator dashboard, challenge audit trail, and whitepaper to understand consensus, OOD scoring, reliability tracking, and validator weighting.', 'Read the protocol overview in About', 'Inspect blocks, validators, and challenge records', 'Download the technical whitepaper (v0.5 with new features)'],
    action: { label: 'Open About', target: 'about' },
  },
];

const START_STEPS = [
  { n: '01', title: 'Create a wallet', body: 'Open the wallet panel, generate or import keys, and keep the wallet encrypted locally in the browser.', color: 'purple' },
  { n: '02', title: 'Fund and send a transaction', body: 'Use the testnet faucet, send a first transaction, and confirm that it appears in the explorer.', color: 'blue' },
  { n: '03', title: 'Submit inference', body: 'Route an inference request through the chain and inspect the final committed output plus validator responses.', color: 'cyan' },
  { n: '04', title: 'Run a node locally', body: 'Start a local PoS node or a DNN validator from the CLI, connect to peers, and inspect live state in the dashboard.', color: 'green' },
  { n: '05', title: 'Register as validator', body: 'Stake, register the node, and if you run a DNN validator, pass Proof of Model so the network can admit you.', color: 'purple' },
];

const ECOSYSTEM_ITEMS = [
  {
    title: 'Research and articles',
    body: 'Reserve this area for protocol papers, technical articles, and ecosystem writeups. The structure should exist before the content pipeline does.',
    badge: 'Research Hub',
  },
  {
    title: 'Partners and collaborators',
    body: 'Keep a clean placeholder for university labs, infrastructure partners, node operators, and model providers so the homepage can expand without redesign.',
    badge: 'Partners Coming',
  },
  {
    title: 'Network news and releases',
    body: 'Use this later for release notes, benchmark drops, testnet milestones, and validator onboarding announcements without changing the information architecture.',
    badge: 'News Slot',
  },
];

const NODE_CLUSTERS = {
  left: [
    { x: '6%', y: '18%', label: 'Validator-alpha', delay: 0 },
    { x: '14%', y: '42%', label: 'DNN-Node-01', delay: 0.9 },
    { x: '4%', y: '62%', label: 'Validator-beta', delay: 1.6 },
    { x: '20%', y: '73%', label: 'PoS-Node-7', delay: 0.4 },
  ],
  right: [
    { x: '6%', y: '22%', label: 'Validator-gamma', delay: 0.6 },
    { x: '16%', y: '48%', label: 'DNN-Node-08', delay: 1.2 },
    { x: '4%', y: '68%', label: 'Node-12', delay: 0.8 },
    { x: '22%', y: '33%', label: 'Validator-delta', delay: 1.7 },
  ],
};

function AnimatedCounter({ target, duration = 1400 }) {
  const [val, setVal] = useState(0);

  useEffect(() => {
    if (!target) return;
    let start = null;
    const step = (ts) => {
      if (!start) start = ts;
      const progress = Math.min((ts - start) / duration, 1);
      setVal(Math.floor(progress * target));
      if (progress < 1) requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
  }, [target, duration]);

  return <>{val.toLocaleString()}</>;
}

export default function LandingPage({ navigate }) {
  const [stats, setStats] = useState(null);
  const canvasRef = useRef(null);
  const heroRef = useRef(null);
  const animFrameRef = useRef(null);

  useEffect(() => {
    const load = () => chainApi.stats().then(setStats).catch(() => {});
    load();
    const id = setInterval(load, 8000);
    return () => clearInterval(id);
  }, []);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');

    const resize = () => {
      canvas.width = canvas.offsetWidth;
      canvas.height = canvas.offsetHeight;
    };
    resize();
    window.addEventListener('resize', resize);

    const particles = Array.from({ length: 42 }, (_, index) => {
      const left = index < 21;
      return {
        x: left
          ? Math.random() * (canvas.width * 0.35)
          : canvas.width * 0.65 + Math.random() * (canvas.width * 0.35),
        y: Math.random() * canvas.height,
        r: Math.random() * 1.4 + 0.4,
        vx: (Math.random() - 0.5) * 0.28,
        vy: (Math.random() - 0.5) * 0.28,
        alpha: Math.random(),
        dalpha: (Math.random() * 0.008 + 0.002) * (Math.random() > 0.5 ? 1 : -1),
      };
    });

    const draw = () => {
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      ctx.shadowBlur = 0;

      particles.forEach((particle) => {
        particle.x += particle.vx;
        particle.y += particle.vy;
        particle.alpha += particle.dalpha;

        if (particle.alpha <= 0 || particle.alpha >= 1) particle.dalpha *= -1;
        particle.alpha = Math.max(0, Math.min(1, particle.alpha));
        if (particle.x < 0) particle.x = canvas.width;
        if (particle.x > canvas.width) particle.x = 0;
        if (particle.y < 0) particle.y = canvas.height;
        if (particle.y > canvas.height) particle.y = 0;

        ctx.beginPath();
        ctx.arc(particle.x, particle.y, particle.r, 0, Math.PI * 2);
        ctx.fillStyle = `rgba(97,196,255,${particle.alpha * 0.75})`;
        ctx.shadowColor = `rgba(97,196,255,${particle.alpha * 0.5})`;
        ctx.shadowBlur = 8;
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

  useEffect(() => {
    const hero = heroRef.current;
    if (!hero) return;

    const onMove = (event) => {
      const rect = hero.getBoundingClientRect();
      const x = ((event.clientX - rect.left) / rect.width - 0.5) * 22;
      const y = ((event.clientY - rect.top) / rect.height - 0.5) * 22;
      hero.style.setProperty('--parallaxX', `${x}px`);
      hero.style.setProperty('--parallaxY', `${y}px`);
    };

    hero.addEventListener('mousemove', onMove);
    return () => hero.removeEventListener('mousemove', onMove);
  }, []);

  return (
    <div className="landing">
      <section className="hero" ref={heroRef}>
        <canvas ref={canvasRef} className="hero-canvas" />
        <div className="hero-ambient" />
        <div className="hero-grid-fade" />

        <div className="node-cluster node-cluster-left">
          {NODE_CLUSTERS.left.map((node) => (
            <div
              key={node.label}
              className="nc-node"
              style={{ top: node.y, left: node.x, animationDelay: `${node.delay}s` }}
            >
              <span className="nc-dot" />
              <span className="nc-label">{node.label}</span>
            </div>
          ))}
        </div>

        <div className="node-cluster node-cluster-right">
          {NODE_CLUSTERS.right.map((node) => (
            <div
              key={node.label}
              className="nc-node"
              style={{ top: node.y, right: node.x, animationDelay: `${node.delay}s` }}
            >
              <span className="nc-dot" />
              <span className="nc-label">{node.label}</span>
            </div>
          ))}
        </div>

        <svg className="circuit-horizon" viewBox="0 0 1200 220" preserveAspectRatio="none" aria-hidden="true">
          <defs>
            <linearGradient id="lineGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#61c4ff" stopOpacity="0.25" />
              <stop offset="100%" stopColor="#61c4ff" stopOpacity="0" />
            </linearGradient>
            <filter id="glow">
              <feGaussianBlur stdDeviation="2" result="coloredBlur" />
              <feMerge>
                <feMergeNode in="coloredBlur" />
                <feMergeNode in="SourceGraphic" />
              </feMerge>
            </filter>
          </defs>

          {[0, 120, 240, 360, 480, 600, 720, 840, 960, 1080, 1200].map((x) => (
            <line key={x} x1={x} y1="0" x2="600" y2="220" stroke="url(#lineGrad)" strokeWidth="0.8" />
          ))}

          {[40, 80, 130, 175].map((y, index) => {
            const t = y / 220;
            const x1 = 600 - (600 * (1 - t) * 1.05);
            const x2 = 600 + (600 * (1 - t) * 1.05);
            return (
              <line
                key={y}
                x1={Math.max(0, x1)}
                y1={y}
                x2={Math.min(1200, x2)}
                y2={y}
                stroke="#61c4ff"
                strokeOpacity={0.08 + index * 0.04}
                strokeWidth="0.7"
              />
            );
          })}

          {[
            [600, 220],
            [480, 175],
            [720, 175],
            [360, 130],
            [840, 130],
            [240, 80],
            [960, 80],
            [120, 40],
            [1080, 40],
          ].map(([cx, cy]) => (
            <circle
              key={`${cx}-${cy}`}
              cx={cx}
              cy={cy}
              r={cy === 220 ? 4 : 2.5}
              fill="#61c4ff"
              fillOpacity={cy === 220 ? 0.9 : 0.55}
              filter="url(#glow)"
            />
          ))}
        </svg>

        <div
          className="hero-content"
          style={{ transform: 'translate(calc(var(--parallaxX,0px)*-0.25), calc(var(--parallaxY,0px)*-0.25))' }}
        >
          <div className="hero-eyebrow">
            <span className="eyebrow-dot" />
            Research Preview · Testnet v0.5
          </div>

          <h1 className="hero-title">
            The blockchain
            <br />
            <span className="hero-gradient">for verifiable AI inference</span>
          </h1>

          <p className="hero-subtitle">
            InferenceChain is a decentralised AI network where users can submit inference,
            researchers can inspect live protocol state, and operators can run validator nodes.
            Consensus is built around the <em>quality</em> of inference results, not just transaction ordering.
          </p>

          <div className="hero-actions">
            <button className="btn hero-btn-primary btn-lg" onClick={() => navigate('get-started')}>
              Get Started →
            </button>
            <button className="btn hero-btn-ghost btn-lg" onClick={() => navigate('explorer')}>
              Explore Chain
            </button>
          </div>

          {stats && (
            <div className="hero-stats">
              {[
                { label: 'Chain Height', val: stats.chain_height },
                { label: 'Total Txs', val: stats.total_txs },
                { label: 'QoI Blocks', val: stats.qoi_blocks },
                { label: 'DNN Validators', val: stats.dnn_validators },
                { label: 'TPS (60 s)', val: stats.tps },
              ].map((stat) => (
                <div key={stat.label} className="hero-stat">
                  <span className="hero-stat-val">
                    <AnimatedCounter target={stat.val} />
                  </span>
                  <span className="hero-stat-label">{stat.label}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      </section>

      <section className="innovations">
        <div className="page-wrap">
          <div className="innovations-header">
            <p className="section-title">Overview</p>
            <h2>One network. Three clear entry points.</h2>
            <p className="innovations-lead">
              The homepage should explain what the system does before it explains protocol acronyms.
              This is the compact map of the product.
            </p>
          </div>

          <div className="innovations-grid">
            {OVERVIEW_CARDS.map((card) => (
              <div key={card.title} className={`inn-card inn-card-${card.color}`}>
                <div className="inn-icon">{card.icon}</div>
                <div className="inn-header">
                  <h3>{card.title}</h3>
                  <span className="inn-subtitle">{card.subtitle}</span>
                </div>
                <p className="inn-body">{card.body}</p>
                <div className="inn-tags">
                  {card.tags.map((tag) => (
                    <span key={tag} className="inn-tag">{tag}</span>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="pathways-section">
        <div className="page-wrap">
          <div className="innovations-header">
            <p className="section-title">Pathways</p>
            <h2>Choose how you want to enter the network</h2>
            <p className="innovations-lead">
              The surface should make it obvious whether someone is here to use the product,
              operate infrastructure, or study the protocol.
            </p>
          </div>

          <div className="pathways-grid">
            {PATHWAYS.map((path) => (
              <div key={path.id} className={`path-card path-card-${path.color}`}>
                <div className="path-label">{path.label}</div>
                <h3>{path.title}</h3>
                <p>{path.body}</p>
                <div className="path-points">
                  {path.points.map((point) => (
                    <div key={point} className="path-point">{point}</div>
                  ))}
                </div>
                <button className="btn btn-ghost" onClick={() => navigate(path.action.target)}>
                  {path.action.label}
                </button>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="how-it-works">
        <div className="page-wrap">
          <p className="section-title">Get Started</p>
          <h2>From wallet creation to validator admission</h2>

          <div className="flow-steps">
            {START_STEPS.map((step) => (
              <div key={step.n} className={`flow-step flow-step-${step.color}`}>
                <div className="flow-num">{step.n}</div>
                <div className="flow-content">
                  <h4>{step.title}</h4>
                  <p>{step.body}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="ecosystem-section">
        <div className="page-wrap">
          <div className="innovations-header">
            <p className="section-title">Ecosystem</p>
            <h2>Leave room for the network to grow into itself</h2>
            <p className="innovations-lead">
              These are intentional placeholders for future partners, release notes, and research coverage
              so the site does not need a structural rewrite later.
            </p>
          </div>

          <div className="ecosystem-grid">
            {ECOSYSTEM_ITEMS.map((item) => (
              <div key={item.title} className="ecosystem-card">
                <div className="ecosystem-badge">{item.badge}</div>
                <h3>{item.title}</h3>
                <p>{item.body}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="cta-section">
        <div className="page-wrap">
          <div className="cta-card">
            <div className="cta-glow" />
            <h2>Start with the path that matches your role</h2>
            <p>Get onboarded as a user, inspect the protocol as a researcher, or prepare a local validator node.</p>
            <div className="cta-actions">
              <button className="btn btn-primary btn-lg" onClick={() => navigate('get-started')}>
                Open Get Started →
              </button>
              <button className="btn btn-ghost btn-lg" onClick={() => navigate('about')}>
                Read About
              </button>
            </div>
          </div>
        </div>
      </section>
    </div>
  );
}
