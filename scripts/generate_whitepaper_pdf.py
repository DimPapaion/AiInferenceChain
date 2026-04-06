#!/usr/bin/env python3
"""Generate a styled PDF from WHITEPAPER.md using reportlab.

This generator preserves markdown content (including tables) and uses
section-oriented pagination to match long-form whitepaper layout.
"""

import re
from pathlib import Path
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    PageBreak,
    Table,
    TableStyle,
    Preformatted,
    HRFlowable,
)
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.lib import colors

PAGE_WIDTH, PAGE_HEIGHT = A4
THEME = {
    'ink': colors.HexColor('#0F172A'),
    'muted': colors.HexColor('#334155'),
    'accent': colors.HexColor('#0EA5E9'),
    'accent_soft': colors.HexColor('#E0F2FE'),
    'line': colors.HexColor('#CBD5E1'),
    'bg': colors.HexColor('#F8FAFC'),
}

def read_markdown(filepath):
    """Read and parse markdown file"""
    with open(filepath, 'r', encoding='utf-8') as f:
        return f.read()

def _inline_format(text):
    """Convert a subset of markdown inline syntax to reportlab tags."""
    text = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', text)
    text = re.sub(r'\*(.*?)\*', r'<i>\1</i>', text)
    text = re.sub(r'`(.*?)`', r'<font face="Courier">\1</font>', text)
    return text


def _is_table_delimiter(line):
    s = line.strip()
    return s.startswith("|") and re.fullmatch(r"\|?\s*:?-+:?\s*(\|\s*:?-+:?\s*)+\|?", s) is not None


def _parse_table(lines):
    rows = []
    for raw in lines:
        s = raw.strip()
        if not s.startswith("|"):
            continue
        parts = [c.strip() for c in s.strip("|").split("|")]
        rows.append(parts)
    return rows


def parse_markdown_to_elements(md_text, styles, content_width):
    """Convert markdown to reportlab flowables while preserving detail."""
    elements = []
    lines = md_text.split('\n')
    i = 0
    section_count = 0
    
    while i < len(lines):
        line = lines[i]
        
        # Preserve empty lines to avoid visual compression.
        if not line.strip():
            elements.append(Spacer(1, 0.06 * inch))
            i += 1
            continue
        
        # H1 - Title
        if line.startswith('# '):
            title = line[2:].strip()
            elements.append(Paragraph(title, styles['Heading1']))
            elements.append(Paragraph('Decentralized AI Inference Consensus', styles['CoverSubtitle']))
            elements.append(Spacer(1, 0.18 * inch))
            elements.append(HRFlowable(width="100%", thickness=1.2, color=THEME['accent']))
            elements.append(Spacer(1, 0.12 * inch))
            i += 1
        
        # H2 - Section
        elif line.startswith('## '):
            section = line[3:].strip()
            # Start numbered major sections on a new page (except first section).
            if re.match(r"^\d+\.", section):
                section_count += 1
                if section_count > 1:
                    elements.append(PageBreak())
            elements.append(Spacer(1, 0.12 * inch))
            section_cell = Table(
                [[Paragraph(section, styles['SectionTitle'])]],
                colWidths=[content_width],
            )
            section_cell.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, -1), THEME['accent_soft']),
                ('BOX', (0, 0), (-1, -1), 0.8, THEME['accent']),
                ('LEFTPADDING', (0, 0), (-1, -1), 8),
                ('RIGHTPADDING', (0, 0), (-1, -1), 8),
                ('TOPPADDING', (0, 0), (-1, -1), 6),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ]))
            elements.append(section_cell)
            elements.append(Spacer(1, 0.08 * inch))
            i += 1
        
        # H3 - Subsection
        elif line.startswith('### '):
            subsection = line[4:].strip()
            elements.append(Paragraph(subsection, styles['Heading3']))
            elements.append(Spacer(1, 0.06 * inch))
            i += 1
        
        # Code blocks
        elif line.startswith('```'):
            code_lines = []
            i += 1
            while i < len(lines) and not lines[i].startswith('```'):
                code_lines.append(lines[i])
                i += 1
            code_text = '\n'.join(code_lines).strip()
            if code_text:
                elements.append(Preformatted(code_text, styles['WPCode']))
                elements.append(Spacer(1, 0.08 * inch))
            i += 1  # Skip closing ```
        
        # Bullet points
        elif line.startswith('- '):
            bullet_text = line[2:].strip()
            bullet_para = Paragraph('• ' + _inline_format(bullet_text), styles['WPBody'])
            elements.append(bullet_para)
            elements.append(Spacer(1, 0.03 * inch))
            i += 1
        
        # Numbered lists
        elif re.match(r'^\d+\. ', line):
            match = re.match(r'^(\d+)\. (.*)', line)
            if match:
                num, text = match.groups()
                elements.append(Paragraph(f'<b>{num}.</b> {_inline_format(text)}', styles['WPBody']))
                elements.append(Spacer(1, 0.03 * inch))
            i += 1
        
        # Horizontal rule
        elif re.fullmatch(r"\s*-{3,}\s*", line):
            elements.append(HRFlowable(width="100%", thickness=0.8, color=colors.HexColor('#B8C2CC')))
            elements.append(Spacer(1, 0.08 * inch))
            i += 1

        # Markdown tables
        elif line.strip().startswith('|') and i + 1 < len(lines) and _is_table_delimiter(lines[i + 1]):
            table_lines = [line]
            i += 1  # delimiter
            while i < len(lines) and lines[i].strip().startswith('|'):
                table_lines.append(lines[i])
                i += 1
            rows = _parse_table(table_lines)
            if rows:
                max_cols = max(len(r) for r in rows)
                rows = [r + [''] * (max_cols - len(r)) for r in rows]
                t = Table(rows, repeatRows=1)
                t.setStyle(TableStyle([
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                    ('BACKGROUND', (0, 0), (-1, 0), THEME['ink']),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                    ('FONTSIZE', (0, 0), (-1, -1), 9.5),
                    ('GRID', (0, 0), (-1, -1), 0.4, THEME['line']),
                    ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F8FAFC')]),
                    ('LEFTPADDING', (0, 0), (-1, -1), 5),
                    ('RIGHTPADDING', (0, 0), (-1, -1), 5),
                    ('TOPPADDING', (0, 0), (-1, -1), 4),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
                    ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ]))
                elements.append(t)
                elements.append(Spacer(1, 0.08 * inch))
        
        # Bold/italic formatting in regular paragraphs
        elif line.strip():
            text = _inline_format(line.strip())
            elements.append(Paragraph(text, styles['WPBody']))
            elements.append(Spacer(1, 0.04 * inch))
            i += 1
        
        else:
            i += 1
    
    return elements

