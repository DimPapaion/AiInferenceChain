import * as secp from '@noble/secp256k1';
import { sha256 } from '@noble/hashes/sha2.js';
import { hmac } from '@noble/hashes/hmac.js';
import { bytesToHex, hexToBytes } from '@noble/hashes/utils.js';
import * as bip39 from '@scure/bip39';
import { wordlist } from '@scure/bip39/wordlists/english.js';

secp.hashes.sha256 = (msg) => sha256(msg);
secp.hashes.hmacSha256 = (key, ...msgs) => hmac(sha256, key, secp.etc.concatBytes(...msgs));

const STORAGE_KEY = 'ic_wallet_desktop_v1';
const PBKDF2_ITERS = 100_000;
const UNLOCKED_KEY = 'ic_unlocked_priv';

function pubkeyToAddress(pub64) {
  return bytesToHex(sha256(pub64).slice(0, 20));
}

function privToPublics(privBytes) {
  const pubFull = secp.getPublicKey(privBytes, false);
  const pub64 = pubFull.slice(1);
  return {
    publicKey: bytesToHex(pub64),
    address: pubkeyToAddress(pub64),
  };
}

function privFromMnemonic(mnemonic) {
  const seed = bip39.mnemonicToSeedSync(mnemonic);
  let priv = seed.slice(0, 32);
  if (priv.every((b) => b === 0)) priv = sha256(seed);
  return priv;
}

function b64(buf) {
  return btoa(String.fromCharCode(...new Uint8Array(buf)));
}

function unb64(str) {
  return Uint8Array.from(atob(str), (c) => c.charCodeAt(0));
}

async function deriveKey(password, salt) {
  const enc = new TextEncoder();
  const keyMat = await crypto.subtle.importKey('raw', enc.encode(password), 'PBKDF2', false, ['deriveKey']);
  return crypto.subtle.deriveKey(
    { name: 'PBKDF2', salt, iterations: PBKDF2_ITERS, hash: 'SHA-256' },
    keyMat,
    { name: 'AES-GCM', length: 256 },
    false,
    ['encrypt', 'decrypt']
  );
}

async function encryptPrivKey(privHex, password) {
  const salt = crypto.getRandomValues(new Uint8Array(16));
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const key = await deriveKey(password, salt);
  const ct = await crypto.subtle.encrypt({ name: 'AES-GCM', iv }, key, new TextEncoder().encode(privHex));
  return { ciphertext: b64(ct), salt: b64(salt), iv: b64(iv) };
}

async function decryptPrivKey(encBlob, password) {
  const salt = unb64(encBlob.salt);
  const iv = unb64(encBlob.iv);
  const ct = unb64(encBlob.ciphertext);
  const key = await deriveKey(password, salt);
  const dec = await crypto.subtle.decrypt({ name: 'AES-GCM', iv }, key, ct);
  return new TextDecoder().decode(dec);
}

export function generateMnemonic() {
  return bip39.generateMnemonic(wordlist, 128);
}

export function validateMnemonic(phrase) {
  return bip39.validateMnemonic((phrase || '').trim().toLowerCase(), wordlist);
}

export async function createWalletFromMnemonic(mnemonic, password) {
  const privBytes = privFromMnemonic(mnemonic);
  const privHex = bytesToHex(privBytes);
  const { publicKey, address } = privToPublics(privBytes);
  const encrypted = await encryptPrivKey(privHex, password);
  return { address, publicKey, encrypted };
}

export async function createWalletFromPrivKey(privHex, password) {
  const clean = (privHex || '').trim().replace(/^0x/i, '');
  if (clean.length !== 64) throw new Error('Private key must be 64 hex characters');
  const privBytes = hexToBytes(clean);
  const { publicKey, address } = privToPublics(privBytes);
  const encrypted = await encryptPrivKey(clean, password);
  return { address, publicKey, encrypted };
}

export function saveStoredWallet(record) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(record));
  localStorage.setItem('ic_pubkey', record.address);
}

export function loadStoredWallet() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

export async function unlockWallet(password) {
  const stored = loadStoredWallet();
  if (!stored) throw new Error('No wallet found');
  try {
    return await decryptPrivKey(stored.encrypted, password);
  } catch {
    throw new Error('Incorrect password');
  }
}

export function setUnlockedPriv(privHex) {
  sessionStorage.setItem(UNLOCKED_KEY, privHex);
}

export function getUnlockedPriv() {
  return sessionStorage.getItem(UNLOCKED_KEY) || '';
}

export function clearUnlockedPriv() {
  sessionStorage.removeItem(UNLOCKED_KEY);
}

export function isPasswordAcceptable(pw) {
  return !!pw && pw.length >= 8;
}

export function shortAddress(addr) {
  if (!addr) return '';
  return `${addr.slice(0, 8)}...${addr.slice(-6)}`;
}
