#!/usr/bin/env python3
"""Generate CV PDFs with all available styles"""

import markdown
from weasyprint import HTML
from pathlib import Path

# Read CV markdown files
cv_content = Path('cv.md').read_text()
cv_3_page_content = Path('cv-3-page.md').read_text()

# Convert to HTML
html_body = markdown.markdown(cv_content, extensions=['extra', 'codehilite'])
html_body_3_page = markdown.markdown(cv_3_page_content, extensions=['extra', 'codehilite'])

# 3-page CV with research creative style
styles_3_page = {
    'cv-3-page.pdf': 'style-research-creative.css',
}

# Generate 3-page CV
print("Generating 3-page CV with research creative styling (purple & green)...")
print("=" * 60)
for pdf_name, css_file in styles_3_page.items():
    try:
        # Read CSS content
        css_path = Path(css_file)
        if not css_path.exists():
            print(f"⚠ Skipping {pdf_name}: CSS file {css_file} not found")
            continue

        css_content = css_path.read_text()

        # Create HTML with embedded CSS
        full_html = f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>CV - Vojtěch Špaček (3-Page)</title>
    <style>
{css_content}
    </style>
</head>
<body>
{html_body_3_page}
</body>
</html>'''

        # Generate PDF
        HTML(string=full_html).write_pdf(pdf_name)
        size = Path(pdf_name).stat().st_size / 1024  # KB
        print(f"✓ Generated {pdf_name:<35} ({size:>6.1f} KB)")

    except Exception as e:
        print(f"✗ Failed {pdf_name}: {e}")

print("=" * 60)
print("All PDFs generated successfully!")
print("\n3-Page CV:")
print("  • cv-3-page.pdf                - 3-page CV with research creative styling (purple & green)")
