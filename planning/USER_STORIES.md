# User Stories — Downstream Products

Three downstream products drive the requirements for this pipeline.
Stories are written verbatim from initial description, lightly tidied.

---

## 1. Cell Ontology Research and Validation Agents

**General story:**
As a biologist/Editor I want to request a change to the Cell Ontology
(addition of one or more terms; edits to one or more terms) in order to
add/edit well-defined, well-researched and well-integrated terms to the
Cell Ontology so that I can use them to annotate my data.

**Workflow:**
Requesters are asked (via GitHub issue templates) to provide as much
detail as possible along with supporting references. The result may be a
well-referenced request with lots of detail, or it might be very minimal
requiring lots of research.

Editors will make a judgement call about whether to pass to:

- **Validation agent** — job is to check that provided references support
  all assertions made in the suggested edits
- **Research agent** — research the literature to synthesise a result from
  multiple sources

In both cases, we need a report with exact quotes from the supporting papers.

**Lit search strategy (research agent):**
For requesting new cell types, start with recent reviews and work back
through citation chains, supplemented with recent paper search for dates
from the year of the most recent review onwards.

For other requested edits, a less comprehensive strategy suffices:
- Synonyms just need supporting references
- Changes to classification or relationships could benefit from a survey
  of supporting (or refuting) papers

---

## 2. evidencell (working title)

**General user story:**
As a developer of a multimodal transcriptomic brain atlas (single cell +
spatial + some coverage from other assays, e.g. patch-seq) I want to map
my cell clusters back to types described in the literature. I want this
mapping to include extensive evidence, supporting transparent review by
other scientists and suggestions for further analysis that can support or
refute these mappings. Evidence includes both experimental evidence
described in papers and supporting text snippets from papers. All refs
must be traceable.

**Likely starting point:**
User has a taxonomy of hierarchically arranged (nested) cell sets
annotated with:
- Markers (possibly multiple sets)
- Location from spatial transcriptomics
- Predicted neurotransmitter / neuropeptides
- Results of other analyses (e.g. circadian expression, sex specificity)
- Annotation transfer from other transcriptomic datasets

User also has context — cell type, anatomical, or both.

Users will be encouraged to keep context and annotated taxonomy
relatively small to keep workflow runs tractable for both agentic research
and review purposes.

Any type of analysis that leverages existing data can be suggested, but
the most valuable is probably annotation transfer from datasets that bridge
classical and transcriptomic definitions of cell types.

**Draft strategy:**
1. Comprehensive literature search for known cell types in context.
   Lit search strategy TBD, but must include search for papers that bridge
   transcriptomics and classical definitions. For all types return a set of
   properties (markers, location, NT, morphology, function, and any genes
   known to underlie morphology and function) + link to any defining
   datasets if transcriptomic. For all properties include details
   (anatomical context that markers have been tested in, protein vs.
   transcript confirmed) and experimental evidence.
2. Make draft mapping of taxonomy types to literature types based on
   properties and location. (May supplement lit search here with searches
   using specific properties.)
3. LLM suggests further experiments — mapping of more properties back to
   classical types.

Rather than storing in free text, all content will be stored in YAML —
including draft mappings and their supporting evidence. Aim will be to
fill out more evidence as more analysis is performed.

---

## 3. Taxonomy Evidence Extraction Tool

Starting from an existing, published taxonomy, mine the reference list +
citations, supplemented by a wider literature search, to add post-hoc
justification (or critique) of annotations.

This process will be combined with mapping to the Cell Ontology.
(Potentially folded into the AMICA annotation tool.)
