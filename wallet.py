"""
wallet.py — InferenceChain CLI wallet.

Manages a local keypair file and talks to any running node via REST.

Commands:
  new        [--out wallet.json]             Generate a new keypair
  import     <private_key_hex>               Import an existing private key
  info       [--node URL]                    Show address, balance, stake, nonce
  send       <to_address> <amount>           Send INFER tokens
  stake      <amount>                        Stake tokens (become eligible for consensus)
  unstake    <amount>                        Unstake tokens
  register   --endpoint URL                  Register as a PoS validator node
  tx         <tx_id>                         Query a transaction by ID
  seal       [--proposer node-8000]          Dev-only: manually seal a block

Usage examples:
  python wallet.py new
  python wallet.py new --out alice.json

  python wallet.py info
  python wallet.py info --node http://192.168.1.10:8000

  python wallet.py send abcdef...1234 500
  python wallet.py send abcdef...1234 500 --fee 2

  python wallet.py stake 10000
  python wallet.py unstake 5000

  python wallet.py register --endpoint http://mynode.example.com:8000

  python wallet.py tx a1b2c3...
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────────────────

DEFAULT_WALLET = Path("wallet.json")
DEFAULT_NODE   = "http://localhost:8000"


# ── HTTP helpers ──────────────────────────────────────────────────────────────

def _get(base: str, path: str) -> dict:
    url = base.rstrip("/") + path
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        _die(f"HTTP {e.code} from {url}: {body[:200]}")
    except urllib.error.URLError as e:
        _die(f"Cannot reach node at {base}: {e.reason}")


def _post(base: str, path: str, payload: dict) -> dict:
    url  = base.rstrip("/") + path
    data = json.dumps(payload).encode()
    req  = urllib.request.Request(
        url, data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        _die(f"HTTP {e.code} from {url}: {body[:300]}")
    except urllib.error.URLError as e:
        _die(f"Cannot reach node at {base}: {e.reason}")


# ── Wallet file helpers ───────────────────────────────────────────────────────

def _load_wallet(path: Path):
    if not path.exists():
        _die(
            f"Wallet file '{path}' not found.\n"
            f"  Create one with:  python wallet.py new\n"
            f"  Or specify path:  --wallet <file.json>"
        )
    from core.node.identity import NodeIdentity
    return NodeIdentity.load(str(path))


def _save_wallet(identity, path: Path) -> None:
    if path.exists():
        _die(
            f"Wallet file '{path}' already exists — refusing to overwrite.\n"
            f"  Use --out <other_file.json> to save to a different path."
        )
    identity.save(str(path))
    print(f"Wallet saved to '{path}'")


# ── Transaction builder ───────────────────────────────────────────────────────

def _build_and_sign(identity, tx_type: str, payload: dict,
                    recipient: str | None, nonce: int, fee: float,
                    node_url: str) -> dict:
    """
    Build, compute tx_id, sign, and return a wire-format transaction dict.
    Uses the same logic as Transaction._compute_id() without importing the
    full transaction module (keeps the wallet dependency-light).
    """
    import hashlib, json as _json
    from core.blockchain.utils import now
    from core.blockchain.transaction import Transaction, TxType
    from core.blockchain.transaction import (
        TokenTransferPayload, StakePayload, UnstakePayload,
        NodeRegisterPOSPayload,
    )

    type_map = {
        "token_transfer":   (TxType.TOKEN_TRANSFER,   lambda p: TokenTransferPayload(p["amount"])),
        "stake":            (TxType.STAKE,             lambda p: StakePayload(p["amount"])),
        "unstake":          (TxType.UNSTAKE,           lambda p: UnstakePayload(p["amount"])),
        "node_register_pos":(TxType.NODE_REGISTER_POS, lambda p: NodeRegisterPOSPayload(**p)),
    }
    ttype, make_payload = type_map[tx_type]
    tx = Transaction(
        tx_type   = ttype,
        sender    = identity.address,
        payload   = make_payload(payload),
        nonce     = nonce,
        fee       = fee,
        recipient = recipient,
    )
    tx.signature = identity.sign_tx(tx.tx_id)
    return tx.to_dict()


# ── Commands ──────────────────────────────────────────────────────────────────

def cmd_new(args) -> None:
    from core.node.identity import NodeIdentity
    identity = NodeIdentity.generate()
    out = Path(args.out)
    _save_wallet(identity, out)
    print()
    print(f"  Address    : {identity.address}")
    print(f"  Public key : {identity.public_key_hex[:24]}…")
    print()
    print("  Keep your wallet file safe — it contains your private key.")
    print(f"  Share your address ({identity.address}) with others to receive INFER.")


def cmd_import(args) -> None:
    from core.node.identity import NodeIdentity
    priv = args.private_key.strip()
    if len(priv) != 64:
        _die("Private key must be exactly 64 hex characters (32 bytes).")
    identity = NodeIdentity.from_private_key(priv)
    out = Path(args.out)
    _save_wallet(identity, out)
    print(f"\n  Imported address: {identity.address}")


def cmd_info(args) -> None:
    identity = _load_wallet(Path(args.wallet))
    addr     = identity.address
    node     = args.node

    print(f"\n  Address    : {addr}")
    print(f"  Public key : {identity.public_key_hex[:24]}…")
    print(f"  Node       : {node}")
    print()

    try:
        bal   = _get(node, f"/state/balance/{addr}")
        stake = _get(node, f"/state/stake/{addr}")
        nonce = _get(node, f"/state/nonce/{addr}")
        rep   = _get(node, f"/state/reputation/{addr}")
        print(f"  Balance    : {bal.get('balance', bal):>16.4f}  INFER")
        print(f"  Staked     : {stake.get('stake', stake):>16.4f}  INFER")
        print(f"  Reputation : {rep.get('reputation', rep):>16.6f}")
        print(f"  Nonce      : {nonce.get('nonce', nonce)}")
    except SystemExit:
        pass
    print()


def cmd_send(args) -> None:
    identity = _load_wallet(Path(args.wallet))
    node     = args.node

    nonce = _get(node, f"/state/nonce/{identity.address}")
    nonce = (nonce.get("nonce", nonce) or 0) + 1

    to     = args.to_address
    amount = float(args.amount)
    fee    = float(args.fee)

    print(f"\n  Sending {amount} INFER → {to[:12]}…")
    print(f"  Fee: {fee} INFER   Nonce: {nonce}")

    tx = _build_and_sign(
        identity  = identity,
        tx_type   = "token_transfer",
        payload   = {"amount": amount},
        recipient = to,
        nonce     = nonce,
        fee       = fee,
        node_url  = node,
    )

    result = _post(node, "/tx/submit", tx)
    if result.get("accepted"):
        print(f"\n  ✓ Accepted   tx_id: {result['tx_id'][:16]}…")
    else:
        print(f"\n  ✗ Rejected   reason: {result.get('reason')}")
    print()


def cmd_stake(args) -> None:
    identity = _load_wallet(Path(args.wallet))
    node     = args.node

    nonce = _get(node, f"/state/nonce/{identity.address}")
    nonce = (nonce.get("nonce", nonce) or 0) + 1

    amount = float(args.amount)
    fee    = float(args.fee)

    print(f"\n  Staking {amount} INFER  (nonce={nonce})")

    tx = _build_and_sign(
        identity  = identity,
        tx_type   = "stake",
        payload   = {"amount": amount},
        recipient = None,
        nonce     = nonce,
        fee       = fee,
        node_url  = node,
    )

    result = _post(node, "/tx/submit", tx)
    if result.get("accepted"):
        print(f"\n  ✓ Stake submitted   tx_id: {result['tx_id'][:16]}…")
    else:
        print(f"\n  ✗ Rejected   reason: {result.get('reason')}")
    print()


def cmd_unstake(args) -> None:
    identity = _load_wallet(Path(args.wallet))
    node     = args.node

    nonce = _get(node, f"/state/nonce/{identity.address}")
    nonce = (nonce.get("nonce", nonce) or 0) + 1

    amount = float(args.amount)
    fee    = float(args.fee)

    print(f"\n  Unstaking {amount} INFER  (nonce={nonce})")

    tx = _build_and_sign(
        identity  = identity,
        tx_type   = "unstake",
        payload   = {"amount": amount},
        recipient = None,
        nonce     = nonce,
        fee       = fee,
        node_url  = node,
    )

    result = _post(node, "/tx/submit", tx)
    if result.get("accepted"):
        print(f"\n  ✓ Unstake submitted   tx_id: {result['tx_id'][:16]}…")
    else:
        print(f"\n  ✗ Rejected   reason: {result.get('reason')}")
    print()


def cmd_register(args) -> None:
    identity = _load_wallet(Path(args.wallet))
    node     = args.node

    nonce = _get(node, f"/state/nonce/{identity.address}")
    nonce = (nonce.get("nonce", nonce) or 0) + 1

    endpoint = args.endpoint.rstrip("/")
    fee      = float(args.fee)

    print(f"\n  Registering PoS node")
    print(f"  Endpoint   : {endpoint}")
    print(f"  Address    : {identity.address}")
    print(f"  Public key : {identity.public_key_hex[:24]}…")

    tx = _build_and_sign(
        identity  = identity,
        tx_type   = "node_register_pos",
        payload   = {
            "endpoint":   endpoint,
            "public_key": identity.public_key_hex,
        },
        recipient = None,
        nonce     = nonce,
        fee       = fee,
        node_url  = node,
    )

    result = _post(node, "/tx/submit", tx)
    if result.get("accepted"):
        print(f"\n  ✓ Registration submitted   tx_id: {result['tx_id'][:16]}…")
        print(f"  Stake some INFER to become an active validator:")
        print(f"    python wallet.py stake 10000 --wallet {args.wallet}")
    else:
        print(f"\n  ✗ Rejected   reason: {result.get('reason')}")
    print()


def cmd_tx(args) -> None:
    node   = args.node
    tx_id  = args.tx_id

    result = _get(node, f"/tx/{tx_id}")
    status = result.get("status", "unknown")

    print(f"\n  tx_id   : {tx_id}")
    print(f"  status  : {status}")
    if status == "confirmed":
        print(f"  type    : {result.get('tx_type', '?')}")
        print(f"  block   : #{result.get('block_height', '?')}  ({result.get('block_hash', '')[:12]}…)")
        if result.get("payload"):
            print(f"  payload : {result['payload']}")
    elif status == "pending":
        print("  (waiting to be included in the next block)")
    elif status == "not_found":
        print("  Not found in mempool or chain.")
    print()


def cmd_seal(args) -> None:
    """Dev-only: manually trigger block sealing on the node."""
    node     = args.node
    proposer = args.proposer or f"node-{args.node.split(':')[-1]}"

    print(f"\n  Sealing block (proposer={proposer})…")
    result = _post(node, "/dev/seal", {"proposer_id": proposer})

    if result.get("hash"):
        print(f"\n  ✓ Block #{result.get('height')} sealed")
        print(f"  Hash  : {result.get('hash', '')}")
        print(f"  Txs   : {result.get('tx_count', 0)}")
    else:
        print(f"\n  Result: {result}")
    print()


# ── Utility ───────────────────────────────────────────────────────────────────

def _die(msg: str) -> None:
    print(f"\n  Error: {msg}\n", file=sys.stderr)
    sys.exit(1)


# ── CLI ───────────────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog        = "wallet",
        description = "InferenceChain CLI wallet",
        formatter_class = argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--wallet", default=str(DEFAULT_WALLET),
                   help=f"Wallet file path (default: {DEFAULT_WALLET})")
    p.add_argument("--node",   default=DEFAULT_NODE,
                   help=f"Node REST URL (default: {DEFAULT_NODE})")

    sub = p.add_subparsers(dest="command", metavar="<command>")
    sub.required = True

    # new
    s = sub.add_parser("new", help="Generate a new keypair")
    s.add_argument("--out", default=str(DEFAULT_WALLET),
                   help="Output file path (default: wallet.json)")

    # import
    s = sub.add_parser("import", help="Import an existing private key")
    s.add_argument("private_key", metavar="PRIVATE_KEY_HEX",
                   help="64-char hex private key")
    s.add_argument("--out", default=str(DEFAULT_WALLET))

    # info
    sub.add_parser("info", help="Show address, balance, stake, nonce")

    # send
    s = sub.add_parser("send", help="Send INFER to an address")
    s.add_argument("to_address", metavar="TO")
    s.add_argument("amount",     metavar="AMOUNT", type=float)
    s.add_argument("--fee",      default=1.0, type=float)

    # stake
    s = sub.add_parser("stake", help="Stake INFER tokens")
    s.add_argument("amount", metavar="AMOUNT", type=float)
    s.add_argument("--fee",  default=1.0, type=float)

    # unstake
    s = sub.add_parser("unstake", help="Unstake INFER tokens")
    s.add_argument("amount", metavar="AMOUNT", type=float)
    s.add_argument("--fee",  default=1.0, type=float)

    # register
    s = sub.add_parser("register", help="Register as a PoS validator node")
    s.add_argument("--endpoint", required=True,
                   help="Your node's public REST URL, e.g. http://192.168.1.10:8000")
    s.add_argument("--fee", default=10.0, type=float)

    # tx
    s = sub.add_parser("tx", help="Query a transaction by its ID")
    s.add_argument("tx_id", metavar="TX_ID")

    # seal (dev)
    s = sub.add_parser("seal", help="[Dev] Manually seal a block on the node")
    s.add_argument("--proposer", default=None,
                   help="Proposer node_id (default: node-<port>)")

    return p


def main() -> None:
    parser  = build_parser()
    args    = parser.parse_args()

    dispatch = {
        "new":      cmd_new,
        "import":   cmd_import,
        "info":     cmd_info,
        "send":     cmd_send,
        "stake":    cmd_stake,
        "unstake":  cmd_unstake,
        "register": cmd_register,
        "tx":       cmd_tx,
        "seal":     cmd_seal,
    }

    dispatch[args.command](args)


if __name__ == "__main__":
    main()
