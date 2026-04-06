"""
generate_whitepaper.py
Generates InferenceChain_Whitepaper.pdf from WHITEPAPER.md using ReportLab.
Run: python generate_whitepaper.py
"""

import re
import shutil
import math
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    HRFlowable, PageBreak, Paragraph, SimpleDocTemplate,
    Spacer, Table, TableStyle,
)

# ── Paths ─────────────────────────────────────────────────────────────────────
ROOT       = Path(__file__).parent
MD_PATH    = ROOT / "WHITEPAPER.md"
OUT_PATH   = ROOT / "InferenceChain_Whitepaper.pdf"
PUB_PATH   = ROOT / "frontend" / "public" / "InferenceChain_Whitepaper.pdf"
BUILD_PATH = ROOT / "frontend" / "build"  / "InferenceChain_Whitepaper.pdf"

# ── Colour palette ────────────────────────────────────────────────────────────
BG     = colors.HexColor("#06081a")   # page background
PANEL  = colors.HexColor("#131933")   # section title panels
DARK   = colors.HexColor("#d9e2ff")   # primary text (kept name for compatibility)
ACCENT = colors.HexColor("#7c3aed")   # purple brand accent
MUTED  = colors.HexColor("#9aa8d6")   # secondary text
CODE   = colors.HexColor("#0f1430")   # code block background
RULE   = colors.HexColor("#1e294f")   # separators

# ── Styles ────────────────────────────────────────────────────────────────────
base = getSampleStyleSheet()

def S(name, **kw):
    return ParagraphStyle(name, **kw)

styles = {
    "title": S("WPTitle",
        fontName="Helvetica-Bold", fontSize=28, leading=34,
        textColor=DARK, alignment=TA_CENTER, spaceAfter=4),
    "subtitle": S("WPSubtitle",
        fontName="Helvetica", fontSize=13, leading=18,
        textColor=MUTED, alignment=TA_CENTER, spaceAfter=2),
    "version": S("WPVersion",
        fontName="Helvetica-Oblique", fontSize=10,
        textColor=MUTED, alignment=TA_CENTER, spaceAfter=20),
    "abstract_label": S("AbsLabel",
        fontName="Helvetica-Bold", fontSize=10,
        textColor=ACCENT, spaceAfter=2),
    "abstract": S("Abstract",
        fontName="Helvetica", fontSize=10, leading=15,
        textColor=DARK, alignment=TA_JUSTIFY,
        leftIndent=20, rightIndent=20, spaceAfter=16),
    "h1": S("H1",
        fontName="Helvetica-Bold", fontSize=16, leading=20,
        textColor=colors.white, spaceBefore=20, spaceAfter=8,
        backColor=PANEL, borderColor=ACCENT, borderWidth=0.8,
        borderPadding=8, leftIndent=0, rightIndent=0),
    "h2": S("H2",
        fontName="Helvetica-Bold", fontSize=13, leading=17,
        textColor=DARK, spaceBefore=14, spaceAfter=4),
    "h3": S("H3",
        fontName="Helvetica-BoldOblique", fontSize=11, leading=14,
        textColor=DARK, spaceBefore=10, spaceAfter=3),
    "body": S("Body",
        fontName="Helvetica", fontSize=10, leading=15,
        textColor=DARK, alignment=TA_JUSTIFY, spaceAfter=6),
    "bullet": S("Bullet",
        fontName="Helvetica", fontSize=10, leading=14,
        textColor=DARK, leftIndent=16, bulletIndent=4,
        spaceAfter=3),
    "code": S("Code",
        fontName="Courier", fontSize=8.5, leading=12,
        textColor=colors.HexColor("#dbeafe"),
        backColor=CODE, leftIndent=12, rightIndent=12,
        spaceBefore=4, spaceAfter=6),
    "footer": S("Footer",
        fontName="Helvetica-Oblique", fontSize=8,
        textColor=MUTED, alignment=TA_CENTER),
}

TABLE_STYLE = TableStyle([
    ("BACKGROUND",   (0, 0), (-1, 0),  colors.HexColor("#5b21b6")),
    ("TEXTCOLOR",    (0, 0), (-1, 0),  colors.white),
    ("FONTNAME",     (0, 0), (-1, 0),  "Helvetica-Bold"),
    ("FONTSIZE",     (0, 0), (-1, -1), 9),
    ("FONTNAME",     (0, 1), (-1, -1), "Helvetica"),
    ("ROWBACKGROUNDS",(0,1),(-1,-1),   [colors.HexColor("#121833"), colors.HexColor("#0d132b")]),
    ("GRID",         (0, 0), (-1, -1), 0.4, RULE),
    ("TOPPADDING",   (0, 0), (-1, -1), 4),
    ("BOTTOMPADDING",(0, 0), (-1, -1), 4),
    ("LEFTPADDING",  (0, 0), (-1, -1), 8),
    ("RIGHTPADDING", (0, 0), (-1, -1), 8),
    ("VALIGN",       (0, 0), (-1, -1), "MIDDLE"),
    ("TEXTCOLOR",    (0, 1), (-1, -1), DARK),
])


