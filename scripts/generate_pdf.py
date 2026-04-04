# -*- coding: utf-8 -*-
"""
Generate InferenceChain whitepaper PDF.
Usage: python scripts/generate_pdf.py
Output: InferenceChain_Whitepaper.pdf
"""

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_JUSTIFY
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, PageBreak, KeepTogether,
)
from reportlab.platypus.flowables import Flowable
from reportlab.graphics.shapes import Drawing, Rect, String, Line, Circle
from reportlab.graphics import renderPDF
import os

# ── Colours ───────────────────────────────────────────────────────────────────
PURPLE      = colors.HexColor("#7c3aed")
PURPLE_DARK = colors.HexColor("#5b21b6")
BLUE        = colors.HexColor("#3b82f6")
CYAN        = colors.HexColor("#06b6d4")
GREEN       = colors.HexColor("#10b981")
DARK        = colors.HexColor("#0f0f1a")
DARK2       = colors.HexColor("#1a1a2e")
DARK3       = colors.HexColor("#16213e")
TEXT1       = colors.HexColor("#f0f0ff")
TEXT2       = colors.HexColor("#a0a0c0")
WHITE       = colors.white
BORDER      = colors.HexColor("#2a2a4a")

PAGE_W, PAGE_H = A4
MARGIN = 2.2 * cm

# ── Styles ────────────────────────────────────────────────────────────────────
styles = getSampleStyleSheet()

def S(name, **kw):
    return ParagraphStyle(name, **kw)

cover_title = S("CoverTitle",
    fontSize=38, leading=46, textColor=WHITE,
    fontName="Helvetica-Bold", alignment=TA_CENTER)

cover_sub = S("CoverSub",
    fontSize=16, leading=24, textColor=colors.HexColor("#a78bfa"),
    fontName="Helvetica", alignment=TA_CENTER)

cover_tag = S("CoverTag",
    fontSize=11, leading=16, textColor=TEXT2,
    fontName="Helvetica", alignment=TA_CENTER)

h1 = S("H1",
    fontSize=22, leading=30, textColor=WHITE,
    fontName="Helvetica-Bold", spaceBefore=22, spaceAfter=8,
    borderPad=0)

h2 = S("H2",
    fontSize=15, leading=22, textColor=colors.HexColor("#a78bfa"),
    fontName="Helvetica-Bold", spaceBefore=14, spaceAfter=6)

h3 = S("H3",
    fontSize=12, leading=18, textColor=CYAN,
    fontName="Helvetica-Bold", spaceBefore=10, spaceAfter=4)

body = S("Body",
    fontSize=10, leading=16, textColor=TEXT2,
    fontName="Helvetica", alignment=TA_JUSTIFY,
    spaceAfter=6)

body_white = S("BodyW",
    fontSize=10, leading=16, textColor=WHITE,
    fontName="Helvetica", alignment=TA_JUSTIFY,
    spaceAfter=6)

bullet = S("Bullet",
    fontSize=10, leading=15, textColor=TEXT2,
    fontName="Helvetica", leftIndent=16, spaceAfter=4,
    bulletIndent=4)

mono = S("Mono",
    fontSize=9, leading=14, textColor=colors.HexColor("#c4b5fd"),
    fontName="Courier", leftIndent=12, spaceAfter=4)

caption = S("Caption",
    fontSize=8, leading=12, textColor=TEXT2,
    fontName="Helvetica", alignment=TA_CENTER, spaceAfter=10)

# ── Custom flowables ──────────────────────────────────────────────────────────

class DarkRect(Flowable):
    """Full-width coloured background rectangle."""
    def __init__(self, h=12, color=DARK2, radius=6):
        super().__init__()
        self.bh = h; self.color = color; self.radius = radius
    def wrap(self, aw, ah): self.aw = aw; return (aw, self.bh)
    def draw(self):
        self.canv.setFillColor(self.color)
        self.canv.roundRect(0, 0, self.aw, self.bh, self.radius, fill=1, stroke=0)

class GradientHeader(Flowable):
    """Coloured left-border section header background."""
    def __init__(self, text, h=36):
        super().__init__()
        self.text = text; self.bh = h
    def wrap(self, aw, ah): self.aw = aw; return (aw, self.bh)
    def draw(self):
        c = self.canv
        # Background
        c.setFillColor(DARK2)
        c.roundRect(0, 0, self.aw, self.bh, 4, fill=1, stroke=0)
        # Left accent bar
        c.setFillColor(PURPLE)
        c.rect(0, 0, 4, self.bh, fill=1, stroke=0)
        # Text
        c.setFillColor(WHITE)
        c.setFont("Helvetica-Bold", 14)
        c.drawString(14, 11, self.text)

class HRule(Flowable):
    def __init__(self, color=BORDER, thickness=0.5):
        super().__init__(); self.color = color; self.thickness = thickness
    def wrap(self, aw, ah): self.aw = aw; return (aw, 1)
    def draw(self):
        self.canv.setStrokeColor(self.color)
        self.canv.setLineWidth(self.thickness)
        self.canv.line(0, 0, self.aw, 0)