def create_pdf():
    """Generate PDF from WHITEPAPER.md"""
    md_path = Path(__file__).parent.parent / 'WHITEPAPER.md'
    pdf_path = Path(__file__).parent.parent / 'InferenceChain_Whitepaper.pdf'
    
    if not md_path.exists():
        print(f"Error: {md_path} not found")
        return False
    
    print(f"Reading {md_path}...")
    md_text = read_markdown(md_path)
    
    # Create PDF document
    doc = SimpleDocTemplate(
        str(pdf_path),
        pagesize=A4,
        rightMargin=0.72 * inch,
        leftMargin=0.72 * inch,
        topMargin=0.72 * inch,
        bottomMargin=0.72 * inch,
        title='InferenceChain Whitepaper v0.5+'
    )
    
    # Create custom styles
    styles = getSampleStyleSheet()
    
    # Override heading styles for professional appearance
    styles['Heading1'].fontSize = 22
    styles['Heading1'].textColor = THEME['ink']
    styles['Heading1'].spaceAfter = 0.16 * inch
    styles['Heading1'].alignment = TA_CENTER
    
    styles['Heading3'].fontSize = 12
    styles['Heading3'].textColor = THEME['muted']
    styles['Heading3'].spaceAfter = 0.05 * inch

    styles.add(ParagraphStyle(
        name='CoverSubtitle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=11,
        leading=14,
        alignment=TA_CENTER,
        textColor=THEME['muted'],
    ))

    styles.add(ParagraphStyle(
        name='SectionTitle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=12.5,
        leading=14,
        textColor=THEME['ink'],
        alignment=TA_LEFT,
    ))
    
    styles.add(ParagraphStyle(
        name='WPBody',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=10.8,
        leading=15.2,
        alignment=TA_JUSTIFY,
        textColor=THEME['ink'],
    ))

    styles.add(ParagraphStyle(
        name='WPCode',
        parent=styles['Normal'],
        fontName='Courier',
        fontSize=9.5,
        leading=12,
        textColor=THEME['ink'],
        backColor=THEME['bg'],
        leftIndent=8,
        rightIndent=8,
    ))

    def draw_page_chrome(canv, doc_obj):
        canv.saveState()
        # Top accent bar
        canv.setFillColor(THEME['ink'])
        canv.rect(0, PAGE_HEIGHT - 22, PAGE_WIDTH, 22, stroke=0, fill=1)
        canv.setFillColor(THEME['accent'])
        canv.rect(0, PAGE_HEIGHT - 22, PAGE_WIDTH * 0.28, 22, stroke=0, fill=1)

        # Subtle corner accent on cover page only
        if canv.getPageNumber() == 1:
            canv.setFillColor(colors.HexColor('#E6F7FF'))
            canv.circle(PAGE_WIDTH - 40, PAGE_HEIGHT - 95, 72, stroke=0, fill=1)
            canv.setFillColor(colors.HexColor('#BAE6FD'))
            canv.circle(PAGE_WIDTH - 24, PAGE_HEIGHT - 82, 36, stroke=0, fill=1)

        # Footer line + page number
        canv.setStrokeColor(THEME['line'])
        canv.setLineWidth(0.7)
        canv.line(doc_obj.leftMargin, 26, PAGE_WIDTH - doc_obj.rightMargin, 26)
        canv.setFillColor(THEME['muted'])
        canv.setFont('Helvetica', 8.5)
        canv.drawString(doc_obj.leftMargin, 14, 'InferenceChain Whitepaper v0.5')
        canv.drawRightString(PAGE_WIDTH - doc_obj.rightMargin, 14, f'Page {canv.getPageNumber()}')
        canv.restoreState()
    
    # Parse markdown and create elements
    print("Converting markdown to PDF elements...")
    elements = parse_markdown_to_elements(md_text, styles, doc.width)
    
    # Build PDF
    print(f"Writing PDF to {pdf_path}...")
    doc.build(elements, onFirstPage=draw_page_chrome, onLaterPages=draw_page_chrome)
    print(f"✓ PDF generated: {pdf_path}")
    return True

if __name__ == '__main__':
    create_pdf()
