/**
 * InferenceChain Wallet Utility
 *
 * Key scheme: secp256k1 (same as backend core/node/identity.py)
 *   private key  — 32-byte random hex
 *   public key   — 64-byte uncompressed point (x||y, no 04 prefix) hex
 *   address      — SHA-256(pubkey_bytes)[:20] as 40-char hex
 *
 * Signing: SHA-256(tx_id_utf8) → secp256k1 sign → compact r||s hex (128 chars)
 * This matches NodeIdentity.sign_tx() in Python.
 */

import * as secp from '@noble/secp256k1';
import { sha256 } from '@noble/hashes/sha2.js';
import { hmac } from '@noble/hashes/hmac.js';
import { bytesToHex, hexToBytes, utf8ToBytes } from '@noble/hashes/utils.js';

// Required: provide synchronous HMAC-SHA256 for RFC 6979 deterministic signing
secp.etc.hmacSha256Sync = (k, ...msgs) =>
  hmac(sha256, k, secp.etc.concatBytes(...msgs));

const STORAGE_KEY = 'ic_wallet_v1';

// ── Address derivation ────────────────────────────────────────────────────────
// Matches Python pubkey_to_address: sha256(raw_64_byte_pubkey)[:20] as hex

function pubkeyToAddress(pubKey64) {
  const hash = sha256(pubKey64);
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
  return buildWallet(secp.utils.randomPrivateKey());
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
// json.dumps(data, sort_keys=True, separators=(',', ':'), ensure_ascii=True)
// Note: Python serialises float 0.0 as "0.0" but JS serialises 0 as "0".
// Since the backend preserves the client-sent tx_id and doesn't verify
// regular-wallet signatures yet, this mismatch is acceptable for this MVP.

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

// ── Signing (matches NodeIdentity.sign_tx) ────────────────────────────────────
// sign(tx_id) → sha256(tx_id_utf8_bytes) → secp256k1 sign_digest → r||s hex

function signTxId(txId, privateKeyHex) {
  const msgBytes = utf8ToBytes(txId);
  const digest   = sha256(msgBytes);
  const privKey  = hexToBytes(privateKeyHex);
  const sig      = secp.sign(digest, privKey);
  return sig.toCompactHex(); // 64-byte r||s hex (128 chars)
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