class CoverHexagon(Flowable):
    """Draws the InferenceChain ⬡ logo as a proper hexagon with glow."""
    def __init__(self, size=72):
        super().__init__()
        self.size = size

    def wrap(self, aw, ah):
        self.aw = aw
        return (aw, self.size * 2 + 20)

    def draw(self):
        import math
        c = self.canv
        cx = self.aw / 2
        cy = self.size + 10
        r  = self.size

        # Glow rings
        for i, (rad, alpha) in enumerate([(r+22, 0.06), (r+12, 0.12), (r+4, 0.22)]):
            c.setFillColor(colors.HexColor("#7c3aed"))
            c.setFillAlpha(alpha)
            pts = []
            for k in range(6):
                ang = math.radians(60*k - 30)
                pts.append((cx + rad*math.cos(ang), cy + rad*math.sin(ang)))
            p = c.beginPath()
            p.moveTo(*pts[0])
            for pt in pts[1:]: p.lineTo(*pt)
            p.close()
            c.drawPath(p, fill=1, stroke=0)
        c.setFillAlpha(1)

        # Main hexagon fill — gradient approximated with two rects clipped
        pts = []
        for k in range(6):
            ang = math.radians(60*k - 30)
            pts.append((cx + r*math.cos(ang), cy + r*math.sin(ang)))
        p = c.beginPath()
        p.moveTo(*pts[0])
        for pt in pts[1:]: p.lineTo(*pt)
        p.close()
        c.setFillColor(PURPLE_DARK)
        c.drawPath(p, fill=1, stroke=0)

        # Inner highlight hexagon
        r2 = r * 0.7
        pts2 = []
        for k in range(6):
            ang = math.radians(60*k - 30)
            pts2.append((cx + r2*math.cos(ang), cy + r2*math.sin(ang)))
        p2 = c.beginPath()
        p2.moveTo(*pts2[0])
        for pt in pts2[1:]: p2.lineTo(*pt)
        p2.close()
        c.setFillColor(PURPLE)
        c.drawPath(p2, fill=1, stroke=0)

        # Border stroke
        c.setStrokeColor(colors.HexColor("#a78bfa"))
        c.setLineWidth(2)
        p3 = c.beginPath()
        p3.moveTo(*pts[0])
        for pt in pts[1:]: p3.lineTo(*pt)
        p3.close()
        c.drawPath(p3, fill=0, stroke=1)

        # ⬡ symbol in centre
        c.setFillColor(WHITE)
        c.setFont("Helvetica-Bold", int(r * 0.75))
        c.drawCentredString(cx, cy - r*0.27, u"\u2b21")

# ── Background canvas callback ────────────────────────────────────────────────

def dark_background(canvas, doc):
    canvas.saveState()
    canvas.setFillColor(DARK)
    canvas.rect(0, 0, PAGE_W, PAGE_H, fill=1, stroke=0)
    # Subtle top gradient band
    canvas.setFillColor(DARK2)
    canvas.rect(0, PAGE_H - 60, PAGE_W, 60, fill=1, stroke=0)
    # Footer
    canvas.setFillColor(colors.HexColor("#12122a"))
    canvas.rect(0, 0, PAGE_W, 28, fill=1, stroke=0)
    canvas.setFillColor(TEXT2)
    canvas.setFont("Helvetica", 8)
    canvas.drawString(MARGIN, 10, "InferenceChain — Confidential Research Preview")
    canvas.drawRightString(PAGE_W - MARGIN, 10, f"Page {doc.page}")
    canvas.restoreState()

# ── Helper to build stat table ────────────────────────────────────────────────

def stat_table(rows, col_widths=None):
    w = PAGE_W - 2*MARGIN
    if col_widths is None:
        col_widths = [w*0.38, w*0.62]
    data = []
    for k, v in rows:
        data.append([
            Paragraph(f"<b>{k}</b>", S("tk", fontSize=9, textColor=CYAN, fontName="Helvetica-Bold")),
            Paragraph(str(v), S("tv", fontSize=9, textColor=WHITE, fontName="Helvetica")),
        ])
    t = Table(data, colWidths=col_widths, hAlign="LEFT")
    t.setStyle(TableStyle([
        ("BACKGROUND",  (0,0), (-1,-1), DARK2),
        ("ROWBACKGROUNDS", (0,0), (-1,-1), [DARK2, DARK3]),
        ("TEXTCOLOR",   (0,0), (-1,-1), WHITE),
        ("FONTSIZE",    (0,0), (-1,-1), 9),
        ("LEADING",     (0,0), (-1,-1), 14),
        ("TOPPADDING",  (0,0), (-1,-1), 6),
        ("BOTTOMPADDING",(0,0),(-1,-1), 6),
        ("LEFTPADDING", (0,0), (-1,-1), 10),
        ("RIGHTPADDING",(0,0),(-1,-1), 10),
        ("LINEABOVE",   (0,0), (-1,-1), 0.3, BORDER),
        ("LINEBELOW",   (0,-1),(-1,-1), 0.3, BORDER),
        ("ROUNDEDCORNERS", [4]),
    ]))
    return t

