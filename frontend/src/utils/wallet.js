/**
 * InferenceChain Wallet Utility
 *
 * Key scheme: secp256k1 — same as backend core/node/identity.py
 *   mnemonic     — 12 BIP39 words (128-bit entropy)
 *   private key  — first 32 bytes of BIP39 seed (sha256 fallback if out of range)
 *   public key   — 64-byte uncompressed point hex (no 04 prefix)
 *   address      — SHA-256(pubkey_bytes)[:20] as 40-char hex
 *
 * Encryption: AES-256-GCM with PBKDF2-derived key (100k iterations, SHA-256)
 * Private key is NEVER stored in plaintext — only in React state while unlocked.
 */

import * as secp from '@noble/secp256k1';
import { sha256 } from '@noble/hashes/sha2.js';
import { hmac } from '@noble/hashes/hmac.js';
import { bytesToHex, hexToBytes, utf8ToBytes } from '@noble/hashes/utils.js';
import * as bip39 from '@scure/bip39';
import { wordlist } from '@scure/bip39/wordlists/english.js';

// Wire up synchronous hashing for v3 API
secp.hashes.sha256     = (msg) => sha256(msg);
secp.hashes.hmacSha256 = (key, ...msgs) => hmac(sha256, key, secp.etc.concatBytes(...msgs));

const STORAGE_KEY = 'ic_wallet_v2';
const PBKDF2_ITERS = 100_000;

// ── Address derivation ────────────────────────────────────────────────────────

function pubkeyToAddress(pub64) {
  return bytesToHex(sha256(pub64).slice(0, 20));
}

function privKeyToWalletPublics(privKeyBytes) {
  const pubFull = secp.getPublicKey(privKeyBytes, false); // 65 bytes uncompressed
  const pub64   = pubFull.slice(1);                       // strip 04 prefix
  return {
    publicKey: bytesToHex(pub64),
    address:   pubkeyToAddress(pub64),
  };
}

// ── Mnemonic → private key ────────────────────────────────────────────────────
// BIP39 seed (64 bytes) → first 32 bytes = private key candidate
// If out of secp256k1 range (astronomically rare), hash the full seed

function privFromMnemonic(mnemonic) {
  const seed    = bip39.mnemonicToSeedSync(mnemonic);      // 64 bytes
  let   privKey = seed.slice(0, 32);
  // Validate: all-zero key is invalid (astronomically rare but guard it)
  const allZero = privKey.every(b => b === 0);
  if (allZero) {
    privKey = sha256(seed);  // fallback: sha256 of full seed
  }
  return privKey;
}

// ── Web Crypto helpers (AES-256-GCM + PBKDF2) ────────────────────────────────

function b64(buf) {
  return btoa(String.fromCharCode(...new Uint8Array(buf)));
}
function unb64(str) {
  return Uint8Array.from(atob(str), c => c.charCodeAt(0));
}

async function deriveKey(password, salt) {
  const enc     = new TextEncoder();
  const keyMat  = await crypto.subtle.importKey(
    'raw', enc.encode(password), 'PBKDF2', false, ['deriveKey'],
  );
  return crypto.subtle.deriveKey(
    { name: 'PBKDF2', salt, iterations: PBKDF2_ITERS, hash: 'SHA-256' },
    keyMat,
    { name: 'AES-GCM', length: 256 },
    false,
    ['encrypt', 'decrypt'],
  );
}

async function encryptPrivKey(privKeyHex, password) {
  const salt = crypto.getRandomValues(new Uint8Array(16));
  const iv   = crypto.getRandomValues(new Uint8Array(12));
  const key  = await deriveKey(password, salt);
  const enc  = new TextEncoder();
  const ct   = await crypto.subtle.encrypt({ name: 'AES-GCM', iv }, key, enc.encode(privKeyHex));
  return { ciphertext: b64(ct), salt: b64(salt), iv: b64(iv) };
}

async function decryptPrivKey(stored, password) {
  const salt = unb64(stored.salt);
  const iv   = unb64(stored.iv);
  const ct   = unb64(stored.ciphertext);
  const key  = await deriveKey(password, salt);
  const dec  = await crypto.subtle.decrypt({ name: 'AES-GCM', iv }, key, ct);
  return new TextDecoder().decode(dec);
}

// ── Public API ────────────────────────────────────────────────────────────────

export function generateMnemonic() {
  return bip39.generateMnemonic(wordlist, 128); // 12 words
}

export function validateMnemonic(phrase) {
  return bip39.validateMnemonic(phrase.trim().toLowerCase(), wordlist);
}

/** Build wallet record (without private key) from mnemonic, encrypted with password. */
export async function createWalletFromMnemonic(mnemonic, password) {
  const privKeyBytes = privFromMnemonic(mnemonic);
  const privKeyHex   = bytesToHex(privKeyBytes);
  const { publicKey, address } = privKeyToWalletPublics(privKeyBytes);
  const encrypted = await encryptPrivKey(privKeyHex, password);
  return { address, publicKey, encrypted };
}

