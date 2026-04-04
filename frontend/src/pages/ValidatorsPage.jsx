import React, { useState, useEffect } from 'react';
import './ValidatorsPage.css';
import { state as stateApi, dashboard } from '../api/client';

const trunc = (s, n = 10) => s ? `${s.slice(0, n)}…` : '—';
const REP_INITIAL = 1.0;   // matches INITIAL_REPUTATION in chain.py

function RepBar({ value }) {
  const pct   = Math.min(Math.max(value / 2.0, 0), 1) * 100; // 0-2 range → 0-100%
  const color = value >= 1.0 ? 'var(--green)' : value >= 0.5 ? 'var(--orange)' : 'var(--red)';
  return (
    <div className="rep-bar-wrap">
      <div className="rep-bar-bg">
        <div className="rep-bar-fill" style={{ width: `${pct}%`, background: color }} />
      </div>
      <span className="rep-val" style={{ color }}>{value.toFixed(4)}</span>
    </div>
  );
}

function StakeBar({ value, max }) {
  const pct = max > 0 ? (value / max) * 100 : 0;
  return (
    <div className="stake-bar-wrap">
      <div className="stake-bar-bg">
        <div className="stake-bar-fill" style={{ width: `${pct}%` }} />
      </div>
      <span className="stake-val">{value.toLocaleString()} IC</span>
    </div>
  );
}

function ValidatorCard({ node, rank, state }) {
  const [expanded, setExpanded] = useState(false);
  const stake = state?.stake_of?.[node.address] ?? node.stake ?? 0;
  const rep   = state?.rep_of?.[node.address]   ?? node.reputation ?? REP_INITIAL;

  return (
    <div className={`val-card ${expanded ? 'expanded' : ''}`}>
      <div className="val-card-main" onClick={() => setExpanded(e => !e)}>
        <div className="val-rank">#{rank}</div>

        <div className="val-info">
          <div className="val-top">
            <span className={`badge badge-${node.node_type}`}>{node.node_type.toUpperCase()}</span>
            {node.pom_verified && <span className="badge badge-ok">PoM ✓</span>}
            {node.is_active    && <span className="badge badge-ok">Active</span>}
          </div>
          <div className="val-id">
            <span className="hash mono">{trunc(node.node_id, 16)}</span>
            {node.model_name && (
              <span className="val-model">{node.model_name}</span>
            )}
          </div>
          <div className="val-endpoint">{node.endpoint}</div>
        </div>

        <div className="val-metrics">
          <div className="metric-group">
            <span className="metric-label">Reputation</span>
            <RepBar value={rep} />
          </div>
          <div className="metric-group">
            <span className="metric-label">Stake</span>
            <span className="stake-num">{stake.toLocaleString()} IC</span>
          </div>
        </div>

        <button className="expand-btn">{expanded ? '▲' : '▼'}</button>
      </div>

      {expanded && (
        <div className="val-expanded">
          <div className="val-detail-grid">
            <Row label="Node ID"      val={<span className="hash">{node.node_id}</span>} />
            <Row label="Address"      val={<span className="hash">{node.address}</span>} />
            <Row label="Public Key"   val={<span className="hash">{trunc(node.public_key, 20)}</span>} />
            <Row label="Endpoint"     val={node.endpoint} />
            <Row label="Node Type"    val={node.node_type} />
            <Row label="Model"        val={node.model_name || '—'} />
            <Row label="Weights Hash" val={<span className="hash">{trunc(node.weights_hash, 20)}</span>} />
            <Row label="Dataset"      val={node.dataset_id || '—'} />
            <Row label="Registered"   val={`Block #${node.registered_at}`} />
            <Row label="PoM Verified" val={node.pom_verified ? 'Yes' : 'No'} />
            <Row label="Reputation"   val={<RepBar value={rep} />} />
            <Row label="Stake"        val={`${stake.toLocaleString()} IC`} />
          </div>
        </div>
      )}
    </div>
  );
}