def two_col_table(rows, header=None):
    w = PAGE_W - 2*MARGIN
    data = []
    if header:
        data.append([
            Paragraph(f"<b>{header[0]}</b>", S("th", fontSize=9, textColor=CYAN, fontName="Helvetica-Bold")),
            Paragraph(f"<b>{header[1]}</b>", S("th2", fontSize=9, textColor=CYAN, fontName="Helvetica-Bold")),
        ])
    for a, b in rows:
        data.append([
            Paragraph(str(a), S("ta", fontSize=9, textColor=WHITE, fontName="Helvetica-Bold")),
            Paragraph(str(b), S("tb", fontSize=9, textColor=TEXT2, fontName="Helvetica", leading=13)),
        ])
    t = Table(data, colWidths=[w*0.28, w*0.72], hAlign="LEFT")
    style = [
        ("BACKGROUND",   (0,0), (-1,-1), DARK2),
        ("ROWBACKGROUNDS",(0,0),(-1,-1), [DARK3, DARK2]),
        ("TOPPADDING",   (0,0), (-1,-1), 7),
        ("BOTTOMPADDING",(0,0), (-1,-1), 7),
        ("LEFTPADDING",  (0,0), (-1,-1), 10),
        ("RIGHTPADDING", (0,0), (-1,-1), 10),
        ("LINEBELOW",    (0,0), (-1,-1), 0.3, BORDER),
    ]
    if header:
        style += [
            ("BACKGROUND", (0,0), (-1,0), PURPLE_DARK),
            ("TEXTCOLOR",  (0,0), (-1,0), WHITE),
        ]
    t.setStyle(TableStyle(style))
    return t

def p(text, style=body): return Paragraph(text, style)
def sp(n=8): return Spacer(1, n)

# ── Build document ─────────────────────────────────────────────────────────────

out = os.path.join(os.path.dirname(__file__), "..", "InferenceChain_Whitepaper.pdf")
doc = SimpleDocTemplate(
    out,
    pagesize=A4,
    leftMargin=MARGIN, rightMargin=MARGIN,
    topMargin=MARGIN, bottomMargin=MARGIN,
    title="InferenceChain Whitepaper",
    author="Dimitrios Papaioannou",
)

story = []

# ─────────────────────────────────────────────────────────────────────────────
# COVER
# ─────────────────────────────────────────────────────────────────────────────
story += [
    sp(60),
    CoverHexagon(size=68),
    sp(28),
    p("InferenceChain", cover_title),
    sp(8),
    HRule(color=PURPLE, thickness=1.5),
    sp(14),
    p("A Decentralised Blockchain Native to AI Inference", cover_sub),
    sp(28),
    p("Quality of Inference Consensus &nbsp;·&nbsp; Proof of Quality of Inference &nbsp;·&nbsp; Sharded BFT",
      S("pills", fontSize=11, textColor=colors.HexColor("#a78bfa"),
        fontName="Helvetica-Bold", alignment=TA_CENTER,
        backColor=colors.HexColor("#1a0a3a"), borderPad=6)),
    sp(40),
    HRule(color=BORDER, thickness=0.5),
    sp(14),
    p("Technical Whitepaper &amp; Vision Document", cover_tag),
    sp(4),
    p("Research Preview · v0.1 · April 2026", cover_tag),
    sp(10),
    p("Dimitrios Papaioannou", S("auth", fontSize=12, textColor=WHITE,
      fontName="Helvetica-Bold", alignment=TA_CENTER)),
    p("Aristotle University of Thessaloniki (AUTH) · InferenceChain Research",
      S("inst", fontSize=10, textColor=TEXT2, fontName="Helvetica", alignment=TA_CENTER)),
    PageBreak(),
]

# ─────────────────────────────────────────────────────────────────────────────
# TABLE OF CONTENTS
# ─────────────────────────────────────────────────────────────────────────────
story += [
    GradientHeader("Table of Contents", h=40),
    sp(16),
]

toc_items = [
    ("1", "Abstract"),
    ("2", "Problem Statement"),
    ("3", "Architecture Overview"),
    ("4", "Quality of Inference Consensus (QoI)"),
    ("5", "Proof of Quality of Inference (PoQI) — On-chain Reputation"),
    ("6", "Proof of Model (PoM) — Admission Protocol"),
    ("7", "Sharded BFT Architecture (S-BFT)"),
    ("8", "Block Structure & Transaction Types"),
    ("9", "What Is Already Built"),
    ("10", "Tokenomics — INFER Token"),
    ("11", "Vision & Roadmap"),
    ("12", "Conclusion"),
]
for num, title in toc_items:
    story.append(p(f"<b><font color='#7c3aed'>{num}.</font></b>  {title}",
                   S("toc", fontSize=11, leading=20, textColor=WHITE, fontName="Helvetica")))

story.append(PageBreak())

# ─────────────────────────────────────────────────────────────────────────────
# 1. ABSTRACT
# ─────────────────────────────────────────────────────────────────────────────
story += [
    GradientHeader("1.  Abstract"),
    sp(10),
    p("""InferenceChain is a novel blockchain protocol designed specifically for decentralised
AI inference. Unlike general-purpose blockchains that treat computation as an opaque
black box, InferenceChain introduces inference <i>quality</i> as a first-class consensus
property. Validators do not merely agree on transaction order — they agree on the
<i>correctness</i> of deep neural network (DNN) outputs."""),
    sp(6),
    p("""Three novel primitives drive the protocol: <b>Quality of Inference Consensus (QoI)</b>,
a PBFT-derived algorithm that uses cosine similarity between inference vectors to reach
Byzantine-fault-tolerant agreement; <b>Proof of Quality of Inference (PoQI)</b>, an
on-chain reputation system that quantifies each validator's historical accuracy and
weights their future influence accordingly; and <b>Sharded BFT (S-BFT)</b>, a horizontal
scaling layer that partitions the validator set into independent committees to achieve
linear throughput growth without sacrificing BFT safety guarantees."""),
    sp(6),
    p("""A working testnet implementation — including the full consensus engine, P2P gossip
layer, on-chain state machine, model admission protocol, and a live web dashboard — has
been developed and is described in this document."""),
    sp(16),
]