# ── Markdown → ReportLab flowables ───────────────────────────────────────────

def escape(text):
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

def md_inline(text):
    """Convert inline markdown (bold, code, italic) to ReportLab XML."""
    # code spans first (before bold/italic)
    text = re.sub(r'`([^`]+)`',
        lambda m: f'<font name="Courier" color="#6366f1">{escape(m.group(1))}</font>',
        text)
    text = re.sub(r'\*\*([^*]+)\*\*',
        lambda m: f'<b>{m.group(1)}</b>', text)
    text = re.sub(r'\*([^*]+)\*',
        lambda m: f'<i>{m.group(1)}</i>', text)
    # strikethrough → muted
    text = re.sub(r'~~([^~]+)~~',
        lambda m: f'<font color="#94a3b8"><strike>{m.group(1)}</strike></font>',
        text)
    return text


def parse_md(md_text):
    """
    Coarse markdown parser → list of ReportLab flowables.
    Handles: headings (# ## ###), paragraphs, bullet lists (-),
    fenced code blocks (```), horizontal rules (---), tables (|).
    """
    flowables = []
    lines = md_text.splitlines()
    i = 0
    in_abstract = False

    while i < len(lines):
        line = lines[i]

        # ── Fenced code block ─────────────────────────────────────────────────
        if line.strip().startswith("```"):
            code_lines = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                code_lines.append(escape(lines[i]))
                i += 1
            code_text = "<br/>".join(code_lines) or " "
            flowables.append(Paragraph(code_text, styles["code"]))
            i += 1
            continue

        # ── Horizontal rule ───────────────────────────────────────────────────
        if re.match(r'^-{3,}$', line.strip()) or re.match(r'^#{1,3} -{3,}', line.strip()):
            flowables.append(Spacer(1, 6))
            flowables.append(HRFlowable(width="100%", thickness=0.5, color=RULE))
            flowables.append(Spacer(1, 6))
            i += 1
            continue

        # ── Headings ──────────────────────────────────────────────────────────
        if line.startswith("# ") and not line.startswith("## "):
            title_text = line[2:].strip()
            # Split title / subtitle / version on first "###"
            if "### " in title_text:
                parts = title_text.split("### ", 1)
                flowables.append(Paragraph(escape(parts[0].strip()), styles["title"]))
                flowables.append(Paragraph(escape(parts[1].strip()), styles["subtitle"]))
            else:
                flowables.append(Paragraph(escape(title_text), styles["title"]))
            i += 1
            continue

        if line.startswith("### "):
            flowables.append(Paragraph(md_inline(line[4:].strip()), styles["h3"]))
            i += 1
            continue

        # ── Abstract label ────────────────────────────────────────────────────
        if line.strip() == "## Abstract":
            flowables.append(Spacer(1, 4))
            flowables.append(Paragraph("ABSTRACT", styles["abstract_label"]))
            in_abstract = True
            i += 1
            continue

        if line.startswith("## "):
            text = line[3:].strip()
            flowables.append(Spacer(1, 4))
            flowables.append(HRFlowable(width="100%", thickness=0.5, color=RULE))
            flowables.append(Paragraph(md_inline(text), styles["h1"]))
            i += 1
            continue

        # ── Table ─────────────────────────────────────────────────────────────
        if line.strip().startswith("|"):
            table_lines = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                table_lines.append(lines[i])
                i += 1
            rows = []
            for tl in table_lines:
                cells = [c.strip() for c in tl.strip().strip("|").split("|")]
                if re.match(r'^[-:| ]+$', tl.replace("|", "").strip()):
                    continue  # separator row
                rows.append(cells)
            if rows:
                # Wrap cells in Paragraphs for text wrapping
                para_rows = []
                for r_idx, row in enumerate(rows):
                    style = ParagraphStyle(
                        "TC",
                        fontName="Helvetica-Bold" if r_idx == 0 else "Helvetica",
                        fontSize=9, leading=12,
                        textColor=colors.white if r_idx == 0 else DARK,
                    )
                    para_rows.append([Paragraph(md_inline(c), style) for c in row])
                col_count = max(len(r) for r in para_rows)
                usable = A4[0] - 4 * cm
                col_w = usable / col_count
                t = Table(para_rows, colWidths=[col_w] * col_count)
                t.setStyle(TABLE_STYLE)
                flowables.append(Spacer(1, 6))
                flowables.append(t)
                flowables.append(Spacer(1, 8))
            continue

        # ── Bullet list ───────────────────────────────────────────────────────
        if re.match(r'^[-*] ', line):
            text = md_inline(line[2:].strip())
            flowables.append(Paragraph(f"• {text}", styles["bullet"]))
            i += 1
            continue

        # Sub-bullets (indented)
        if re.match(r'^  [-*] ', line):
            text = md_inline(line[4:].strip())
            style = ParagraphStyle("sub_bullet", parent=styles["bullet"],
                                   leftIndent=28, fontSize=9.5)
            flowables.append(Paragraph(f"– {text}", style))
            i += 1
            continue

        # ── Version / italicised subtitle line ───────────────────────────────
        if line.startswith("### ") and ("v0." in line or "April" in line or "2026" in line):
            flowables.append(Paragraph(escape(line[4:].strip()), styles["version"]))
            i += 1
            continue

        # ── Blank line ────────────────────────────────────────────────────────
        if not line.strip():
            flowables.append(Spacer(1, 4))
            in_abstract = False
            i += 1
            continue

        # ── Paragraph ─────────────────────────────────────────────────────────
        style = styles["abstract"] if in_abstract else styles["body"]
        flowables.append(Paragraph(md_inline(escape(line.strip())), style))
        i += 1

    return flowables


