import React, { useState, useEffect, useRef } from 'react';
import './NetworkPage.css';
import { p2p as p2pApi, chain as chainApi } from '../api/client';
import { ws as wsUrls } from '../api/client';

const trunc = (s, n = 14) => s ? `${s.slice(0, n)}…` : '—';
const ago = ts => {
  if (!ts) return '—';
  const s = Math.floor(Date.now() / 1000 - ts);
  if (s < 60)   return `${s}s ago`;
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  return `${Math.floor(s / 3600)}h ago`;
};

// ── Pulse dot ─────────────────────────────────────────────────────────────────
function PulseDot({ color = 'green' }) {
  const c = color === 'green' ? 'var(--green)' : color === 'orange' ? 'var(--orange)' : 'var(--red)';
  return <span className="pulse-dot" style={{ '--dot-color': c }} />;
}

// ── Node status card ──────────────────────────────────────────────────────────
function NodeStatusCard({ status }) {
  if (!status) return null;
  return (
    <div className="net-node-card card">
      <p className="section-title">This Node</p>
      <div className="node-status-grid">
        <Row label="Node ID"      val={<span className="hash">{status.node_id}</span>} />
        <Row label="Endpoint"     val={status.endpoint} />
        <Row label="Chain Height" val={status.chain_height} />
        <Row label="Tip Hash"     val={<span className="hash">{trunc(status.tip_hash, 20)}</span>} />
        <Row label="Peers"        val={status.peer_count} />
        <Row label="Mempool"      val={`${status.mempool_size} txs`} />
      </div>
    </div>
  );
}

function Row({ label, val }) {
  return (
    <div className="net-row">
      <span className="net-label">{label}</span>
      <span className="net-val">{val}</span>
    </div>
  );
}