# ─────────────────────────────────────────────────────────────────────────────
# 2. PROBLEM STATEMENT
# ─────────────────────────────────────────────────────────────────────────────
story += [
    GradientHeader("2.  Problem Statement"),
    sp(10),
    p("""The rise of AI inference as a service has created a critical centralisation risk.
Today, virtually all AI inference is performed by a handful of large cloud providers.
Users have no way to verify that the model they requested actually ran, that the output
has not been tampered with, or that the service provider is not selectively serving
degraded results."""),
    sp(6),
    p("Existing blockchain-based approaches fall into two categories, both inadequate:"),
    sp(4),
]

problems = [
    ("Optimistic execution", "Assume the inference result is correct and only dispute on-chain after the fact. Disputes are slow, expensive, and rely on a trusted arbiter."),
    ("Commit-reveal schemes", "A node commits to a result hash then reveals it. This prevents copying but provides no quality guarantee — a node can commit a random hash."),
    ("Reputation without verification", "Systems that track reputation without on-chain verifiable proof of model quality are gameable. A node can report high accuracy it never achieved."),
    ("General-purpose BFT", "Standard PBFT agrees on values, not on quality. Two nodes producing different (but equally valid) inference outputs would cause consensus to fail even if both are correct."),
]
story.append(two_col_table(problems, header=("Approach", "Limitation")))
story += [sp(10),
p("""InferenceChain addresses all four limitations simultaneously. Consensus is reached on
inference <i>quality</i>, verified by mathematical comparison (cosine similarity).
Reputation is an on-chain quantity, updated deterministically by protocol rules.
Admission requires cryptographic proof of model capability before a node may participate."""),
sp(16)]

# ─────────────────────────────────────────────────────────────────────────────
# 3. ARCHITECTURE OVERVIEW
# ─────────────────────────────────────────────────────────────────────────────
story += [
    GradientHeader("3.  Architecture Overview"),
    sp(10),
    p("""InferenceChain separates concerns cleanly across four layers:"""),
    sp(6),
]

arch_layers = [
    ("Network Layer", "P2P gossip over WebSocket connections. Each node maintains persistent connections to peers. Messages are typed (CONSENSUS, TRANSACTION, BLOCK, PEER_DISCOVERY) and routed accordingly."),
    ("Consensus Layer", "Two concurrent consensus protocols. QoI consensus runs when an INFERENCE_REQUEST transaction enters the mempool. PoS consensus runs for all other (simple) transaction blocks."),
    ("State Layer", "A single ChainState object is the authoritative source of truth — balances, stakes, reputations, registered nodes, inference log, contract state. All reads bypass any off-chain registry."),
    ("Application Layer", "FastAPI REST + WebSocket API served on port 8000. A compiled React dashboard is served at /ui. All data shown in the UI is read directly from chain state."),
]
story.append(two_col_table(arch_layers, header=("Layer", "Responsibility")))
story += [sp(16)]

# ─────────────────────────────────────────────────────────────────────────────
# 4. QoI CONSENSUS
# ─────────────────────────────────────────────────────────────────────────────
story += [
    GradientHeader("4.  Quality of Inference Consensus (QoI)"),
    sp(10),
    p("""QoI is a three-phase Byzantine-fault-tolerant consensus protocol derived from PBFT,
adapted to agree not on an arbitrary value but on the <i>quality</i> of a DNN inference
result. The key insight is that correct DNN inference on the same image produces output
probability vectors that are mathematically close — measurable by cosine similarity."""),
    sp(8),
    p("The protocol requires n ≥ 3f + 1 validators to tolerate f Byzantine nodes.", body_white),
    sp(10),
    p("<b>Phase 1 — PRE-PREPARE</b>", h3),
    p("""The primary (proposer) receives an INFERENCE_REQUEST containing an image hash.
It fetches the image from the requesting client, runs it through its local DNN model,
and broadcasts a PRE_PREPARE message containing its output probability vector
(softmax over 10 CIFAR-10 classes)."""),
    sp(6),
    p("<b>Phase 2 — PREPARE</b>", h3),
    p("""Each DNN validator independently runs the same image through its own local model.
It computes the cosine similarity between its output vector and the primary's vector.
If the similarity exceeds the threshold, it broadcasts a PREPARE message with its own
vector. The primary collects PREPARE messages until it has 2f+1."""),
    sp(6),
    p("<b>Phase 3 — COMMIT</b>", h3),
    p("""Once 2f+1 PREPARE messages are collected, the primary broadcasts a COMMIT message.
Each validator that has seen 2f+1 PREPAREs broadcasts its own COMMIT.
When a node collects 2f+1 COMMITs, the round is finalised. A QoI block is appended
to the chain containing the consensus result, all signatures, and reputation deltas."""),
    sp(10),
    p("<b>Quality Scoring</b>", h3),
    p("""After each round, each validator's output vector is compared pairwise against all
others. Validators whose vectors lie within the cosine similarity threshold of the
majority cluster are marked as honest and receive reputation increases proportional
to their similarity score. Outliers (Byzantine or low-quality nodes) are penalised."""),
    sp(16),
]

