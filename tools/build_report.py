#!/usr/bin/env python3
"""Build the submission design document as a BITS-style report PDF.

    pip install markdown pymupdf      # once
    python tools/build_report.py S1_Design_Document.pdf

Sources: docs/design-document.md (abstract + shared chapters 1-7), then docs/p1-, p2-, p3- as
Parts A, B and C, then an appendix with task_divison.txt. Markdown -> HTML -> headless Chrome
(Mermaid diagrams drawn by mermaid.js, so internet is needed) -> PyMuPDF stamps the BITS header
and footer with page numbers on every page after the cover.
"""
import html
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

import markdown
import pymupdf

ROOT = pathlib.Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
CREST = DOCS / "images" / "bits_crest.png"
MERMAID = "https://cdn.jsdelivr.net/npm/mermaid@11.4.1/dist/mermaid.min.js"
TITLE = "S1 Smart Agriculture — Design Document"
FOOTER_LEFT = "S1 Smart Agriculture  ·  Cloud Computing (CS/SS G527)"
def _font(*candidates):
    """First font file that exists: Times New Roman, else its metric-compatible Liberation Serif."""
    return next((f for f in candidates if pathlib.Path(f).exists()), candidates[-1])


FONT_REG = _font("/usr/share/fonts/truetype/msttcorefonts/Times_New_Roman.ttf",
                 "/usr/share/fonts/truetype/liberation/LiberationSerif-Regular.ttf")
FONT_BOLD = _font("/usr/share/fonts/truetype/msttcorefonts/Times_New_Roman_Bold.ttf",
                  "/usr/share/fonts/truetype/liberation/LiberationSerif-Bold.ttf")
NAVY = (0x10 / 255, 0x11 / 255, 0x41 / 255)
MUTED = (0x59 / 255, 0x59 / 255, 0x59 / 255)
STRIPE = [(0xFC / 255, 0xB0 / 255, 0x17 / 255), (0x76 / 255, 0xC2 / 255, 0xE5 / 255), (1, 0, 0)]

PARTS = [
    ("A", "p1-infrastructure-storage.md"),
    ("B", "p2-events-streaming.md"),
    ("C", "p3-concept-scaling-monitoring.md"),
]
TEAM = [
    ("Saravanasudharsan S", "2026H1030068P"),
    ("Pranav Harresh Vishwanathan", "2026H1030074P"),
    ("Dhaduk Mrudul", "2026H1030069P"),
]

