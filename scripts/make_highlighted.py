#!/usr/bin/env python3
"""Build the change-marked manuscript IEEE Access asks for at resubmission.

The usual way to do this is latexdiff against the submitted source. We do not have that
source: the manuscript directory was never under version control, and the only artifact of
the June submission is its PDF. Rather than fake a sentence-level diff we cannot verify,
this marks change at the granularity we can actually stand behind, and says so on the page.

Two things are produced. Every section that is new or substantially rewritten gets its
heading highlighted and tagged, and a summary of changes is inserted after the abstract
listing what changed and where. A reviewer can then read the marked PDF top to bottom and
know what is new without trusting a diff nobody can reproduce.

    python scripts/make_highlighted.py
"""
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PAPER = ROOT / "paper"

# What changed, by section label, and how. NEW means the section did not exist in the
# submitted version; REWRITTEN means it existed but its content was substantially redone.
CHANGES = {
    "sec:theory": ("NEW", "Formal model, Propositions 1 and 2 with proofs, the arity "
                          "inflation table, and the power analysis"),
    "sec:experiments": ("REWRITTEN", "New data (5029 decisions, three models, genuine "
                                     "replicates, hiring at 24 matched sets), new analysis "
                                     "plan, and eight findings replacing four"),
    "sec:limitations": ("REWRITTEN", "Power, single-provider, unpinned decoding, and the "
                                     "non-determinism result added"),
    "sec:repro": ("REWRITTEN", "Released replicate traces, private-split commitment, "
                               "canary statistic, and the corrected collection-path claim"),
    "app:protocol": ("NEW", "Verbatim prompts, schemas, retry and stopping rules, call "
                            "counts, decoding settings, token budget"),
    "app:data": ("NEW", "Generation rules, strata, thresholds and label validity, and the "
                        "consistency check against published criteria"),
    "app:names": ("NEW", "Full name pools, provenance, perception probe, and the "
                         "unmeasured dimensions"),
    "app:canary": ("NEW", "Detection statistic, threshold, and false-positive analysis"),
}

SUMMARY = r"""
\begin{table*}[t]\centering\small
\caption{Summary of changes in this revision. Section headings marked in the text carry the
same tags. Sentence-level marking was not possible because the submitted \LaTeX{} source was
not retained; change is marked at section granularity and described here instead.}
\label{tab:changes}
\begin{tabular}{lll}\toprule
Reviewer concern & Change & Where \\\midrule
R1: no mathematical support & Two propositions with proofs, inflation table & Sec.~\ref{sec:theory} (NEW) \\
R1: abstract too long, contributions unclear & Abstract rewritten, three contributions named & Abstract \\
R1: reads as a technical report & Estimand, hypothesis and analysis plan precede results & Sec.~\ref{sec:theory}, \ref{sec:experiments} \\
R1: reduce unnecessary content & Procedural detail moved to appendices, repetition cut & Throughout \\
R2.1: evidence too limited & Three models, 5029 decisions, hiring at $n=24$, power analysis & Sec.~\ref{sec:experiments} \\
R2.2: noise floor unconvincing & Replicate-based floor, bootstrap intervals, randomization test & Sec.~\ref{sec:theory}, \ref{sec:experiments} \\
R2.3: demographic intervention unvalidated & Pools, provenance, perception probe, leave-one-name-out & App.~\ref{app:names} (NEW) \\
R2.4: novelty imprecise & Adopted, proposed and validated separated explicitly & Sec.~\ref{sec:related} \\
R2.5: suggested references & All three located, verified, and cited as a cross-domain analogy & Sec.~\ref{sec:related} \\
R2.6: scaffolds under-specified & Verbatim prompts and schemas, plus the C0L length control & App.~\ref{app:protocol} (NEW) \\
R2.7: dataset construction undocumented & Rules, strata, thresholds, published-criteria check & App.~\ref{app:data} (NEW) \\
R2.8: audit trail incomplete & Replicate traces, split commitment, canary statistic, tagged release & Sec.~\ref{sec:repro}, App.~\ref{app:canary} \\
R3.1, R3.5: CFR definition and framing & Pairwise CFR primary, impact ratio in the main table & Sec.~\ref{sec:theory}, \ref{sec:experiments} \\
R3.2, R3.3: C4 semantics & Renamed the information-request channel; no tool is executed & Sec.~\ref{sec:design}, App.~\ref{app:protocol} \\
R3.6: uncertainty for $\Delta_{\text{tool}}$ & Wilson intervals and a within-set permutation test & Sec.~\ref{sec:experiments} \\
R3.7: pin temperature, collect replicates & Replicates collected; non-determinism at $T=0$ reported & Sec.~\ref{sec:limitations} \\
\bottomrule\end{tabular}
\end{table*}

\noindent\colorbox{yellow}{\parbox{0.97\columnwidth}{\textbf{How change is marked.}
Section headings that are new or substantially rewritten are highlighted and tagged
\textsc{new} or \textsc{rewritten}. Table~\ref{tab:changes} maps every reviewer concern to
the change that answers it. The submitted \LaTeX{} source was not retained, so a
sentence-level \texttt{latexdiff} could not be produced; we mark change at the granularity
we can verify rather than present a diff we cannot.}}

"""


def main():
    src = (PAPER / "main.tex").read_text(encoding="utf-8")

    if "\\usepackage{soul}" not in src:
        src = src.replace("\\usepackage[hidelinks]{hyperref}",
                          "\\usepackage[hidelinks]{hyperref}\n"
                          "\\usepackage{soul}\\sethlcolor{yellow}")

    # The marker goes after the label, not inside the heading. soul's \hl is fragile in a
    # moving argument and breaks the running head, which is what the first attempt hit.
    marked = 0
    for label, (kind, why) in CHANGES.items():
        tag = (f"\n\n\\noindent\\colorbox{{yellow}}{{\\textbf{{[{kind}]}} "
               f"{why}.}}\\par\\medskip\n")
        pat = re.compile(r"(\\label\{" + re.escape(label) + r"\})")
        src, n = pat.subn(lambda m: m.group(1) + tag, src, count=1)
        marked += n
        if not n:
            print(f"  warn: no label found for {label}")

    # Drop the summary in right after the keywords block, which is where a reader looks.
    anchor = "\\ifaccess\\titlepgskip=-15pt\\maketitle\\else\\IEEEpeerreviewmaketitle\\fi"
    if anchor in src:
        src = src.replace(anchor, anchor + "\n" + SUMMARY, 1)
    else:
        print("  warn: could not place the summary of changes")

    out = PAPER / "main_highlighted.tex"
    out.write_text(src, encoding="utf-8", newline="\n")
    print(f"wrote {out}  ({marked} section headings marked)")

    for i in range(3):
        r = subprocess.run(["pdflatex", "-interaction=nonstopmode", "-halt-on-error",
                            "main_highlighted.tex"], cwd=PAPER,
                           capture_output=True, text=True)
        if r.returncode != 0 and i == 0:
            tail = [l for l in r.stdout.splitlines() if l.startswith("!")][:5]
            print("  pdflatex errors:", tail or "see main_highlighted.log")
    pdf = PAPER / "main_highlighted.pdf"
    if pdf.exists():
        log = (PAPER / "main_highlighted.log").read_text(encoding="utf-8", errors="ignore")
        pages = re.search(r"Output written .*\((\d+) pages", log)
        print(f"built {pdf.name}: {pages.group(1) if pages else '?'} pages")
    else:
        print("  build failed; see paper/main_highlighted.log")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