# ─────────────────────────────────────────────────────────────────────────────
# 5. PoQI
# ─────────────────────────────────────────────────────────────────────────────
story += [
    GradientHeader("5.  Proof of Quality of Inference (PoQI)"),
    sp(10),
    p("""PoQI is the on-chain reputation system that tracks each validator's cumulative
inference quality. It is not a separate consensus protocol — it is a deterministic
state transition that occurs at the end of every QoI round."""),
    sp(8),
    p("Reputation parameters (from protocol constants):", h3),
]
story.append(stat_table([
    ("Initial reputation",      "0.0  (all nodes start equal)"),
    ("Max gain per round",      "0.5  (REP_CAP_PER_ROUND)"),
    ("Penalty per Byzantine act","0.3  (REP_PENALTY)"),
    ("Leader bonus per round",  "+0.1 on top of quality-proportional gain"),
    ("Reputation cap",          "No hard cap — grows unboundedly with consistent quality"),
    ("Reputation floor",        "0.0  (cannot go negative)"),
]))
story += [
    sp(10),
    p("""Reputation serves two functions: it weights the proposer election (higher reputation
→ higher probability of being selected as primary), and it weights block reward
distribution. A validator that consistently produces high-quality inference results
earns disproportionately more INFER tokens over time — creating a strong economic
incentive for model quality maintenance."""),
    sp(16),
]

# ─────────────────────────────────────────────────────────────────────────────
# 6. PoM
# ─────────────────────────────────────────────────────────────────────────────
story += [
    GradientHeader("6.  Proof of Model (PoM) — Admission Protocol"),
    sp(10),
    p("""Before a node may participate in QoI consensus, it must pass the Proof of Model
admission protocol. PoM prevents Sybil attacks and ensures that every active DNN
validator in the network actually possesses a model that meets minimum quality standards."""),
    sp(8),
    p("Admission flow:", h3),
]

pom_steps = [
    ("Step 1 — Register", "Node submits a NODE_REGISTER_DNN transaction containing: model name, weights SHA-256 hash (on-chain commitment), endpoint URL, dataset ID, architecture JSON, and public key. Node status: PENDING_POM."),
    ("Step 2 — Challenge", "Protocol generates a MODEL_CHALLENGE transaction with 50 deterministically selected CIFAR-10 test samples. Seed = SHA-256(prev_block_hash + node_address) — fully reproducible by any verifier."),
    ("Step 3 — Response", "Challenged node runs the 50 samples through its model and broadcasts a MODEL_RESPONSE transaction with its predictions within the timeout window (30 seconds)."),
    ("Step 4 — Verification", "Existing DNN validators independently verify the response against known CIFAR-10 test labels. Each broadcasts a MODEL_VERIFY transaction with pass/fail."),
    ("Step 5 — Admission", "If ≥ 80% accuracy is achieved and enough verifiers agree, a NODE_ADMITTED transaction is committed. Node becomes active. If it fails: NODE_REJECTED — node must re-register."),
]
story.append(two_col_table(pom_steps))
story += [sp(10),
p("""The weights hash committed in Step 1 binds the node to a specific model. If a node
later attempts to serve a different model, the hash mismatch is detectable on-chain
by any verifier — providing cryptographic proof of model substitution fraud."""),
sp(16)]

# ─────────────────────────────────────────────────────────────────────────────
# 7. S-BFT
# ─────────────────────────────────────────────────────────────────────────────
story += [
    GradientHeader("7.  Sharded BFT Architecture (S-BFT)"),
    sp(10),
    p("""Standard PBFT has O(n²) message complexity — as the validator set grows, the
communication overhead grows quadratically, making it impractical beyond ~100 nodes.
S-BFT solves this by partitioning the validator set into independent committees."""),
    sp(8),
    p("""Each committee runs a complete, independent QoI consensus instance in parallel.
Different inference requests are routed to different committees. Throughput scales
linearly with the number of committees while each committee maintains full BFT
safety guarantees (tolerating f Byzantine nodes within the committee)."""),
    sp(8),
    p("""Cross-committee coordination is minimal: a lightweight inter-committee finalisation
layer aggregates committee results and writes them to the main chain. The sharding
scheme is deterministic — committee assignment for a given inference request is
derived from the request hash, making routing verifiable and unpredictable by
adversaries."""),
    sp(16),
]

# ─────────────────────────────────────────────────────────────────────────────
# 8. BLOCK STRUCTURE & TRANSACTION TYPES
# ─────────────────────────────────────────────────────────────────────────────
story += [
    GradientHeader("8.  Block Structure & Transaction Types"),
    sp(10),
    p("<b>Two block types</b>", h3),
]

block_types = [
    ("QoI Block", "Produced after a successful QoI consensus round. Contains exactly one INFERENCE_REQUEST, plus system transactions: INFERENCE_RESPONSE, CONSENSUS_RESULT, REWARD entries for each participating validator, and reputation delta updates. Committed by the QoI state machine."),
    ("PoS Block", "Produced for all simple (non-inference) transactions. Contains up to 50 simple transactions per block. Proposer is selected by stake × reputation weighting. Committed by the PoS consensus machine with 2f+1 votes."),
]
story.append(two_col_table(block_types))
story += [sp(10), p("<b>Transaction taxonomy</b>", h3)]