CSS = """
@page { size: Letter; margin: 0.98in 0.8in 0.9in 0.8in; }
html { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
body { font-family: "Times New Roman", "Liberation Serif", Times, serif; font-size: 11pt; line-height: 1.4;
       color: #1f1f1f; margin: 0; }
h1 { font-size: 19pt; color: #101141; margin: 0 0 4pt; line-height: 1.2; break-before: page; }
h1 + p { color: #595959; font-size: 9.6pt; }
h2 { font-size: 13.5pt; color: #101141; margin: 17pt 0 6pt; padding-bottom: 3pt; border-bottom: 2pt solid;
     border-image: linear-gradient(to right, #FCB017 0 33.3%, #76C2E5 33.3% 66.6%, #FF0000 66.6% 100%) 1;
     break-after: avoid; }
h3 { font-size: 11.3pt; color: #101141; margin: 13pt 0 4pt; break-after: avoid; }
h4 { font-size: 10.5pt; color: #101141; margin: 10pt 0 3pt; break-after: avoid; }
p { margin: 0 0 7pt; }
ul, ol { margin: 0 0 8pt; padding-left: 18pt; }
li { margin: 0 0 3pt; }
strong { color: #101141; }
a { color: #0070C0; text-decoration: none; }
code { font-family: "DejaVu Sans Mono", Consolas, monospace; font-size: 8.5pt; background: #EEF1F8;
       padding: 0.5pt 2.5pt; border-radius: 2pt; }
pre { background: #F3F5FA; border-left: 3pt solid #76C2E5; padding: 7pt 10pt; margin: 4pt 0 10pt;
      white-space: pre-wrap; word-break: break-word; break-inside: avoid; border-radius: 2pt; }
pre code { background: none; padding: 0; font-size: 8.2pt; line-height: 1.45; }
pre.wide code { font-size: 6.3pt; white-space: pre; }
table { border-collapse: collapse; width: 100%; font-size: 9pt; margin: 6pt 0 12pt; }
thead { display: table-header-group; }
th { background: #101141; color: #fff; text-align: left; padding: 5pt 7pt; font-weight: 600; }
td { padding: 5pt 7pt; border-bottom: 1px solid #D5DAE6; vertical-align: top; }
tr { break-inside: avoid; }
tbody tr:nth-child(even) td { background: #F6F7FB; }
td code, th code { font-size: 8pt; overflow-wrap: anywhere; }
th code { background: none; color: #fff; }
blockquote { margin: 6pt 0 10pt; padding: 6pt 10pt; background: #FFF8E6; border-left: 3pt solid #FCB017; }
blockquote p { margin: 0; }
hr { display: none; }
img { max-width: 100%; max-height: 4.6in; display: block; margin: 8pt auto; break-inside: avoid; }
.mermaid { text-align: center; margin: 8pt 0 12pt; break-inside: avoid; }
.mermaid svg { max-width: 100%; max-height: 6.4in; height: auto; }
.pagebreak { break-after: page; }

.cover { text-align: center; padding-top: 0.55in; break-after: page; }
.cover img { width: 1.3in; margin: 0 auto; }
.cover .inst { font-size: 13pt; color: #101141; font-weight: 600; margin: 10pt 0 0; }
.cover .campus { font-size: 10pt; color: #595959; margin: 2pt 0 46pt; }
.cover .title { font-size: 30pt; color: #101141; font-weight: 700; margin: 0 0 8pt; }
.cover .subtitle { font-size: 15pt; color: #8064A2; margin: 0 0 6pt; }
.cover .kind { font-size: 12pt; color: #595959; margin: 0 0 46pt; }
.cover table { width: 66%; margin: 0 auto 44pt; font-size: 11pt; }
.cover td { border: none; padding: 3pt 6pt; background: none !important; }
.cover td:first-child { text-align: right; font-weight: 700; color: #101141; }
.cover td:last-child { text-align: left; color: #333; }
.cover .meta { font-size: 10.5pt; color: #595959; line-height: 1.65; }
.front h2 { margin-top: 0; }
.abstract { font-size: 10.8pt; line-height: 1.55; text-align: justify; }
.toc { margin-top: 18pt; }
.toc ol { list-style: none; padding-left: 0; margin: 0; }
.toc li { margin: 0 0 4pt; font-size: 10.5pt; }
.toc li.part { margin-top: 9pt; font-weight: 700; color: #101141; }
.toc li.sub { padding-left: 18pt; font-size: 9.6pt; color: #333; margin-bottom: 2pt; }
.partnote { color: #595959; font-size: 9.6pt; margin: -2pt 0 10pt; }
"""


def md_to_html(text):
    text = text.replace("- [ ] ", "- ☐ ").replace("- [x] ", "- ☑ ")
    body = markdown.markdown(text, extensions=["tables", "fenced_code", "sane_lists"])
    body = re.sub(r'<pre><code class="language-mermaid">(.*?)</code></pre>',
                  lambda m: f'<div class="mermaid">{html.escape(html.unescape(m.group(1)), quote=False)}</div>',
                  body, flags=re.S)

    def pre(m):
        inner = html.unescape(re.sub(r"<[^>]+>", "", m.group(0)))
        wide = max((len(line) for line in inner.split("\n")), default=0) > 100
        long_block = inner.count("\n") > 18
        attrs = (' class="wide"' if wide else "") + (' style="break-inside:auto"' if long_block else "")
        return m.group(0).replace("<pre>", f"<pre{attrs}>", 1)

    body = re.sub(r"<pre>.*?</pre>", pre, body, flags=re.S)
    # long inline paths wrap at "/" instead of mid-word
    return re.sub(r"<code>([^<]*)</code>", lambda m: "<code>" + m.group(1).replace("/", "/<wbr>") + "</code>", body)


