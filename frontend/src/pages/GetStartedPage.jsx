import React from 'react';
import './GetStartedPage.css';

const USER_STEPS = [
  {
    n: '01',
    title: 'Create or import a wallet',
    body: 'Open the wallet panel from the top-right corner. Generate a new wallet or import an existing one. Keys stay encrypted in the browser with AES-GCM.',
  },
  {
    n: '02',
    title: 'Request testnet funds',
    body: 'Use the faucet endpoint to fund your account for local or testnet experimentation. Then confirm the balance from the dashboard or chain state routes.',
  },
  {
    n: '03',
    title: 'Send a transaction or submit inference',
    body: 'Start by sending a simple transaction, then move to the inference page to submit an AI request and inspect its final committed result.',
  },
];

const OPERATOR_PATHS = [
  {
    label: 'PoS validator',
    title: 'Run a consensus-only node',
    body: 'Stake INFER, run the node without a model, connect to peers, and participate in PoS block production.',
    command: 'python node_runner.py --port 8000 --private-key <hex_private_key>',
  },
  {
    label: 'DNN validator',
    title: 'Run a model-backed validator',
    body: 'Download the InferenceChain desktop app, upload your architecture file, connect a dataset, configure training in the hyperparameter panel, and submit your signed checkpoint — no command line required.',
    command: '↓ Download the desktop app from inferencechain.io/run-a-node',
    isDownload: true,
  },
  {
    label: 'LLM-enabled node',
    title: 'Enable orchestration endpoints',
    body: 'If you want the optional orchestration layer, start the node with Ollama, OpenAI, or the deterministic mock provider.',
    command: 'python node_runner.py --llm-provider ollama --llm-model llama3.2',
  },
];

const RESOURCES = [
  {
    title: 'Explore Chain',
    body: 'Inspect blocks, transactions, validators, network state, and inference activity from the dashboard routes.',
    target: 'explorer',
    action: 'Open Explorer',
  },
  {
    title: 'About',
    body: 'Read the product and protocol overview online, then move into the whitepaper when you want the formal technical layer.',
    target: 'about',
    action: 'Open About',
  },
  {
    title: 'Run a Node',
    body: 'Go directly to the node participation page when you are ready to join as a PoS or DNN validator.',
    target: 'join',
    action: 'Run a Node',
  },
];

export default function GetStartedPage({ navigate }) {
  return (
    <div className="gs-root">
      <section className="gs-hero page-wrap">
        <div className="gs-hero-shell">
          <div className="gs-kicker">Get Started</div>
          <h1>From first wallet to local validator</h1>
          <p>
            This page is the product onboarding path: create a wallet, fund an account,
            submit inference, explore the chain, and only then move into validator operation
            if that is your goal.
          </p>
          <div className="gs-hero-actions">
            <button className="btn btn-primary btn-lg" onClick={() => navigate('home')}>
              Back to Home
            </button>
            <button className="btn btn-ghost btn-lg" onClick={() => navigate('about')}>
              Open About
            </button>
          </div>
        </div>
      </section>

      <section className="gs-section page-wrap">
        <div className="gs-section-head">
          <p className="section-title">For users</p>
          <h2>Do the first useful things quickly</h2>
          <p>
            A product should get someone to a successful first transaction or inference request fast.
            These are the minimum steps.
          </p>
        </div>

        <div className="gs-timeline">
          {USER_STEPS.map((step) => (
            <div key={step.n} className="gs-step">
              <div className="gs-step-num">{step.n}</div>
              <div className="gs-step-body">
                <h3>{step.title}</h3>
                <p>{step.body}</p>
              </div>
            </div>
          ))}
        </div>
      </section>

      <section className="gs-section gs-ops-section">
        <div className="page-wrap">
          <div className="gs-section-head">
            <p className="section-title">For operators</p>
            <h2>Pick the node path that matches your role</h2>
            <p>
              PoS validators, DNN validators, and LLM-enabled nodes all share the same network
              but require different startup choices.
            </p>
          </div>

          <div className="gs-ops-grid">
            {OPERATOR_PATHS.map((path) => (
              <div key={path.label} className="gs-ops-card">
                <div className="gs-ops-label">{path.label}</div>
                <h3>{path.title}</h3>
                <p>{path.body}</p>
                {path.isDownload ? (
                  <a
                    className="btn btn-primary"
                    href="https://github.com/DimPapaion/AiInferenceChain/blob/main/DEPLOYMENT_GUIDE.md"
                    target="_blank"
                    rel="noreferrer"
                    style={{ display: 'inline-flex', marginTop: 4 }}
                  >
                    ↓ Download Desktop App
                  </a>
                ) : (
                  <div className="gs-command">{path.command}</div>
                )}
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="gs-section page-wrap">
        <div className="gs-section-head">
          <p className="section-title">Next Stops</p>
          <h2>Use the rest of the site intentionally</h2>
          <p>
            Once onboarding is clear, the rest of the surface can stay focused on exploration,
            research, and operations.
          </p>
        </div>

        <div className="gs-resource-grid">
          {RESOURCES.map((resource) => (
            <div key={resource.title} className="gs-resource-card">
              <h3>{resource.title}</h3>
              <p>{resource.body}</p>
              <button className="btn btn-ghost" onClick={() => navigate(resource.target)}>
                {resource.action}
              </button>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}