tx_types = [
    ("TOKEN_TRANSFER",    "Simple", "Peer-to-peer INFER token transfer"),
    ("STAKE / UNSTAKE",   "Simple", "Lock / unlock tokens as validator stake"),
    ("NODE_REGISTER_DNN", "Simple", "Register as a DNN validator (triggers PoM)"),
    ("NODE_REGISTER_POS", "Simple", "Register as a PoS-only validator"),
    ("MODEL_RESPONSE",    "Simple", "Node's answer to a PoM challenge"),
    ("INFERENCE_REQUEST", "Inference", "Client submits an image for consensus inference"),
    ("INFERENCE_RESPONSE","System", "Protocol records a validator's output vector"),
    ("CONSENSUS_RESULT",  "System", "Final agreed inference result"),
    ("REWARD",            "System", "Token minted to a validator for honest participation"),
    ("SLASH",             "System", "Tokens burned from a validator for Byzantine behaviour"),
    ("MODEL_CHALLENGE",   "System", "Protocol challenges a pending node's model"),
    ("MODEL_VERIFY",      "System", "Existing validator verifies a challenge response"),
    ("NODE_ADMITTED",     "System", "Node passed PoM — becomes active"),
    ("NODE_REJECTED",     "System", "Node failed PoM — must re-register"),
]

w = PAGE_W - 2*MARGIN
tx_table_data = [[
    Paragraph("<b>Type</b>",   S("th", fontSize=8, textColor=CYAN, fontName="Helvetica-Bold")),
    Paragraph("<b>Family</b>", S("th", fontSize=8, textColor=CYAN, fontName="Helvetica-Bold")),
    Paragraph("<b>Purpose</b>",S("th", fontSize=8, textColor=CYAN, fontName="Helvetica-Bold")),
]]
for typ, fam, desc in tx_types:
    fam_color = {"Simple": "#10b981", "Inference": "#a78bfa", "System": "#06b6d4"}[fam]
    tx_table_data.append([
        Paragraph(f"<font name='Courier' size='8' color='#c4b5fd'>{typ}</font>", body),
        Paragraph(f"<font color='{fam_color}' size='8'>{fam}</font>", body),
        Paragraph(desc, S("td", fontSize=8, leading=12, textColor=TEXT2, fontName="Helvetica")),
    ])

tx_t = Table(tx_table_data, colWidths=[w*0.32, w*0.15, w*0.53], hAlign="LEFT")
tx_t.setStyle(TableStyle([
    ("BACKGROUND",    (0,0),(-1,-1), DARK2),
    ("BACKGROUND",    (0,0),(-1, 0), PURPLE_DARK),
    ("ROWBACKGROUNDS",(0,1),(-1,-1), [DARK3, DARK2]),
    ("TOPPADDING",    (0,0),(-1,-1), 5),
    ("BOTTOMPADDING", (0,0),(-1,-1), 5),
    ("LEFTPADDING",   (0,0),(-1,-1), 8),
    ("RIGHTPADDING",  (0,0),(-1,-1), 8),
    ("LINEBELOW",     (0,0),(-1,-1), 0.3, BORDER),
]))
story.append(tx_t)
story.append(PageBreak())

# ─────────────────────────────────────────────────────────────────────────────
# 9. WHAT IS ALREADY BUILT
# ─────────────────────────────────────────────────────────────────────────────
story += [
    GradientHeader("9.  What Is Already Built"),
    sp(10),
    p("""The following components are fully implemented and operational on the local testnet
as of April 2026. This is not a paper prototype — all described functionality runs
as working Python/React code."""),
    sp(10),
]

built = [
    ("Blockchain Core",
     "Full chain with QoI and PoS block types, Merkle root computation, SHA-256 block hashing, chain validation, genesis block with 10M INFER allocation, SQLite-backed persistent storage."),
    ("State Machine",
     "ChainState tracks balances, stakes, reputations, registered nodes (DNN & PoS), PoM states, inference log, and smart contract state. All reads are authoritative from chain, no off-chain registries."),
    ("QoI Consensus Engine",
     "Full 3-phase PBFT-derived consensus (PRE-PREPARE → PREPARE → COMMIT). View-change protocol for primary failure recovery. Timeout manager. Message scheduler. Async state machine."),
    ("PoS Consensus",
     "Parallel PoS consensus for simple transaction blocks. Stake × reputation weighted proposer election. 2f+1 vote threshold. Auto-commits in single-node dev mode."),
    ("Proof of Model (PoM)",
     "Full admission protocol: challenge generation (deterministic seed), response verification against CIFAR-10 ground truth, tally logic, NODE_ADMITTED / NODE_REJECTED system transactions."),
    ("P2P Gossip Layer",
     "WebSocket-based peer-to-peer network. Message types: CONSENSUS, TRANSACTION, BLOCK, PEER_DISCOVERY. Persistent connections with reconnect logic. Image fetch protocol for inference requests."),
    ("REST API (FastAPI)",
     "40+ endpoints across /chain, /state, /tx, /p2p, /dashboard, /ws namespaces. Full OpenAPI docs at /docs. WebSocket streams for live consensus events."),
    ("Model Registry",
     "Local off-chain model staging with SQLite backend. Upload → validate → approve pipeline. ModelValidator runs size, loadability, and latency benchmarks. SHA-256 weights commitment."),
    ("Cryptographic Identity",
     "Ed25519 key generation, transaction signing, signature verification. Node identity persisted to JSON keyfiles. Hex-encoded public keys committed on-chain."),
    ("Frontend Dashboard",
     "React SPA with 6 pages: Landing (live stats, canvas particles, circuit hero), Chain Explorer (search, block detail, tx panel, charts), Validators (reputation leaderboard), Inference (submit + consensus monitor), Network (P2P topology, live event stream), Become a Node (4-step DNN registration wizard)."),
    ("Vercel Deployment",
     "Production build configured for Vercel with vercel.json. .env.production sets relative API URLs for same-origin serving. Deployed at inferencechain.vercel.app (or equivalent)."),
    ("Test Suite",
     "Unit and integration tests covering chain state transitions, QoI consensus rounds, PoM flow, P2P image fetch, dashboard API, and transaction serialisation."),
]