def headings(text, level):
    """Headings of one level, ignoring code blocks."""
    text = re.sub(r"```.*?```", "", text, flags=re.S)
    return [h.strip() for h in re.findall(rf"^{'#' * level} (.+)$", text, re.M)]


def build_html():
    shared = (DOCS / "design-document.md").read_text(encoding="utf-8")
    abstract = re.search(r"^## Abstract\n(.*?)\n---", shared, re.S | re.M).group(1).strip()
    shared_body = shared[shared.index("## 1. System overview"):]

    toc = ['<li class="part">System Design (shared)</li>'] + [f'<li class="sub">{h}</li>' for h in headings(shared_body, 2)]
    parts_html = []
    for letter, name in PARTS:
        text = (DOCS / name).read_text(encoding="utf-8")
        first = re.search(r"^# (.+)$", text, re.M)
        person, _, topic = first.group(1).partition(": ")
        title = f"Part {letter} — {topic}"
        text = text[:first.start()] + f"# {title}\n\n<p class='partnote'>{person}</p>" + text[first.end():]
        toc.append(f'<li class="part">{title}</li>')
        toc += [f'<li class="sub">{h}</li>' for h in headings(text, 2)]
        parts_html.append(md_to_html(text))

    division = (ROOT / "task_divison.txt").read_text(encoding="utf-8")
    appendix = ("# Appendix — Task division and deliverables\n\n"
                "Contents of `task_divison.txt` in the repository root:\n\n```\n" + division.strip() + "\n```\n\n"
                "| Deliverable | Where |\n|---|---|\n"
                "| Design document | This report (sources in `docs/`, built by `tools/build_report.py`) |\n"
                "| Microservice code | `services/` (one folder per service), shared contracts in `contracts/` |\n"
                "| Infrastructure as code | `infra/` (Terraform stacks; runbook `infra/README.md`) |\n"
                "| Kubernetes manifests and GitOps | `k8s/base`, `k8s/local`, `k8s/gke`; ArgoCD installed by `infra/platform` |\n"
                "| Load test and observability | `loadtest/`, `observability/` |\n"
                "| Repository | https://github.com/MrudulDhaduk/s1-smart-agriculture |\n")
    toc.append('<li class="part">Appendix — Task division and deliverables</li>')

    team = "".join(f"<tr><td>{n}</td><td>{i}</td></tr>" for n, i in TEAM)
    cover = f"""<div class="cover">
<img src="{CREST.as_uri()}" alt="BITS Pilani crest">
<p class="inst">Birla Institute of Technology and Science, Pilani</p>
<p class="campus">Pilani Campus</p>
<p class="title">S1 Smart Agriculture</p>
<p class="subtitle">Sensor-Based Irrigation Across Multiple Farms</p>
<p class="kind">Design Document — Cloud Computing Group Assignment</p>
<table>{team}</table>
<p class="meta">Cloud Computing (CS/SS G527)<br>First Semester 2025–26<br>
Scenario S1 — Data partitioning using consistent hashing<br>November 2026<br>
github.com/MrudulDhaduk/s1-smart-agriculture</p>
</div>"""
    front = (f'<div class="front"><h2>Abstract</h2><div class="abstract">{md_to_html(abstract)}</div>'
             f'<h2 class="toc-title">Contents</h2><div class="toc"><ol>{"".join(toc)}</ol></div></div>')
    body = (cover + front + md_to_html("# System Design\n\n<p class='partnote'>Shared by all three members</p>\n\n" + shared_body) + "".join(parts_html)
            + md_to_html(appendix))
    return f"""<!doctype html><html><head><meta charset="utf-8"><title>{TITLE}</title>
<base href="{DOCS.as_uri()}/"><style>{CSS}</style>
<script src="{MERMAID}"></script>
<script>mermaid.initialize({{startOnLoad: true, theme: "neutral",
  themeVariables: {{fontFamily: "Times New Roman, Liberation Serif, serif", fontSize: "16px"}},
  flowchart: {{useMaxWidth: true, htmlLabels: true, nodeSpacing: 18, rankSpacing: 32, padding: 6}}}});</script>
</head><body>{body}</body></html>"""


