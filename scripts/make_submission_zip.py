#!/usr/bin/env python3
"""Assemble the IEEE Access resubmission package.

The decision letter asks for three uploads: a response-to-reviewers document, the updated
manuscript with changes highlighted as a PDF, and a clean final manuscript as both source
and PDF. This collects exactly those, plus the LaTeX support files a fresh Overleaf project
needs, and writes a short README saying which file goes in which upload slot.

    python scripts/make_submission_zip.py
"""
import hashlib
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PAPER = ROOT / "paper"
OUT = ROOT / "AgentFairBench_IEEE_Access_resubmission.zip"

# (source path, path inside the zip). Order mirrors the portal's upload slots.
FILES = [
    (ROOT / "Review/Response_to_Reviewers_Access-2026-28984.docx",
     "1_response_to_reviewers/Response_to_Reviewers_Access-2026-28984.docx"),
    (PAPER / "main_highlighted.pdf",
     "2_highlighted_manuscript/AgentFairBench_highlighted.pdf"),
    (PAPER / "main.pdf",
     "3_clean_manuscript/AgentFairBench.pdf"),
    (PAPER / "main.tex", "3_clean_manuscript/source/main.tex"),
    (PAPER / "references.bib", "3_clean_manuscript/source/references.bib"),
    (PAPER / "main.bbl", "3_clean_manuscript/source/main.bbl"),
    (PAPER / "ieeeaccess.cls", "3_clean_manuscript/source/ieeeaccess.cls"),
    (PAPER / "spotcolor.sty", "3_clean_manuscript/source/spotcolor.sty"),
    (PAPER / "IEEEtran.bst", "3_clean_manuscript/source/IEEEtran.bst"),
    (PAPER / "logo.png", "3_clean_manuscript/source/logo.png"),
    (PAPER / "bullet.png", "3_clean_manuscript/source/bullet.png"),
    (PAPER / "notaglinelogo.png", "3_clean_manuscript/source/notaglinelogo.png"),
    (PAPER / "figures/f_arity.pdf", "3_clean_manuscript/source/figures/f_arity.pdf"),
    (PAPER / "figures/f_scaffold.pdf", "3_clean_manuscript/source/figures/f_scaffold.pdf"),
    (ROOT / "Review/SUBMISSION_CHECKLIST.md", "SUBMISSION_CHECKLIST.md"),
]

# Fonts the IEEE Access class needs; missing ones are reported, not silently dropped.
FONT_GLOBS = ["t1-*.pfb", "t1-*.tfm", "t1-*.map", "t1formata.fd", "t1giovannistd.fd",
              "t1helvetica.fd", "t1times.fd"]

README = """AgentFairBench - IEEE Access resubmission package
Manuscript ID: Access-2026-28984

Upload these three, in the slots the decision letter names.

1. Author's Response Files
   1_response_to_reviewers/Response_to_Reviewers_Access-2026-28984.docx
   Every reviewer concern, our response, and the action taken.

2. Highlighted PDF
   2_highlighted_manuscript/AgentFairBench_highlighted.pdf
   Sections that are new or substantially rewritten are tagged and highlighted, and a
   summary table after the abstract maps each reviewer concern to the change answering it.
   One caveat stated on the page itself: the LaTeX source of the submitted version was not
   retained, so change is marked at section granularity rather than by sentence-level diff.

3. Main Manuscript
   3_clean_manuscript/AgentFairBench.pdf          the clean PDF
   3_clean_manuscript/source/                     the LaTeX source, compiles as-is

No byline change form is needed. The author list and corresponding author match the
submitted version exactly: Triveni Morla, Rohith Reddy Bellibaltu, Manpreet Singh, and
Manmeet Singh Kapoor, corresponding author Manmeet Singh Kapoor.

Read SUBMISSION_CHECKLIST.md before uploading.

One thing to raise in the cover note. The finding changed. The submitted version reported a
null; expanding the hiring domain to 24 matched sets, which is what Reviewer 2 asked for,
produced three cells whose group ordering survives multiplicity correction. Disparity
magnitude still sits at the noise floor everywhere. The response letter opens with this
rather than burying it.
"""


def main():
    missing = [str(s.relative_to(ROOT)) for s, _ in FILES if not s.exists()]
    if missing:
        print("MISSING, package not written:")
        for m in missing:
            print("  -", m)
        return 1

    fonts = []
    for g in FONT_GLOBS:
        fonts.extend(sorted(PAPER.glob(g)))
    if not fonts:
        print("  warn: no IEEE Access font files found; a fresh Overleaf project may not "
              "reproduce the official look")

    OUT.unlink(missing_ok=True)
    with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("README.txt", README)
        for src, arc in FILES:
            z.write(src, arc)
        for f in fonts:
            z.write(f, f"3_clean_manuscript/source/{f.name}")

    digest = hashlib.sha256(OUT.read_bytes()).hexdigest()[:16]
    with zipfile.ZipFile(OUT) as z:
        names = z.namelist()
    print(f"wrote {OUT.name}")
    print(f"  {len(names)} entries, {OUT.stat().st_size/1e6:.1f} MB, sha256 {digest}")
    for n in sorted(names):
        if "/source/" not in n or n.endswith((".tex", ".bib", ".bbl")):
            print("   ", n)
    print(f"    (plus {sum(1 for n in names if '/source/' in n)} source and font files)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