for component, description in built:
    story.append(KeepTogether([
        p(f"<b><font color='#a78bfa'>▸</font>  {component}</b>",
          S("bc", fontSize=11, textColor=WHITE, fontName="Helvetica-Bold", spaceBefore=8, spaceAfter=3)),
        p(description),
        sp(2),
    ]))

story.append(PageBreak())

# ─────────────────────────────────────────────────────────────────────────────
# 10. TOKENOMICS
# ─────────────────────────────────────────────────────────────────────────────
story += [
    GradientHeader("10.  Tokenomics — INFER Token"),
    sp(10),
    p("""The INFER token is the native currency of InferenceChain. It serves three distinct
roles: <b>economic incentive</b> for honest inference quality, <b>security bond</b>
that makes Byzantine behaviour costly, and <b>governance weight</b> for future
protocol parameter votes."""),
    sp(10),
    p("<b>Supply parameters</b>", h3),
]
story.append(stat_table([
    ("Token name",          "INFER"),
    ("Maximum supply",      "100,000,000 INFER  (100M hard cap)"),
    ("Genesis allocation",  "10,000,000 INFER   (10% — minted at block 0)"),
    ("Block reward",        "10.0 INFER per QoI consensus round"),
    ("Leader bonus",        "+2.0 INFER for the primary that drove the round"),
    ("Slash penalty",       "100.0 INFER burned per confirmed Byzantine act"),
    ("Min stake — DNN",     "1,000 INFER"),
    ("Min stake — PoS",     "500 INFER"),
]))

story += [sp(12), p("<b>Reward distribution per QoI round</b>", h3),
p("""When a QoI round reaches COMMIT, the protocol mints INFER and distributes it as follows:"""),
sp(6)]

reward_rows = [
    ("Primary (proposer)",   "Base reward × (1 + leader_bonus_ratio) — higher share for driving consensus"),
    ("Honest validators",    "Proportional share of remaining reward, weighted by cosine similarity score"),
    ("Byzantine validators", "Zero reward + 100 INFER slashed from stake"),
    ("PoS validators",       "Proportional share of PoS block reward (separate pool, no inference bonus)"),
]
story.append(two_col_table(reward_rows, header=("Recipient", "Amount")))

story += [
    sp(12),
    p("<b>Stake economics</b>", h3),
    p("""Stake serves as a security deposit. A node that is confirmed Byzantine by the
protocol loses 100 INFER from its staked balance. If the stake falls below the minimum
(1,000 INFER for DNN), the node is automatically deactivated. This creates a direct
cost for Byzantine behaviour proportional to the expected value of sustained honest
participation — the classical mechanism for making attacks economically irrational."""),
    sp(10),
    p("<b>Reputation × stake interaction</b>", h3),
    p("""Block reward shares are computed as:"""),
    p("reward_share(i) = (stake(i) × reputation(i)) / Σ (stake(j) × reputation(j))", mono),
    p("""This means a node with twice the stake but half the reputation earns the same as
a node with equal stake and reputation — quality and capital are equally weighted.
A new node with zero reputation earns nothing until it demonstrates quality,
regardless of how much it stakes. This prevents pure capital dominance."""),
    sp(10),
    p("<b>Genesis allocation rationale</b>", h3),
    p("""10M INFER is pre-minted at genesis and distributed to bootstrap nodes. This
provides the initial stake pool necessary for the network to function before any
block rewards have accumulated. Genesis nodes are expected to be research nodes
operated by the protocol authors — their identity and stakes are committed in the
genesis block and auditable by all participants."""),
    sp(10),
    p("<b>Emission schedule</b>", h3),
    p("""At 10 INFER per QoI block and a 5-second block target, the maximum theoretical
emission rate is approximately 6.3M INFER per year (10 × 6M seconds / 5 target seconds
but reduced by actual block production rate). At this rate, the remaining 90M INFER
supply would take ~14 years to emit — providing a long runway of validator incentives.
In practice, not every 5-second window produces a QoI block (only when inference
requests are pending), so actual emission is demand-driven."""),
    PageBreak(),
]