function Row({ label, val }) {
  return (
    <div className="vd-row">
      <span className="vd-label">{label}</span>
      <span className="vd-val">{val}</span>
    </div>
  );
}

function SummaryStats({ nodes, chainState }) {
  const total = nodes.length;
  const dnn   = nodes.filter(n => n.node_type === 'dnn').length;
  const pos   = nodes.filter(n => n.node_type === 'pos').length;
  const totalStake = nodes.reduce((s, n) => s + (n.stake ?? 0), 0);
  const avgRep     = total
    ? (nodes.reduce((s, n) => s + (n.reputation ?? REP_INITIAL), 0) / total).toFixed(4)
    : '—';

  return (
    <div className="val-summary">
      {[
        { label: 'Total Nodes',   val: total },
        { label: 'DNN Validators',val: dnn },
        { label: 'PoS Nodes',     val: pos },
        { label: 'Total Stake',   val: `${totalStake.toLocaleString()} IC` },
        { label: 'Avg Reputation',val: avgRep },
      ].map(s => (
        <div key={s.label} className="val-summary-stat">
          <span className="val-sum-val">{s.val}</span>
          <span className="val-sum-label">{s.label}</span>
        </div>
      ))}
    </div>
  );
}

export default function ValidatorsPage() {
  const [nodes,   setNodes]   = useState([]);
  const [filter,  setFilter]  = useState('all');   // all | dnn | pos
  const [sortBy,  setSortBy]  = useState('reputation'); // reputation | stake
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const load = () => {
      stateApi.active()
        .then(data => { setNodes(Array.isArray(data) ? data : []); setLoading(false); })
        .catch(() => setLoading(false));
    };
    load();
    const id = setInterval(load, 8000);
    return () => clearInterval(id);
  }, []);

  const filtered = nodes
    .filter(n => filter === 'all' || n.node_type === filter)
    .sort((a, b) => {
      if (sortBy === 'reputation') return (b.reputation ?? REP_INITIAL) - (a.reputation ?? REP_INITIAL);
      return (b.stake ?? 0) - (a.stake ?? 0);
    });

  const maxStake = Math.max(...filtered.map(n => n.stake ?? 0), 1);

  return (
    <div className="page-wrap">
      <div className="val-page-header">
        <div>
          <h2 className="page-title">Validator Network</h2>
          <p className="page-subtitle">
            On-chain DNN and PoS nodes ranked by QoI reputation score
          </p>
        </div>
      </div>

      <SummaryStats nodes={nodes} />

      {/* Controls */}
      <div className="val-controls">
        <div className="filter-group">
          {[
            { id: 'all', label: 'All Nodes' },
            { id: 'dnn', label: 'DNN Validators' },
            { id: 'pos', label: 'PoS Nodes' },
          ].map(f => (
            <button
              key={f.id}
              className={`filter-btn ${filter === f.id ? 'active' : ''}`}
              onClick={() => setFilter(f.id)}
            >
              {f.label}
            </button>
          ))}
        </div>
        <div className="sort-group">
          <span className="sort-label">Sort:</span>
          <button
            className={`filter-btn ${sortBy === 'reputation' ? 'active' : ''}`}
            onClick={() => setSortBy('reputation')}
          >
            Reputation
          </button>
          <button
            className={`filter-btn ${sortBy === 'stake' ? 'active' : ''}`}
            onClick={() => setSortBy('stake')}
          >
            Stake
          </button>
        </div>
      </div>

      {/* List */}
      {loading ? (
        <div className="loading-center"><div className="spinner" />Loading validators…</div>
      ) : filtered.length === 0 ? (
        <div className="empty-state">No active nodes on-chain yet</div>
      ) : (
        <div className="val-list">
          {filtered.map((n, i) => (
            <ValidatorCard
              key={n.node_id}
              node={n}
              rank={i + 1}
              state={{ stake_of: {}, rep_of: {} }}
            />
          ))}
        </div>
      )}
    </div>
  );
}