// ── Peers table ───────────────────────────────────────────────────────────────
function PeersTable({ peers }) {
  if (!peers || peers.length === 0)
    return <div className="empty-state" style={{minHeight:80}}>No connected peers</div>;

  return (
    <div className="peers-table-wrap">
      <table className="peers-table">
        <thead>
          <tr>
            <th>Status</th><th>Endpoint</th><th>Node ID</th>
            <th>Height</th><th>Latency</th><th>Last Seen</th>
          </tr>
        </thead>
        <tbody>
          {peers.map((p, i) => {
            const alive  = p.connected !== false;
            const latency = p.latency_ms != null ? `${p.latency_ms} ms` : '—';
            return (
              <tr key={i}>
                <td><PulseDot color={alive ? 'green' : 'red'} /></td>
                <td><span className="hash">{p.endpoint}</span></td>
                <td><span className="hash">{trunc(p.node_id, 14)}</span></td>
                <td>{p.chain_height ?? '—'}</td>
                <td>{latency}</td>
                <td>{ago(p.last_seen)}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

// ── Live event stream ─────────────────────────────────────────────────────────
function LiveStream() {
  const [events,      setEvents]      = useState([]);
  const [wsStatus,    setWsStatus]    = useState('disconnected');
  const wsRef = useRef(null);
  const bottomRef = useRef(null);

  const connect = (url, channel) => {
    const ws = new WebSocket(url);
    ws.onopen    = () => setWsStatus('connected');
    ws.onerror   = () => setWsStatus('error');
    ws.onclose   = () => { setWsStatus('reconnecting'); setTimeout(() => connect(url, channel), 3000); };
    ws.onmessage = (e) => {
      try {
        const msg = JSON.parse(e.data);
        setEvents(prev => [{ ...msg, _id: Date.now() + Math.random(), _ch: channel }, ...prev].slice(0, 100));
      } catch {}
    };
    wsRef.current = ws;
  };

  useEffect(() => {
    connect(wsUrls.consensus, 'consensus');
    return () => wsRef.current?.close();
  }, []);

  const statusColor = wsStatus === 'connected' ? 'green' : wsStatus === 'reconnecting' ? 'orange' : 'red';

  const typeIcon = (t) => {
    if (t === 'consensus_round') return '⬡';
    if (t === 'validator_activity') return '◎';
    if (t === 'model_validation')   return '◈';
    return '·';
  };

  const phaseColor = p => {
    if (p === 'commit') return 'var(--green)';
    if (p === 'pos')    return 'var(--blue)';
    if (p === 'prepare') return 'var(--orange)';
    return 'var(--purple-light)';
  };

  return (
    <div className="live-stream card">
      <div className="stream-header">
        <p className="section-title" style={{margin:0}}>Live Event Stream</p>
        <span className="ws-status">
          <PulseDot color={statusColor} />
          {wsStatus}
        </span>
      </div>

      <div className="stream-log">
        {events.length === 0 ? (
          <div className="empty-state" style={{minHeight:80}}>Waiting for events…</div>
        ) : events.map(ev => (
          <div key={ev._id} className="stream-event">
            <span className="ev-time">
              {new Date((ev.timestamp || Date.now()/1000) * (ev.timestamp > 1e10 ? 1 : 1000))
                .toLocaleTimeString('en-US', { hour12: false })}
            </span>
            <span className="ev-icon" style={{color: phaseColor(ev.phase)}}>{typeIcon(ev.type)}</span>
            <span className="ev-body">
              {ev.type === 'consensus_round' && (
                <>
                  <span className="ev-tag" style={{background: ev.phase==='pos'?'rgba(59,130,246,0.15)':'rgba(124,58,237,0.15)', color: phaseColor(ev.phase)}}>
                    {ev.phase?.toUpperCase() || 'ROUND'}
                  </span>
                  {' '}Block #{ev.round}
                  {ev.status === 'committed' && <span className="ev-commit"> ✓ committed</span>}
                  {ev.participants > 0 && <span className="ev-dim"> · {ev.participants} validators</span>}
                </>
              )}
              {ev.type === 'validator_activity' && (
                <>
                  <span className="ev-tag" style={{background:'rgba(16,185,129,0.12)',color:'var(--green)'}}>VALIDATOR</span>
                  {' '}{trunc(ev.validator_id, 10)} {ev.action}
                </>
              )}
              {ev.type === 'model_validation' && (
                <>
                  <span className="ev-tag" style={{background:'rgba(245,158,11,0.12)',color:'var(--orange)'}}>MODEL</span>
                  {' '}{trunc(ev.model_id, 10)} → {ev.status}
                </>
              )}
            </span>
          </div>
        ))}
        <div ref={bottomRef} />
      </div>

      <div className="stream-footer">
        <span>{events.length} events</span>
        <button className="btn btn-ghost btn-sm" onClick={() => setEvents([])}>Clear</button>
      </div>
    </div>
  );
}

// ── Block time chart (sparkline-ish) ──────────────────────────────────────────
function BlockTimeChart({ blocks }) {
  if (!blocks || blocks.length < 2) return null;
  const times = [];
  for (let i = 1; i < blocks.length; i++) {
    times.push(Math.abs(blocks[i-1].timestamp - blocks[i].timestamp));
  }
  const max = Math.max(...times, 1);
  const avg = (times.reduce((a, b) => a + b, 0) / times.length).toFixed(1);

  return (
    <div className="bt-chart card">
      <div className="bt-header">
        <p className="section-title" style={{margin:0}}>Block Intervals</p>
        <span className="bt-avg">avg {avg}s</span>
      </div>
      <div className="bt-bars">
        {times.map((t, i) => (
          <div
            key={i}
            className="bt-bar"
            style={{ height: `${Math.round((t / max) * 52) + 4}px` }}
            title={`${t.toFixed(1)}s`}
          />
        ))}
      </div>
    </div>
  );
}

// ── Main ──────────────────────────────────────────────────────────────────────
export default function NetworkPage() {
  const [status, setStatus]  = useState(null);
  const [peers,  setPeers]   = useState([]);
  const [blocks, setBlocks]  = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const load = async () => {
      const [s, p, b] = await Promise.allSettled([
        p2pApi.status(),
        p2pApi.peers(),
        chainApi.blocks(20),
      ]);
      if (s.status === 'fulfilled') setStatus(s.value);
      if (p.status === 'fulfilled') setPeers(p.value);
      if (b.status === 'fulfilled') setBlocks(b.value);
      setLoading(false);
    };
    load();
    const id = setInterval(load, 6000);
    return () => clearInterval(id);
  }, []);

  if (loading) return <div className="loading-center" style={{minHeight:'60vh'}}><div className="spinner" />Loading network…</div>;

  return (
    <div className="page-wrap">
      <div className="net-header">
        <div>
          <h2 className="page-title">Network</h2>
          <p className="page-subtitle">Live P2P topology and consensus event stream</p>
        </div>
      </div>

      <div className="net-grid">
        {/* Left column */}
        <div className="net-left">
          <NodeStatusCard status={status} />

          <div className="card" style={{marginTop:16}}>
            <p className="section-title">Peers ({peers.length})</p>
            <PeersTable peers={peers} />
          </div>

          <BlockTimeChart blocks={[...blocks].reverse()} />
        </div>

        {/* Right column: live stream */}
        <div className="net-right">
          <LiveStream />
        </div>
      </div>
    </div>
  );
}
