---
name: synthesize-report
description: Synthesize a literature review report from per-snippet summaries and a paper catalogue. Reads all_summaries.json and paper_catalogue.json from a traversal output directory. Produces a markdown report with inline quotes and DOI-hyperlinked references.
---

# Synthesize Report

You produce a structured literature review report from the outputs of a citation traversal. You read per-snippet summaries (with quotes) and a paper catalogue, then synthesize a coherent report with proper references.

**You work only from summaries and quotes — never from raw snippet text.**

## Input

`$ARGUMENTS` contains:
- A research question (free text)
- `--input-dir path` (optional, default `traversal_output/`) — directory containing traversal outputs

You expect these files in the input directory:
- `all_summaries.json` — array of per-snippet summaries with quotes
- `paper_catalogue.json` — metadata for all papers (from `get_paper_batch`)
- `seeds.json` (optional) — original seed papers and search strategy

## Procedure

### 1. Load data

Read `all_summaries.json` and `paper_catalogue.json` from the input directory. Optionally read `seeds.json` for context on how seeds were discovered.

### 2. Build reference list

From `paper_catalogue.json`, build a numbered reference list. Sort by year (newest first), then alphabetically by first author.

For each paper, construct:
- `[N]` — reference number
- Authors (Year). Title. *Venue*.
- Hyperlinked DOI: `[DOI](https://doi.org/{doi})` if available
- Corpus ID for traceability

Map each `corpus_id` to its reference number for inline citations.

### 3. Group and organize summaries

Group the per-snippet summaries by topic/theme, not by depth level. The evidence chain (which depth a snippet came from) is metadata, not the organizing principle.

Identify major themes from the summaries. For example, for a salivary gland query:
- Cell types and their locations
- Markers and gene expression
- Functions and secretory mechanisms
- Development and differentiation

### 4. Write report

Produce a markdown report following this structure:

```markdown
# {Report Title}

> **Query:** {research question}
> **Seeds:** {N} papers ({strategies used})
> **Evidence:** {M} snippets across {D} traversal depths from {P} unique papers

## {Theme 1}

{Synthesized narrative for this theme. Every factual claim is supported
by an inline quote and reference.}

"{exact quote from snippet}" [N]

{More narrative...}

"{another exact quote}" [M]

## {Theme 2}

...

## Gaps and Limitations

{What the evidence didn't cover. Which papers had no indexed body text.
Which aspects of the query remain unanswered.}

## References

[1] Author1 et al. (2024). Paper title. *Journal Name*. [DOI](https://doi.org/10.xxxx/xxxxx). CorpusId:NNNNN
[2] Author2 & Author3 (2023). Another paper. *Venue*. [DOI](https://doi.org/10.xxxx/xxxxx). CorpusId:NNNNN
...

## Traversal Metadata

- **Strategy:** {review, scRNAseq, keyword}
- **Seed papers:** {count}
- **Traversal depth:** {max depth reached}
- **Snippets processed:** {count}
- **Unique papers in evidence:** {count}
- **Papers with quotes used in report:** {count}
```

### 5. Quote formatting

Quotes appear inline with the narrative, indented or in quotation marks, immediately followed by the reference number:

**For short quotes (< 1 line):**
> Tanycytes are "the primary adult neural stem cells of the hypothalamus" [3].

**For longer quotes (1-3 lines):**
> Studies have shown that:
>
> > "β-tanycytes express DIO2 and convert T4 to T3, playing a critical role in thyroid hormone regulation at the median eminence" [5]

**Every quote must:**
- Be an exact substring from a snippet (as recorded in all_summaries.json)
- Have a reference number linking to a specific paper
- Support the claim it follows

### 6. Save

Write the report to `{input_dir}/report.md`.

## Rules

- **Never fabricate quotes.** Only use quotes that appear in all_summaries.json.
- **Never fabricate references.** Only cite papers in paper_catalogue.json.
- **Every factual claim needs a citation.** If you can't cite it, don't assert it.
- **Organize by theme, not by depth.** The reader doesn't care about traversal order.
- **Include a Gaps section.** Be honest about what wasn't found.
- **DOI hyperlinks are mandatory** when a DOI is available in the catalogue.
- If a paper has no DOI, use the Semantic Scholar URL from the catalogue.
- Prefer quotes that contain specific data (gene names, measurements, mechanisms) over generic statements.
