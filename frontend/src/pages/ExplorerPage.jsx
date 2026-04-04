import React, { useState, useEffect, useCallback, useRef } from 'react';
import './ExplorerPage.css';
import { chain as chainApi, tx as txApi, state as stateApi } from '../api/client';

// ── Helpers ──────────────────────────────────────────────────────────────────
const trunc = (s, n = 10) => s ? `${s.slice(0,n)}…` : '—';
const ago   = ts => {
  if (!ts) return '—';
  const s = Math.floor(Date.now()/1000 - ts);
  if (s < 60)   return `${s}s ago`;
  if (s < 3600) return `${Math.floor(s/60)}m ago`;
  return `${Math.floor(s/3600)}h ago`;
};
const typeColor = t => t === 'qoi' ? 'badge-dnn' : 'badge-pos';
const typeLabel = t => t === 'qoi' ? 'QoI' : 'PoS';

// ── Stats row ─────────────────────────────────────────────────────────────────
function StatsRow({ stats }) {
  if (!stats) return null;
  const pct = stats.total_blocks > 0
    ? Math.round(stats.qoi_blocks / stats.total_blocks * 100) : 0;
  return (
    <div className="exp-stats-row">
      {[
        { label: 'Height',        val: stats.chain_height.toLocaleString() },
        { label: 'Total Blocks',  val: stats.total_blocks.toLocaleString() },
        { label: 'QoI Blocks',    val: `${stats.qoi_blocks} (${pct}%)` },
        { label: 'Total TXs',     val: stats.total_txs.toLocaleString() },
        { label: 'TPS (60s)',     val: stats.tps },
        { label: 'Avg Block Time',val: stats.avg_block_time ? `${stats.avg_block_time}s` : '—' },
        { label: 'Mempool',       val: stats.mempool_size },
        { label: 'DNN Validators',val: stats.dnn_validators },
      ].map(s => (
        <div key={s.label} className="exp-stat">
          <span className="exp-stat-val">{s.val}</span>
          <span className="exp-stat-label">{s.label}</span>
        </div>
      ))}
    </div>
  );
}

// ── Block row ─────────────────────────────────────────────────────────────────
function BlockRow({ blk, selected, onClick }) {
  return (
    <tr className={`blk-row ${selected ? 'selected' : ''}`} onClick={onClick}>
      <td><span className="blk-height">#{blk.height}</span></td>
      <td><span className={`badge ${typeColor(blk.block_type)}`}>{typeLabel(blk.block_type)}</span></td>
      <td><span className="hash">{trunc(blk.hash, 14)}</span></td>
      <td><span className="hash">{trunc(blk.proposer_id, 12)}</span></td>
      <td>{blk.tx_count}</td>
      <td className="time-col">{ago(blk.timestamp)}</td>
    </tr>
  );
}