/** Import from raw hex private key, encrypted with password. */
export async function createWalletFromPrivKey(privKeyHex, password) {
  const clean = privKeyHex.trim().replace(/^0x/i, '');
  if (clean.length !== 64) throw new Error('Private key must be 64 hex characters');
  const privKeyBytes = hexToBytes(clean);
  const { publicKey, address } = privKeyToWalletPublics(privKeyBytes);
  const encrypted = await encryptPrivKey(clean, password);
  return { address, publicKey, encrypted };
}

/** Recover wallet from mnemonic + set new password. */
export async function recoverWalletFromMnemonic(mnemonic, password) {
  if (!validateMnemonic(mnemonic)) throw new Error('Invalid mnemonic phrase');
  return createWalletFromMnemonic(mnemonic, password);
}

/** Unlock: decrypt and return the private key hex. Throws if password is wrong. */
export async function unlockWallet(password) {
  const stored = loadStoredWallet();
  if (!stored) throw new Error('No wallet found');
  try {
    const privKeyHex = await decryptPrivKey(stored.encrypted, password);
    return privKeyHex;
  } catch {
    throw new Error('Incorrect password');
  }
}

// ── Persistence ───────────────────────────────────────────────────────────────
// Only stores: address, publicKey, encrypted blob — never raw private key.

export function saveStoredWallet(walletRecord) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(walletRecord));
  // Clear old v1 format if present
  localStorage.removeItem('ic_wallet_v1');
}

export function loadStoredWallet() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

export function clearStoredWallet() {
  localStorage.removeItem(STORAGE_KEY);
  localStorage.removeItem('ic_wallet_v1');
}

// ── Password strength ─────────────────────────────────────────────────────────

export function passwordStrength(pw) {
  if (!pw) return { score: 0, label: '', color: '' };
  let score = 0;
  if (pw.length >= 8)  score++;
  if (pw.length >= 12) score++;
  if (/[A-Z]/.test(pw)) score++;
  if (/[0-9]/.test(pw)) score++;
  if (/[^A-Za-z0-9]/.test(pw)) score++;
  const labels = ['', 'Weak', 'Fair', 'Good', 'Strong', 'Very Strong'];
  const colors = ['', '#ef4444', '#f59e0b', '#3b82f6', '#10b981', '#10b981'];
  return { score, label: labels[score] || 'Weak', color: colors[score] || '#ef4444' };
}

export function isPasswordAcceptable(pw) {
  return pw && pw.length >= 8 && passwordStrength(pw).score >= 2;
}

// ── Signing ───────────────────────────────────────────────────────────────────

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
  return bytesToHex(sha256(utf8ToBytes(canonicalJson(txData))));
}

function signTxId(txId, privateKeyHex) {
  // Python verify_signature does sha256(tx_id.encode()) before verifying,
  // so we must pre-hash too (noble-secp256k1 expects a 32-byte message hash).
  const msgHash = sha256(utf8ToBytes(txId));
  const sig = secp.sign(msgHash, hexToBytes(privateKeyHex));
  return bytesToHex(sig.toCompactRawBytes());
}

// ── Transaction builders ──────────────────────────────────────────────────────

export function buildTransferTx(address, publicKey, privateKeyHex, recipient, amount, fee, nonce) {
  const timestamp = Date.now() / 1000;
  const payload   = { amount };
  const txData    = { fee, nonce, payload, recipient, sender: address, timestamp, tx_type: 'token_transfer' };
  const txId      = computeTxId(txData);
  const signature = signTxId(txId, privateKeyHex);
  return { tx_type: 'token_transfer', sender: address, recipient, payload, nonce, fee, timestamp, signature, tx_id: txId, public_key: publicKey };
}

export function buildStakeTx(address, publicKey, privateKeyHex, amount, fee, nonce) {
  const timestamp = Date.now() / 1000;
  const payload   = { amount };
  const txData    = { fee, nonce, payload, recipient: null, sender: address, timestamp, tx_type: 'stake' };
  const txId      = computeTxId(txData);
  const signature = signTxId(txId, privateKeyHex);
  return { tx_type: 'stake', sender: address, recipient: null, payload, nonce, fee, timestamp, signature, tx_id: txId, public_key: publicKey };
}

export function buildUnstakeTx(address, publicKey, privateKeyHex, amount, fee, nonce) {
  const timestamp = Date.now() / 1000;
  const payload   = { amount };
  const txData    = { fee, nonce, payload, recipient: null, sender: address, timestamp, tx_type: 'unstake' };
  const txId      = computeTxId(txData);
  const signature = signTxId(txId, privateKeyHex);
  return { tx_type: 'unstake', sender: address, recipient: null, payload, nonce, fee, timestamp, signature, tx_id: txId, public_key: publicKey };
}

// Staking thresholds (mirrors core/blockchain/constants.py)
export const MIN_STAKE_DNN = 1000;
export const MIN_STAKE_POS = 500;

// ── Formatting helpers ────────────────────────────────────────────────────────

export function shortAddr(addr) {
  if (!addr) return '';
  return `${addr.slice(0, 6)}…${addr.slice(-4)}`;
}

export function formatInfer(amount) {
  return Number(amount).toLocaleString(undefined, { maximumFractionDigits: 2 });
}
