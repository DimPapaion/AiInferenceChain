/**
 * InferenceChain Wallet Utility
 *
 * Key scheme: secp256k1 (same as backend core/node/identity.py)
 *   private key  — 32-byte random hex
 *   public key   — 64-byte uncompressed point (x||y, no 04 prefix) hex
 *   address      — SHA-256(pubkey_bytes)[:20] as 40-char hex
 *
 * Signing: SHA-256(tx_id_utf8) → secp256k1 sign → compact r||s hex (128 chars)
 * Matches NodeIdentity.sign_tx() in Python.
 */

import * as secp from '@noble/secp256k1';
import { sha256 } from '@noble/hashes/sha2.js';
import { hmac } from '@noble/hashes/hmac.js';
import { bytesToHex, hexToBytes, utf8ToBytes } from '@noble/hashes/utils.js';

// ── Wire up synchronous hashing for RFC 6979 deterministic signing (v3 API) ──
secp.hashes.sha256     = (msg) => sha256(msg);
secp.hashes.hmacSha256 = (key, ...msgs) => hmac(sha256, key, secp.etc.concatBytes(...msgs));

const STORAGE_KEY = 'ic_wallet_v1';

// ── Address derivation ────────────────────────────────────────────────────────
// Matches Python: sha256(raw_64_byte_pubkey)[:20] as hex

function pubkeyToAddress(pub64) {
  const hash = sha256(pub64);
  return bytesToHex(hash.slice(0, 20));
}

// ── Keypair helpers ───────────────────────────────────────────────────────────

function buildWallet(privKeyBytes) {
  const pubFull = secp.getPublicKey(privKeyBytes, false); // Uint8Array(65) uncompressed
  const pub64   = pubFull.slice(1);                       // strip 04 prefix → 64 bytes
  return {
    privateKey: bytesToHex(privKeyBytes),
    publicKey:  bytesToHex(pub64),
    address:    pubkeyToAddress(pub64),
  };
}

// ── Public API ────────────────────────────────────────────────────────────────

export function generateWallet() {
  return buildWallet(secp.utils.randomSecretKey());
}

export function walletFromPrivateKey(privHex) {
  const clean = privHex.trim().replace(/^0x/i, '');
  if (clean.length !== 64) throw new Error('Private key must be 64 hex characters (32 bytes)');
  return buildWallet(hexToBytes(clean));
}

// ── Persistence ───────────────────────────────────────────────────────────────

export function saveWallet(wallet) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify({
    privateKey: wallet.privateKey,
    publicKey:  wallet.publicKey,
    address:    wallet.address,
  }));
}

export function loadWallet() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

export function clearWallet() {
  localStorage.removeItem(STORAGE_KEY);
}

// ── Canonical JSON (matches Python sha256_json) ───────────────────────────────

function canonicalJson(obj) {
  if (obj === null || obj === undefined) return 'null';
  if (typeof obj === 'boolean') return obj ? 'true' : 'false';
  if (typeof obj === 'number') return JSON.stringify(obj);
  if (typeof obj === 'string') return JSON.stringify(obj);
  if (Array.isArray(obj)) return '[' + obj.map(canonicalJson).join(',') + ']';
  const keys = Object.keys(obj).sort();
  return '{' + keys.map(k => JSON.stringify(k) + ':' + canonicalJson(obj[k])).join(',') + '}';
}

function computeTxId(txData) {
  const str   = canonicalJson(txData);
  const bytes = utf8ToBytes(str);
  return bytesToHex(sha256(bytes));
}

// ── Signing ───────────────────────────────────────────────────────────────────
// sign(tx_id) → v3 sign() prehashes with sha256 by default, returns compact Uint8Array

function signTxId(txId, privateKeyHex) {
  const msgBytes = utf8ToBytes(txId);
  const privKey  = hexToBytes(privateKeyHex);
  // sign() with default opts: prehash=true (applies sha256 internally)
  const sig      = secp.sign(msgBytes, privKey);
  return bytesToHex(sig.toCompactRawBytes());
}

// ── Transaction builders ──────────────────────────────────────────────────────

export function buildTransferTx(wallet, recipient, amount, fee, nonce) {
  const timestamp = Date.now() / 1000;
  const payload   = { amount };
  const txData    = {
    fee,
    nonce,
    payload,
    recipient,
    sender:    wallet.address,
    timestamp,
    tx_type:   'token_transfer',
  };
  const txId      = computeTxId(txData);
  const signature = signTxId(txId, wallet.privateKey);
  return {
    tx_type:   'token_transfer',
    sender:    wallet.address,
    recipient,
    payload,
    nonce,
    fee,
    timestamp,
    signature,
    tx_id: txId,
  };
}

// ── Formatting helpers ────────────────────────────────────────────────────────

export function shortAddr(addr) {
  if (!addr) return '';
  return `${addr.slice(0, 6)}…${addr.slice(-4)}`;
}

export function formatInfer(amount) {
  return Number(amount).toLocaleString(undefined, { maximumFractionDigits: 2 });
}