# ── Page template ─────────────────────────────────────────────────────────────

def on_page(canvas, doc):
    canvas.saveState()
    w, h = A4
    # Full dark background
    canvas.setFillColor(BG)
    canvas.rect(0, 0, w, h, fill=1, stroke=0)

    # Top accent strip + rule
    canvas.setFillColor(colors.HexColor("#29104d"))
    canvas.rect(0, h - 0.50 * cm, w, 0.50 * cm, fill=1, stroke=0)
    canvas.setFillColor(ACCENT)
    canvas.rect(0, h - 0.50 * cm, w * 0.34, 0.50 * cm, fill=1, stroke=0)

    # Cover-only geometric logo motif
    if doc.page == 1:
        cx, cy = w / 2, h - 4.2 * cm
        for r, col in [(2.4, colors.HexColor("#1b1244")), (2.0, colors.HexColor("#2a1764")), (1.6, colors.HexColor("#5b21b6")), (1.2, colors.HexColor("#7c3aed"))]:
            canvas.setFillColor(col)
            p = canvas.beginPath()
            for k in range(6):
                ang = (60 * k + 30) * 3.141592653589793 / 180.0
                x = cx + (r * cm) * math.cos(ang)
                y = cy + (r * cm) * math.sin(ang)
                if k == 0:
                    p.moveTo(x, y)
                else:
                    p.lineTo(x, y)
            p.close()
            canvas.drawPath(p, fill=1, stroke=0)
        canvas.setFillColor(colors.HexColor("#f8fafc"))
        canvas.rect(cx - 0.38 * cm, cy - 0.38 * cm, 0.76 * cm, 0.76 * cm, fill=1, stroke=0)

    # Bottom footer
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(MUTED)
    page_num = f"InferenceChain Whitepaper  •  Page {doc.page}"
    canvas.drawCentredString(w / 2, 0.7 * cm, page_num)
    canvas.restoreState()


# ── Build ─────────────────────────────────────────────────────────────────────

def build():
    md = MD_PATH.read_text(encoding="utf-8")
    flowables = parse_md(md)

    doc = SimpleDocTemplate(
        str(OUT_PATH),
        pagesize=A4,
        leftMargin=2 * cm,
        rightMargin=2 * cm,
        topMargin=1.8 * cm,
        bottomMargin=1.6 * cm,
    )
    doc.build(flowables, onFirstPage=on_page, onLaterPages=on_page)
    print(f"Generated: {OUT_PATH}")

    # Copy to frontend locations
    for dest in (PUB_PATH, BUILD_PATH):
        if dest.parent.exists():
            shutil.copy2(OUT_PATH, dest)
            print(f"Copied  -> {dest}")
        else:
            print(f"Skipped   {dest}  (directory missing)")


if __name__ == "__main__":
    build()
