#!/usr/bin/env python3
"""Build the submission design document: docs/design-document.md followed by each person's part, as one PDF.

    pip install markdown        # once
    python tools/build_design_pdf.py design-document.pdf

Mermaid diagrams are drawn by mermaid.js in headless Chrome (needs internet for the CDN script).
"""
import html
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

import markdown

DOCS = pathlib.Path(__file__).resolve().parent.parent / "docs"
PARTS = [
    ("design-document.md", None),
    ("p1-infrastructure-storage.md", "Part A · "),
    ("p2-events-streaming.md", "Part B · "),
    ("p3-concept-scaling-monitoring.md", "Part C · "),
]
MERMAID = "https://cdn.jsdelivr.net/npm/mermaid@11.4.1/dist/mermaid.min.js"

CSS = """
@page { size: A4; margin: 14mm 13mm 16mm 13mm; }
body { font-family: "DejaVu Sans", "Liberation Sans", Arial, sans-serif; font-size: 9.6pt; line-height: 1.42; color: #1d2329; }
h1 { font-size: 18pt; margin: 0 0 6pt; color: #0b3d2e; border-bottom: 2.5px solid #2e7d5b; padding-bottom: 4pt; }
h2 { font-size: 13pt; margin: 16pt 0 6pt; color: #0b3d2e; border-bottom: 1px solid #c9d6cf; padding-bottom: 2pt; break-after: avoid; }
h3 { font-size: 11pt; margin: 12pt 0 4pt; color: #1f5f45; break-after: avoid; }
p { margin: 4pt 0 6pt; }
hr { border: none; border-top: 1px solid #c9d6cf; margin: 10pt 0; }
blockquote { margin: 6pt 0; padding: 4pt 10pt; border-left: 3px solid #2e7d5b; background: #f2f7f4; }
table { border-collapse: collapse; width: 100%; margin: 6pt 0 10pt; font-size: 8.6pt; }
th, td { border: 1px solid #c3cdc7; padding: 3pt 5pt; vertical-align: top; text-align: left; }
th { background: #e3eee8; }
tr { break-inside: avoid; }
code { font-family: "DejaVu Sans Mono", "Liberation Mono", monospace; font-size: 8.2pt; background: #f1f3f4;
       padding: 0 2px; border-radius: 2px; overflow-wrap: anywhere; }
pre { background: #f6f8f7; border: 1px solid #d6dfda; border-radius: 3px; padding: 6pt 7pt; break-inside: avoid;
      font-size: 7.8pt; line-height: 1.4; white-space: pre-wrap; overflow-wrap: anywhere; }
pre code { background: none; padding: 0; font-size: inherit; white-space: pre-wrap; }
pre.wide, pre.wide code { font-size: 6.1pt; line-height: 1.28; white-space: pre; }
ul, ol { margin: 3pt 0 6pt 16pt; padding-left: 6pt; }
li { margin: 1.5pt 0; }
img { max-width: 100%; max-height: 120mm; display: block; margin: 6pt auto; break-inside: avoid; }
.mermaid { text-align: center; margin: 8pt 0; break-inside: avoid; }
.mermaid svg { max-width: 100%; max-height: 175mm; height: auto; }
.pagebreak { break-before: page; }
.part { break-before: page; }
"""


def render(md_text):
    text = md_text.replace("- [ ] ", "- ☐ ").replace("- [x] ", "- ☑ ")
    body = markdown.markdown(text, extensions=["tables", "fenced_code", "sane_lists"])
    body = re.sub(r'<pre><code class="language-mermaid">(.*?)</code></pre>',
                  lambda m: f'<div class="mermaid">{html.escape(html.unescape(m.group(1)), quote=False)}</div>',
                  body, flags=re.S)

    def size_pre(m):
        inner = re.sub(r"<[^>]+>", "", m.group(0))
        wide = max((len(line) for line in html.unescape(inner).split("\n")), default=0) > 110
        return m.group(0).replace("<pre>", '<pre class="wide">', 1) if wide else m.group(0)

    return re.sub(r"<pre>.*?</pre>", size_pre, body, flags=re.S)


def main():
    out = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "design-document.pdf").resolve()
    sections = []
    for name, prefix in PARTS:
        text = (DOCS / name).read_text(encoding="utf-8")
        if prefix:
            text = re.sub(r"^# ", "# " + prefix, text, count=1)
        sections.append(f'<section class="{"part" if prefix else "intro"}">{render(text)}</section>')

    page = f"""<!doctype html><html><head><meta charset="utf-8"><title>S1 Smart Agriculture: Design Document</title>
<base href="{DOCS.as_uri()}/"><style>{CSS}</style>
<script src="{MERMAID}"></script>
<script>mermaid.initialize({{startOnLoad: true, theme: "neutral", themeVariables: {{fontSize: "15px"}}, flowchart: {{useMaxWidth: true, htmlLabels: true, nodeSpacing: 18, rankSpacing: 32, padding: 6}}}});</script>
</head><body>{''.join(sections)}</body></html>"""

    chrome = next((c for c in ("google-chrome", "chromium", "chromium-browser") if shutil.which(c)), None)
    if not chrome:
        sys.exit("needs google-chrome or chromium on PATH")
    with tempfile.TemporaryDirectory() as tmp:
        src = pathlib.Path(tmp, "design-document.html")
        src.write_text(page, encoding="utf-8")
        subprocess.run([chrome, "--headless=new", f"--user-data-dir={tmp}/profile", "--no-pdf-header-footer",
                        "--allow-file-access-from-files", "--virtual-time-budget=20000",
                        f"--print-to-pdf={out}", src.as_uri()], check=True, capture_output=True)
    print("wrote", out)


if __name__ == "__main__":
    main()