# ─────────────────────────────────────────────────────────────────────────────
# 11. VISION & ROADMAP
# ─────────────────────────────────────────────────────────────────────────────
story += [
    GradientHeader("11.  Vision & Roadmap"),
    sp(10),
    p("""InferenceChain's long-term vision is to become the trust layer for AI inference —
the protocol that any application can use to prove that a specific AI model produced
a specific output, that the output quality was independently verified, and that the
verifiers were economically incentivised to be honest."""),
    sp(8),
    p("""This vision positions InferenceChain not as a competitor to AI model providers,
but as an infrastructure layer beneath them — analogous to how TCP/IP is not a
competitor to web applications but the foundation they rely on."""),
    sp(12),
    p("<b>Phase 1 — Foundation (Current: Testnet v0.1)</b>", h3),
]

phase1 = [
    ("✓", "QoI consensus engine (3-phase PBFT, view change, timeout)"),
    ("✓", "PoQI on-chain reputation system"),
    ("✓", "Proof of Model admission protocol"),
    ("✓", "PoS consensus for simple transactions"),
    ("✓", "P2P gossip layer with WebSocket connections"),
    ("✓", "Full REST + WebSocket API"),
    ("✓", "Live web dashboard (React, 6 pages)"),
    ("✓", "DNN validator registration wizard"),
    ("✓", "SQLite-backed persistent chain storage"),
    ("✓", "Ed25519 cryptographic identity"),
]
for status, item in phase1:
    story.append(p(f"<font color='#10b981'>{status}</font>  {item}", bullet))

story += [sp(10), p("<b>Phase 2 — Scaling & Security (Q3 2026)</b>", h3)]
phase2 = [
    ("◎", "S-BFT sharding — partition validator set into parallel committees"),
    ("◎", "Signature aggregation — BLS multi-signatures to reduce COMMIT message size"),
    ("◎", "Peer discovery — full Kademlia DHT for automatic peer finding"),
    ("◎", "Multi-model support — validators serve multiple DNN architectures"),
    ("◎", "Slashing evidence proofs — on-chain verifiable proof of Byzantine behaviour"),
    ("◎", "Light client protocol — verify chain state without full node"),
]
for status, item in phase2:
    story.append(p(f"<font color='#3b82f6'>{status}</font>  {item}", bullet))

story += [sp(10), p("<b>Phase 3 — Ecosystem (Q1 2027)</b>", h3)]
phase3 = [
    ("◎", "Smart contracts — Turing-complete VM for inference result consumers"),
    ("◎", "Cross-chain bridge — export verified inference results to EVM chains"),
    ("◎", "Model marketplace — on-chain registry of validated model architectures"),
    ("◎", "DAO governance — INFER-weighted protocol parameter votes"),
    ("◎", "Mainnet launch — permissionless validator onboarding, full token economy"),
    ("◎", "SDK — Python/JS libraries for submitting inference requests programmatically"),
]
for status, item in phase3:
    story.append(p(f"<font color='#06b6d4'>{status}</font>  {item}", bullet))

story += [
    sp(12),
    p("<b>The broader vision</b>", h3),
    p("""As AI systems become increasingly consequential — in healthcare, law, finance,
autonomous systems — the ability to audit and verify AI outputs becomes a
regulatory and ethical necessity. InferenceChain provides the cryptographic
infrastructure for this audit trail: any inference result committed on-chain can
be independently re-verified by anyone, at any time, with mathematical certainty."""),
    sp(8),
    p("""The end state is a world where AI inference is not a black box operated by a
single trusted party, but a transparent, economically incentivised, and
cryptographically auditable process — running on a network of thousands of
independent validators, none of which can unilaterally corrupt the result."""),
    PageBreak(),
]

# ─────────────────────────────────────────────────────────────────────────────
# 12. CONCLUSION
# ─────────────────────────────────────────────────────────────────────────────
story += [
    GradientHeader("12.  Conclusion"),
    sp(10),
    p("""InferenceChain introduces a fundamentally new class of blockchain protocol — one
designed from first principles for AI inference, not adapted from general-purpose
designs. The three core innovations (QoI, PoQI, S-BFT) together solve the problem
of trustless, verifiable, quality-assured DNN inference at scale."""),
    sp(8),
    p("""A complete working implementation has been built, demonstrating that the protocol
is not merely theoretical. The testnet runs QoI consensus rounds, admits validators
through PoM, tracks on-chain reputation, and serves a full-featured web dashboard —
all operating as a coherent system."""),
    sp(8),
    p("""The INFER token creates a self-sustaining economic system where quality incentives
and security incentives are aligned: the same stake that secures the network
proportionally determines reward shares, and reputation — earned only through
demonstrated inference quality — amplifies that stake's influence."""),
    sp(8),
    p("""InferenceChain is positioned to become the trust infrastructure for the AI era —
the protocol that makes AI outputs as verifiable as blockchain transactions."""),
    sp(30),
    HRule(color=PURPLE),
    sp(10),
    p("Dimitrios Papaioannou", S("sig", fontSize=12, textColor=WHITE, fontName="Helvetica-Bold", alignment=TA_CENTER)),
    p("InferenceChain Research · Aristotle University of Thessaloniki (AUTH)", caption),
    p("April 2026 · Research Preview v0.1", caption),
]

# ─────────────────────────────────────────────────────────────────────────────
# BUILD
# ─────────────────────────────────────────────────────────────────────────────
doc.build(story, onFirstPage=dark_background, onLaterPages=dark_background)
print(f"PDF written to: {os.path.abspath(out)}")