def print_pdf(page_html, out):
    chrome = next((c for c in ("google-chrome", "chromium", "chromium-browser") if shutil.which(c)), None)
    if not chrome:
        sys.exit("needs google-chrome or chromium on PATH")
    with tempfile.TemporaryDirectory() as tmp:
        src = pathlib.Path(tmp, "report.html")
        src.write_text(page_html, encoding="utf-8")
        subprocess.run([chrome, "--headless=new", "--disable-gpu", f"--user-data-dir={tmp}/profile",
                        "--no-pdf-header-footer", "--allow-file-access-from-files", "--virtual-time-budget=25000",
                        f"--print-to-pdf={out}", src.as_uri()], check=True, capture_output=True)


def stripe(page, x0, x1, y, h):
    seg = (x1 - x0) / 3
    for i, c in enumerate(STRIPE):
        page.draw_rect(pymupdf.Rect(x0 + i * seg, y, x0 + (i + 1) * seg, y + h), color=None, fill=c)


def stamp(out):
    """BITS header and footer on every page except the cover; numbering starts after the cover."""
    doc = pymupdf.open(out)
    reg, bold = pymupdf.Font(fontfile=FONT_REG), pymupdf.Font(fontfile=FONT_BOLD)
    total = len(doc) - 1
    for i, page in enumerate(doc):
        if i == 0:
            continue
        left, right = 57.6, page.rect.width - 57.6
        page.insert_image(pymupdf.Rect(left, 20, left + 31, 50), filename=str(CREST))
        page.insert_text((left + 38, 33), "BITS", fontsize=10, fontfile=FONT_BOLD, fontname="NSB", color=NAVY)
        page.insert_text((left + 38 + bold.text_length("BITS ", 10), 33), "Pilani", fontsize=10,
                         fontfile=FONT_REG, fontname="NSR", color=NAVY)
        page.insert_text((left + 38, 45), "Pilani Campus", fontsize=7.5, fontfile=FONT_REG, fontname="NSR",
                         color=MUTED)
        page.insert_text((right - reg.text_length(TITLE, 8.5), 42), TITLE, fontsize=8.5, fontfile=FONT_REG,
                         fontname="NSR", color=MUTED)
        stripe(page, left, right, 53, 1.8)
        fy = page.rect.height - 44
        stripe(page, left, right, fy, 1.2)
        page.insert_text((left, fy + 14), FOOTER_LEFT, fontsize=7.8, fontfile=FONT_REG, fontname="NSR",
                         color=MUTED)
        label = f"Page {i} of {total}"
        page.insert_text((right - reg.text_length(label, 7.8), fy + 14), label, fontsize=7.8, fontfile=FONT_REG,
                          fontname="NSR", color=MUTED)
    doc.set_metadata({"title": TITLE, "author": "Saravanasudharsan S, Pranav Harresh Vishwanathan, Dhaduk Mrudul",
                      "subject": "CS/SS G527 Cloud Computing group assignment, scenario S1", "keywords": "",
                      "creator": "tools/build_report.py", "producer": "Chromium / PyMuPDF"})
    doc.subset_fonts()
    tmp_out = out.with_suffix(".stamped.pdf")
    doc.save(tmp_out, garbage=4, deflate=True)
    doc.close()
    tmp_out.replace(out)


def main():
    out = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "S1_Design_Document.pdf").resolve()
    print_pdf(build_html(), out)
    stamp(out)
    print(f"wrote {out} ({len(pymupdf.open(out))} pages)")


if __name__ == "__main__":
    main()
