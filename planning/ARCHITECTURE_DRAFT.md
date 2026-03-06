# Architecture Draft — Capabilities and Modular Components

**Status: DRAFT — decisions pending experiments**

User stories: [planning/USER_STORIES.md](USER_STORIES.md)

**Product shorthand used in this doc:**

| Shorthand | Full name | User story |
|---|---|---|
| Cell Ont. Validation | Cell Ontology Validation agent | US1 — validation mode |
| Cell Ont. Research | Cell Ontology Research agent | US1 — research mode |
| evidencell | evidencell | US2 |
| Taxonomy Extraction | Taxonomy Evidence Extraction Tool | US3 |

---

## Two fundamental modes

All three downstream products need both modes, in different proportions:

| Mode | Description | Primary user |
|---|---|---|
| **Verification** | Given claim + refs, find exact quotes that support/refute | Cell Ontology Validation; Taxonomy Extraction |
| **Discovery** | Given topic/entity, find + synthesise relevant literature | Cell Ontology Research; evidencell |

---

## Capability map

| Capability | Cell Ont. Validation | Cell Ont. Research | evidencell | Taxonomy Extraction |
|---|---|---|---|---|
| EuropePMC keyword search | minimal | ✓ | ✓ | ✓ |
| ASTA snippet search (body text) | ✓ | ✓ | ✓ | ✓ |
| `PUB_TYPE:review` + date filter | — | ✓ (reviews-first) | ✓ | — |
| Citation traversal (backward) | — | ✓ (deep) | partial | ✓ (seed paper) |
| Co-citation overlap ranking | — | ✓ (quality signal) | ✓ (quality signal) | — |
| Claim → exact quote verification | ✓ core | ✓ | ✓ | ✓ core |
| Property-based search (gene/anatomy) | — | — | ✓ | — |
| Chronological supplement (post-review) | — | ✓ | ✓ | — |
| Structured output (YAML + provenance) | ✓ | ✓ | ✓ core | ✓ |
| Seed paper mining (refs + citations) | — | — | — | ✓ core |
| Venue/citation count surfaced in output | ✓ (editor review) | ✓ | ✓ | ✓ |

---

## Proposed modular components

### 1. `lit-discover`
EuropePMC + ASTA snippet search, with `PUB_TYPE:review` and date-range options.
Current `/literature-search` skill is a rough version of this.
Needs: ASTA snippet search integration, `BODY:` field search, date filter.

### 2. `citation-traverse`
Reviews-first → ASTA refMentions → recurse. Validated in EXP-002, not yet a skill.
Depth + corpus-size bounded. Co-citation overlap (from paperqa2 agentic interface)
as a complementary quality signal.

### 3. `ref-verify`
Given (claim, [paper_ids]), return exact quotes + relevance judgement.
Powers Cell Ontology validation mode and YAML evidence tracing.
Key principle: always trace to primary research paper, not review summary.

### 4. `evidence-structure`
Extract structured property set (marker, location, NT, morphology, function)
from retrieved chunks into YAML with provenance. Specific to evidencell
but the quote+provenance pattern is shared with ref-verify.

### 5. `seed-mine`
Given a published taxonomy/paper, extract its reference list, resolve to IDs,
filter for OA, fetch full texts. Powers Taxonomy Extraction.
Overlaps with `citation-traverse` at depth=1 but direction is different
(exhaustive vs. query-scoped).

---

## Pipeline architecture

### Primary path (OA papers via EuropePMC/ASTA)

```
EuropePMC search / ASTA snippet search
        |
        v
Full text (JATS) or pre-chunked snippets
        |
        v
Section-aware chunking (JATS structure preserved where available)
        |
        v
Embedding + retrieval
        |
        v
LLM relevance scoring / evidence extraction
        |
        v
Structured output (YAML + provenance + venue/citation count)
```

### Secondary path (non-OA PDFs, small numbers, manually downloaded)

```
PDF (institutional access, manual download)
        |
        v
paperqa2 chunking + embedding
        |
        v
Same downstream as primary path
```

paperqa2 is retained as a utility for the secondary path only.
It is not the backbone of the primary pipeline.

---

## Quality signal design

**Problem:** low-quality secondary sources (especially low-prestige reviews)
can distort synthesis if used as evidence rather than as discovery vehicles.

**Principle:** reviews and primary research papers should be treated differently:
- **Reviews** = discovery vehicles → use to find primary papers, not as evidence
- **Primary research** = evidence sources → quote these directly

**Mitigations:**
- ASTA citation count weighting deprioritises obscure papers at discovery stage
- `ref-verify` forces claims to be traced to primary sources
- Venue + citation count surfaced explicitly in output so human reviewers can assess
- Co-citation overlap (paperqa2) rewards papers independently cited by multiple
  relevant sources — stronger quality signal than corpus-wide citation count alone

---

## What needs experiments before deciding

- Whether ASTA snippet search alone is sufficient for S3 (body-text-only) discovery,
  or whether EuropePMC `BODY:` field search adds meaningful coverage
- Whether co-citation overlap (via paperqa2 agentic interface) adds signal beyond
  ASTA's built-in citation count weighting, at the cost of switching interface
- Whether section-aware JATS chunking materially improves evidence extraction vs.
  flat-text chunking (current approach)
- How well `ref-verify` (claim → exact quote) works in practice with ASTA snippet
  search scoped to specific paper IDs
- Whether property-based search (gene symbol + anatomy context) via EuropePMC/ASTA
  is reliable enough for evidencell use case