// ── Block detail ──────────────────────────────────────────────────────────────
function BlockDetail({ height, onClose }) {
  const [blk,  setBlk]  = useState(null);
  const [load, setLoad] = useState(true);

  useEffect(() => {
    setLoad(true);
    chainApi.block(height).then(b => { setBlk(b); setLoad(false); }).catch(() => setLoad(false));
  }, [height]);

  if (load) return (
    <div className="blk-detail card">
      <div className="loading-center"><div className="spinner" />Loading block…</div>
    </div>
  );
  if (!blk) return null;

  const h = blk.header;
  const allTxs = [
    ...(blk.system_txs   || []).map(t => ({ ...t, _cat: 'system' })),
    ...(blk.inference_tx ? [{ ...blk.inference_tx, _cat: 'inference' }] : []),
    ...(blk.simple_txs   || []).map(t => ({ ...t, _cat: 'simple' })),
  ];

  return (
    <div className="blk-detail card">
      <div className="detail-header">
        <h3>Block #{h.height} <span className={`badge ${typeColor(h.block_type)}`}>{typeLabel(h.block_type)}</span></h3>
        <button className="btn btn-ghost btn-sm" onClick={onClose}>✕ Close</button>
      </div>

      <div className="detail-grid">
        <Row label="Hash"         val={<span className="hash">{h.hash}</span>} />
        <Row label="Prev Hash"    val={<span className="hash">{h.prev_hash}</span>} />
        <Row label="Proposer"     val={<span className="hash">{h.proposer_id}</span>} />
        <Row label="Timestamp"    val={new Date(h.timestamp * 1000).toLocaleString()} />
        <Row label="Merkle Root"  val={<span className="hash">{h.merkle_root}</span>} />
        <Row label="View"         val={h.view} />
        <Row label="Consensus"    val={
          <span>
            {blk.consensus?.type}
            {blk.consensus?.signatures?.length > 0 &&
              ` · ${blk.consensus.signatures.length} sigs`}
          </span>
        } />
        <Row label="Transactions" val={blk.tx_count} />
      </div>

      {allTxs.length > 0 && (
        <>
          <p className="section-title" style={{marginTop:20}}>Transactions ({allTxs.length})</p>
          <div className="tx-table-wrap">
            <table className="tx-table">
              <thead>
                <tr><th>Category</th><th>Type</th><th>Sender</th><th>Fee</th><th>Payload</th></tr>
              </thead>
              <tbody>
                {allTxs.map((t, i) => (
                  <tr key={i}>
                    <td><span className={`badge badge-${t._cat === 'inference' ? 'dnn' : t._cat === 'system' ? 'warn' : 'pos'}`}>{t._cat}</span></td>
                    <td><span className="hash">{t.tx_type || '—'}</span></td>
                    <td><span className="hash">{trunc(t.sender, 12)}</span></td>
                    <td>{t.fee ?? '—'}</td>
                    <td className="payload-cell"><span className="hash">{JSON.stringify(t.payload).slice(0, 60)}…</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}

function Row({ label, val }) {
  return (
    <div className="detail-row">
      <span className="detail-label">{label}</span>
      <span className="detail-val">{val}</span>
    </div>
  );
}

// ── Mempool / recent txs ──────────────────────────────────────────────────────
function TxPanel({ selectedTx, onSelectTx }) {
  const [txs,  setTxs]  = useState([]);
  const [load, setLoad] = useState(true);

  useEffect(() => {
    const fetch = () =>
      txApi.pending().then(data => { setTxs(Array.isArray(data) ? data.slice(0, 30) : []); setLoad(false); }).catch(() => setLoad(false));
    fetch();
    const id = setInterval(fetch, 4000);
    return () => clearInterval(id);
  }, []);

  if (load) return <div className="loading-center"><div className="spinner" /></div>;

  return (
    <div className="tx-panel">
      <p className="section-title">Mempool ({txs.length})</p>
      {txs.length === 0
        ? <div className="empty-state">No pending transactions</div>
        : (
          <div className="tx-list">
            {txs.map((t, i) => (
              <div
                key={t.tx_id || i}
                className={`tx-item ${selectedTx?.tx_id === t.tx_id ? 'selected' : ''}`}
                onClick={() => onSelectTx(t)}
              >
                <div className="tx-item-top">
                  <span className="badge badge-pending">{t.tx_type}</span>
                  <span className="tx-fee">{t.fee} IC</span>
                </div>
                <span className="hash">{trunc(t.tx_id, 16)}</span>
                <span className="hash" style={{fontSize:11}}>{trunc(t.sender, 14)}</span>
              </div>
            ))}
          </div>
        )
      }
    </div>
  );
}

// ── Address / TX lookup ────────────────────────────────────────────────────────
function LookupResult({ query, onClose }) {
  const [result, setResult] = useState(null);
  const [kind,   setKind]   = useState(null);  // 'block'|'tx'|'address'|'node'
  const [load,   setLoad]   = useState(true);
  const [error,  setError]  = useState(null);

  useEffect(() => {
    if (!query) return;
    setLoad(true); setError(null);

    const tryAll = async () => {
      // integer → block height
      if (/^\d+$/.test(query)) {
        const b = await chainApi.block(parseInt(query, 10)).catch(() => null);
        if (b) { setResult(b); setKind('block'); return; }
      }
      // 64-char hex → block hash or tx
      if (/^[0-9a-fA-F]{20,}$/.test(query)) {
        const t = await txApi.get(query).catch(() => null);
        if (t && t.status !== 'not_found') { setResult(t); setKind('tx'); return; }
        const b = await chainApi.blockByHash(query).catch(() => null);
        if (b) { setResult(b); setKind('block'); return; }
        // Try as address
        const a = await stateApi.balance(query).catch(() => null);
        if (a) { setResult(a); setKind('address'); return; }
        const n = await stateApi.node(query).catch(() => null);
        if (n) { setResult(n); setKind('node'); return; }
      }
      setError(`Nothing found for "${query}"`);
    };

    tryAll().finally(() => setLoad(false));
  }, [query]);

  if (load) return <div className="lookup-panel card"><div className="loading-center"><div className="spinner" />Searching…</div></div>;
  if (error) return <div className="lookup-panel card"><div className="empty-state">{error}<button className="btn btn-ghost btn-sm" style={{marginTop:8}} onClick={onClose}>Clear</button></div></div>;
  if (!result) return null;

  return (
    <div className="lookup-panel card">
      <div className="detail-header">
        <h3 style={{textTransform:'capitalize'}}>{kind} Result</h3>
        <button className="btn btn-ghost btn-sm" onClick={onClose}>✕</button>
      </div>
      {kind === 'tx' && <TxResult data={result} />}
      {kind === 'block' && <BlockSummary data={result} />}
      {kind === 'address' && <AddressResult data={result} />}
      {kind === 'node' && <NodeResult data={result} />}
    </div>
  );
}

function TxResult({ data }) {
  return (
    <div className="detail-grid">
      <Row label="TX ID"    val={<span className="hash">{data.tx_id}</span>} />
      <Row label="Status"   val={<span className={`badge ${data.status === 'confirmed' ? 'badge-ok' : 'badge-pending'}`}>{data.status}</span>} />
      <Row label="Type"     val={data.tx_type || '—'} />
      <Row label="Sender"   val={<span className="hash">{data.sender || '—'}</span>} />
      <Row label="Block"    val={data.block_height ?? '—'} />
      <Row label="Payload"  val={<pre className="payload-pre">{JSON.stringify(data.payload, null, 2)}</pre>} />
    </div>
  );
}
function BlockSummary({ data }) {
  const h = data.header || {};
  return (
    <div className="detail-grid">
      <Row label="Height"   val={h.height} />
      <Row label="Type"     val={<span className={`badge ${typeColor(h.block_type)}`}>{h.block_type}</span>} />
      <Row label="Hash"     val={<span className="hash">{h.hash}</span>} />
      <Row label="Proposer" val={<span className="hash">{h.proposer_id}</span>} />
      <Row label="TXs"      val={data.tx_count} />
      <Row label="Time"     val={new Date((h.timestamp || 0)*1000).toLocaleString()} />
    </div>
  );
}
function AddressResult({ data }) {
  return (
    <div className="detail-grid">
      <Row label="Address"    val={<span className="hash">{data.address}</span>} />
      <Row label="Balance"    val={`${data.balance} IC`} />
      <Row label="Stake"      val={`${data.stake} IC`} />
      <Row label="Reputation" val={data.reputation?.toFixed(4)} />
      <Row label="Nonce"      val={data.nonce} />
    </div>
  );
}
function NodeResult({ data }) {
  return (
    <div className="detail-grid">
      <Row label="Node ID"     val={<span className="hash">{data.node_id}</span>} />
      <Row label="Type"        val={<span className={`badge badge-${data.node_type}`}>{data.node_type}</span>} />
      <Row label="Address"     val={<span className="hash">{data.address}</span>} />
      <Row label="Model"       val={data.model_name || '—'} />
      <Row label="Endpoint"    val={data.endpoint} />
      <Row label="PoM Verified"val={data.pom_verified ? '✓ Yes' : '—'} />
      <Row label="Active"      val={data.is_active ? '✓ Yes' : '—'} />
    </div>
  );
}

// ── Block type distribution chart ─────────────────────────────────────────────
function BlockTypeChart({ blocks }) {
  if (!blocks || blocks.length === 0) return null;
  const qoi = blocks.filter(b => b.block_type === 'qoi').length;
  const pos = blocks.filter(b => b.block_type === 'pos').length;
  const total = qoi + pos;
  const qPct = total ? Math.round(qoi/total*100) : 0;
  const pPct = 100 - qPct;

  return (
    <div className="type-chart card">
      <p className="section-title">Block Distribution (last {blocks.length})</p>
      <div className="chart-bar-wrap">
        <div className="chart-bar">
          {qPct > 0 && <div className="chart-seg chart-qoi" style={{width:`${qPct}%`}} title={`QoI: ${qoi}`} />}
          {pPct > 0 && <div className="chart-seg chart-pos" style={{width:`${pPct}%`}} title={`PoS: ${pos}`} />}
        </div>
      </div>
      <div className="chart-legend">
        <span><span className="leg-dot dot-qoi" />QoI {qoi} ({qPct}%)</span>
        <span><span className="leg-dot dot-pos" />PoS {pos} ({pPct}%)</span>
      </div>
    </div>
  );
}

// ── Main ExplorerPage ─────────────────────────────────────────────────────────
export default function ExplorerPage() {
  const [stats,       setStats]       = useState(null);
  const [blocks,      setBlocks]      = useState([]);
  const [selectedBlk, setSelectedBlk] = useState(null);
  const [selectedTx,  setSelectedTx]  = useState(null);
  const [search,      setSearch]      = useState('');
  const [query,       setQuery]       = useState('');
  const [loadingBlk,  setLoadingBlk]  = useState(true);
  const [before,      setBefore]      = useState(null);   // pagination

  const loadStats = useCallback(() =>
    chainApi.stats().then(setStats).catch(() => {}), []);

  const loadBlocks = useCallback((beforeH = null) => {
    setLoadingBlk(true);
    chainApi.blocks(20, beforeH)
      .then(data => { setBlocks(Array.isArray(data) ? data : []); setLoadingBlk(false); })
      .catch(() => setLoadingBlk(false));
  }, []);

  useEffect(() => {
    loadStats();
    loadBlocks();
    const id = setInterval(() => { loadStats(); loadBlocks(); }, 6000);
    return () => clearInterval(id);
  }, [loadStats, loadBlocks]);

  const handleSearch = (e) => {
    e.preventDefault();
    if (search.trim()) setQuery(search.trim());
  };

  const olderHeight = blocks.length > 0 ? blocks[blocks.length - 1].height : null;
  const newerHeight = blocks.length > 0 ? blocks[0].height + 20 : null;

  return (
    <div className="page-wrap">
      {/* Search bar */}
      <form className="search-bar" onSubmit={handleSearch}>
        <input
          className="search-input"
          placeholder="Search by block height, block hash, tx ID, or address…"
          value={search}
          onChange={e => setSearch(e.target.value)}
        />
        <button type="submit" className="btn btn-primary">Search</button>
        {query && (
          <button type="button" className="btn btn-ghost" onClick={() => { setQuery(''); setSearch(''); }}>
            Clear
          </button>
        )}
      </form>

      {/* Lookup result */}
      {query && (
        <LookupResult
          key={query}
          query={query}
          onClose={() => { setQuery(''); setSearch(''); }}
        />
      )}

      {/* Stats row */}
      <StatsRow stats={stats} />

      {/* Two-column layout */}
      <div className="exp-grid">

        {/* Left: block list */}
        <div>
          <div className="exp-col-header">
            <p className="section-title">Latest Blocks</p>
            <div className="exp-pager">
              <button
                className="btn btn-ghost btn-sm"
                disabled={!newerHeight || newerHeight > (stats?.chain_height || 0)}
                onClick={() => { setBefore(newerHeight); loadBlocks(newerHeight); }}
              >
                ← Newer
              </button>
              <button
                className="btn btn-ghost btn-sm"
                disabled={!olderHeight || olderHeight === 0}
                onClick={() => { setBefore(olderHeight); loadBlocks(olderHeight); }}
              >
                Older →
              </button>
            </div>
          </div>

          {loadingBlk
            ? <div className="loading-center"><div className="spinner" /></div>
            : (
              <div className="blk-table-wrap card">
                <table className="blk-table">
                  <thead>
                    <tr><th>Height</th><th>Type</th><th>Hash</th><th>Proposer</th><th>TXs</th><th>Age</th></tr>
                  </thead>
                  <tbody>
                    {blocks.map(b => (
                      <BlockRow
                        key={b.height}
                        blk={b}
                        selected={selectedBlk === b.height}
                        onClick={() => setSelectedBlk(selectedBlk === b.height ? null : b.height)}
                      />
                    ))}
                  </tbody>
                </table>
                {blocks.length === 0 && <div className="empty-state">No blocks yet</div>}
              </div>
            )
          }

          {/* Block detail (inline expand) */}
          {selectedBlk !== null && (
            <BlockDetail
              key={selectedBlk}
              height={selectedBlk}
              onClose={() => setSelectedBlk(null)}
            />
          )}
        </div>

        {/* Right column */}
        <div className="exp-right">
          {/* Block type chart */}
          <BlockTypeChart blocks={blocks} />

          {/* Mempool */}
          <TxPanel selectedTx={selectedTx} onSelectTx={setSelectedTx} />

          {/* TX detail */}
          {selectedTx && (
            <div className="card" style={{marginTop:16}}>
              <div className="detail-header">
                <h3>Transaction</h3>
                <button className="btn btn-ghost btn-sm" onClick={() => setSelectedTx(null)}>✕</button>
              </div>
              <TxResult data={selectedTx} />
            </div>
          )}
        </div>

      </div>
    </div>
  );
}
