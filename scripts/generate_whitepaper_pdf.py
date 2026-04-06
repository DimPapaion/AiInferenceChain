#!/usr/bin/env python3
"""
Generate professional PDF from WHITEPAPER.md using reportlab
"""

import re
from pathlib import Path
from reportlab.lib.pagesizes import letter, A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak, Table, TableStyle, Preformatted
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_JUSTIFY, TA_RIGHT
from reportlab.lib import colors
from reportlab.pdfgen import canvas

def read_markdown(filepath):
    """Read and parse markdown file"""
    with open(filepath, 'r', encoding='utf-8') as f:
        return f.read()

def parse_markdown_to_elements(md_text, styles):
    """Convert markdown to reportlab elements"""
    elements = []
    lines = md_text.split('\n')
    i = 0
    
    while i < len(lines):
        line = lines[i]
        
        # Skip empty lines between sections
        if not line.strip():
            i += 1
            continue
        
        # H1 - Title
        if line.startswith('# '):
            title = line[2:].strip()
            elements.append(Paragraph(title, styles['Heading1']))
            elements.append(Spacer(1, 0.2*inch))
            i += 1
        
        # H2 - Section
        elif line.startswith('## '):
            section = line[3:].strip()
            elements.append(Spacer(1, 0.15*inch))
            elements.append(Paragraph(section, styles['Heading2']))
            elements.append(Spacer(1, 0.1*inch))
            i += 1
        
        # H3 - Subsection
        elif line.startswith('### '):
            subsection = line[4:].strip()
            elements.append(Paragraph(subsection, styles['Heading3']))
            elements.append(Spacer(1, 0.08*inch))
            i += 1
        
        # Code blocks
        elif line.startswith('```'):
            code_lines = []
            i += 1
            while i < len(lines) and not lines[i].startswith('```'):
                code_lines.append(lines[i])
                i += 1
            code_text = '\n'.join(code_lines).strip()
            elements.append(Preformatted(code_text, styles['Normal']))
            elements.append(Spacer(1, 0.1*inch))
            i += 1  # Skip closing ```
        
        # Bullet points
        elif line.startswith('- '):
            bullet_text = line[2:].strip()
            bullet_para = Paragraph('• ' + bullet_text, styles['Normal'])
            elements.append(bullet_para)
            i += 1
        
        # Numbered lists
        elif re.match(r'^\d+\. ', line):
            match = re.match(r'^(\d+)\. (.*)', line)
            if match:
                num, text = match.groups()
                elements.append(Paragraph(f'<b>{num}.</b> {text}', styles['Normal']))
            i += 1
        
        # Tables (simplified - just text)
        elif '|' in line:
            # Skip table lines for now (complex parsing)
            i += 1
        
        # Bold/italic formatting in regular paragraphs
        elif line.strip():
            # Convert markdown formatting to reportlab tags
            text = line.strip()
            text = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', text)
            text = re.sub(r'\*(.*?)\*', r'<i>\1</i>', text)
            text = re.sub(r'`(.*?)`', r'<font face="Courier"><b>\1</b></font>', text)
            elements.append(Paragraph(text, styles['Normal']))
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
        pagesize=letter,
        rightMargin=0.75*inch,
        leftMargin=0.75*inch,
        topMargin=0.75*inch,
        bottomMargin=0.75*inch,
        title='InferenceChain Whitepaper v0.5+'
    )
    
    # Create custom styles
    styles = getSampleStyleSheet()
    
    # Override heading styles for professional appearance
    styles['Heading1'].fontSize = 24
    styles['Heading1'].textColor = colors.HexColor('#1a1a1a')
    styles['Heading1'].spaceAfter = 0.2*inch
    styles['Heading1'].alignment = TA_CENTER
    
    styles['Heading2'].fontSize = 14
    styles['Heading2'].textColor = colors.HexColor('#2c3e50')
    styles['Heading2'].spaceAfter = 0.1*inch
    styles['Heading2'].borderColor = colors.HexColor('#3498db')
    styles['Heading2'].borderWidth = 0
    
    styles['Heading3'].fontSize = 12
    styles['Heading3'].textColor = colors.HexColor('#34495e')
    styles['Heading3'].spaceAfter = 0.08*inch
    
    styles['Normal'].fontSize = 11
    styles['Normal'].leading = 14
    styles['Normal'].alignment = TA_JUSTIFY
    
    # Parse markdown and create elements
    print("Converting markdown to PDF elements...")
    elements = parse_markdown_to_elements(md_text, styles)
    
    # Build PDF
    print(f"Writing PDF to {pdf_path}...")
    doc.build(elements)
    print(f"✓ PDF generated: {pdf_path}")
    return True

if __name__ == '__main__':
    create_pdf()
