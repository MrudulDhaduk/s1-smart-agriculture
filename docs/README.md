# docs/: design document

The submitted design document is **one BITS-style report PDF built from these files**: `python tools/build_report.py S1_Design_Document.pdf` (needs `pip install markdown pymupdf`, Chrome/Chromium, and internet for the Mermaid diagrams). It adds the cover page, abstract, contents, BITS header/footer and an appendix with `task_divison.txt`.

| File | Content |
|---|---|
| `design-document.md` | Abstract and shared part: team, system overview, microservice architecture diagram, responsibilities, interconnection mechanisms, rationale, requirement-by-requirement evidence |
| `p1-infrastructure-storage.md` | Part A (Person 1): cloud deployment architecture, Terraform, GitOps, storage, Farm/Sensor Registry, Irrigation Controller |
| `p2-events-streaming.md` | Part B (Person 2): Telemetry Ingestion, Kafka, Flink, Farm Analytics, Alert Service |
| `p3-concept-scaling-monitoring.md` | Part C (Person 3): consistent hashing, Partition Manager, Sensor Store, GKE, HPA, k6, observability |

Not in the PDF: `p3-demo-script.md` (live demo walkthrough), `p3-viva-runbook.md` (step-by-step viva runbook), `p3-design-decisions.md` (Person 3's working notes). `images/` holds the figures; `images/make_figures.py` redraws the charts.
