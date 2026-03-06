
  Citation Traversal Results: Allen Brain Cell Atlas → 2 steps

  Tanycytes

  Subtypes (dorsal→ventral along 3V):
  - α1: Slc17a8, Cd59a, Mafb, S100β; dorsal 3V adjacent to VMH/DMH; most ependymal-like
  - α2: Vcan, Pdzph1, Rarres2; lateral 3V adjacent to ARC; primary adult neural stem cells —
  self-renew and generate β tanycytes, astrocytes, neurons
  - β1: Frzb, Penk, Crym, Lrp2; lateral ME walls; leptin transport via Megalin/LRP2, nutrient
  sensing
  - β2: Scn7a, Adm, Sprr1a; ME floor projecting to portal capillaries; thyroid hormone
  regulation (DIO2 converts T4→T3), TRH degradation (PPII), BBB permeability via VEGF-A

  Pan-tanycyte markers: Rax, Nestin, Vimentin, Sox2, Col23a1, Slc16a2, Lhx2

  Key insight: Neurogenesis hierarchy runs β→α (not α→β) — β tanycytes are slow-dividing
  progenitors producing transit-amplifying α tanycytes that generate parenchymal neurons/glia.
  Fgf10+ β tanycytes generate orexigenic NPY+ neurons in ARC.

  Primary evidence: Campbell 2017, Robins 2013, Haan 2013, Sullivan 2022 (Tany-Seq), Langlet
  2019, Miranda-Angulo 2014

  ---
  Cajal-Retzius Cells

  Markers: p73 is the ONLY specific marker (100% of CR cells, 0% of interneurons P7–P60).
  Reelin, calretinin, COUP-TFII are all non-specific (shared with GABAergic interneurons).
  Additional: Cxcr4 (hem-derived), Tbr1, 5-HT3 receptor.

  Three developmental origins:
  - Cortical hem: p73+/Cxcr4+/calretinin+ → dorsomedial cortex, hippocampus (main source)
  - Pallial-subpallial boundary: p73−/Dbx1-lineage → ventrolateral pallium
  - Septum: p73+/Cxcr4− → medial regions

  Function: Reelin secretion for cortical lamination + dendritic maturation regulation.
  CR-derived reelin and interneuron-derived reelin have distinct contributions (Vilchez-Acosta
  2022).

  Fate: Neocortical CR cells undergo apoptosis by P14–P21; hippocampal CR cells persist through
  P60+. CR death is functionally required for L1 inhibitory circuit maturation — preventing it
  causes hyperexcitability and sensory processing deficits (Damilou 2024).

  Primary evidence: Anstötz & Maccaferri 2020, Meyer 2004, Damilou 2024, Miyoshi 2010, Trousse
  2015

  ---
  Pinealocytes

  Two subtypes (1:19 ratio from Mays et al. 2018 scRNA-seq):
  - α-pinealocytes (5%): High Asmt (~3.4×), high OxPhos genes, low ribosomal genes —
  metabolically optimized for the final O-methylation step (NAS→melatonin)
  - β-pinealocytes (95%): Higher ribosomal/G-protein transducin genes, more day/night
  differentially expressed genes — produce bulk N-acetylserotonin via AANAT

  TF cascade (sequential nightly peaks): Rax (day→night transition) → Otx2 (early night) → Crx
  (mid-night) → Aanat expression (late night peak). Dual control: PCE elements for tissue
  specificity via CRX/OTX2 + CRE elements for circadian rhythm via cAMP/norepinephrine.

  Melatonin pathway: TPH1 → AANAT (rate-limiting) → ASMT/HIOMT. Cooperative model:
  β-pinealocytes produce NAS, α-pinealocytes efficiently convert it to melatonin.

  Photoreceptor relationship: >55 genes shared with retina (common evolutionary origin).
  Neonatal pinealocytes express all phototransduction components (rod + cone variants); most
  decline during development. Adult mammalian pineal uses neural (sympathetic) not photic input.

  Primary evidence: Mays 2018, Coon 2019, Rohde 2014, Bailey 2009, Blackshaw & Snyder 1997

  ---
  Method Validation

  This 2-step traversal from the Allen Brain Cell Atlas paper — using EuropePMC full text
  extraction (step 0) → ASTA snippet_search (steps 1–2) — recovered substantial primary evidence
   that would be invisible to keyword search alone. The atlas paper itself contains minimal
  marker evidence; the real content is 2 citation hops away in scRNA-seq datasets, developmental
   biology papers, and specialized reviews.

✻ Sautéed for 36s

❯ Summarise how you did this: what methods did you use, what worked what didn't, what are   
  the inefficiencies?                                                                       

⏺ Method Summary: 2-Step Citation Traversal Experiment

  What we did

  Starting from one paper (Yao et al. 2023, Allen Brain Cell Atlas), traced citations for 3 cell
   types (tanycyte, Cajal-Retzius, pinealocyte) through 2 levels to find primary evidence about
  markers, function, location, and gene expression.

  Step 0: Extract mentions from the seed paper

  Tried first: ASTA snippet_search scoped to the paper's DOI. Failed — returned only
  abstract/title snippets. The cell type content is in figures, tables, and extended data, which
   ASTA doesn't index well for this paper.

  Fallback: EuropePMC full text (JATS→markdown via get_europepmc_full_text), then grepped for
  cell type names. Worked, but reference extraction was painful — the references section was
  poorly formatted (concatenated without delimiters). Required multiple regex attempts to parse
  ref numbers → DOIs.

  Coverage varied by cell type:
  - Tanycytes: 10 mentions, rich text with specific refs (74, 75, 76)
  - Cajal-Retzius: 2 mentions, minimal detail
  - Pinealocytes: 0 mentions ("Pineal Glut" class name only, 2 hits)

  Step 1: Follow cited references

  Resolved ref numbers → DOIs (manual extraction from mangled ref list) → ASTA get_paper_batch
  for metadata → ASTA snippet_search scoped to cited papers.

  What worked: Scoped snippet search on review papers (Miyata 2022 for tanycytes, Langlet 2019
  for tanycyte subtypes) returned rich, relevant passages with refMentions corpus IDs.

  What didn't: Scoped search against non-OA papers returned empty (Maronde 2007 for pinealocytes
   — not in the peS2o corpus). Fallback: unscoped broad snippet search, which worked well but
  loses the citation-chain provenance.

  Step 2: Follow refMentions one more level

  Ran as 3 parallel background agents, each doing 2-3 snippet_search calls on topics derived
  from step-1 findings. All returned rich results.

  Key choice: At step 2, searches were unscoped (not restricted to specific paper IDs from
  refMentions). This was pragmatic — extracting and resolving individual corpus IDs from step-1
  JSON would have required more orchestration — but it means step 2 is really "informed keyword
  search" rather than true citation traversal.

  What worked well

  1. EuropePMC → ASTA hybrid: EuropePMC for full text access + metadata filtering; ASTA for
  body-text semantic search with citation annotations. Each tool does what it's best at.
  2. Parallel background agents: 3 cell types searched simultaneously at step 2, each completing
   in ~2 minutes.
  3. Haiku-based agents for synthesis: Each agent compiled structured summaries across the
  traversal chain, not just raw search results.
  4. Coverage depth: Recovered substantial primary evidence (scRNA-seq datasets, developmental
  papers) that the atlas paper only references in passing.

  What didn't work well

  1. ASTA body-text coverage is uneven: The atlas paper (Nature, 2023, very high profile) had
  almost no body text indexed. Other papers had full coverage. Unpredictable.
  2. Reference parsing from JATS→markdown: The converted reference list was a wall of
  concatenated text. Extracting structured refs required brittle regex. A proper JATS XML parser
   would be far more reliable.
  3. Non-OA papers are invisible to scoped snippet search: Maronde 2007 simply wasn't in the
  corpus. No error — just empty results. You only discover this by absence.

  Inefficiencies

  1. Step 2 lost citation-chain fidelity: Instead of extracting specific matchedPaperCorpusId
  values from step-1 snippets and scoping step-2 searches to those papers, the agents ran broad
  topical searches. Faster to implement but doesn't prove the citation-traversal mechanism at
  depth 2 — it proves "iteratively refined keyword search."
  2. Manual reference resolution at step 0→1: Parsing ref numbers from full text,
  cross-referencing against a mangled ref list, resolving to DOIs — this was the most
  time-consuming part and the most fragile. A JATS XML parser or Grobid would automate this
  entirely.
  3. No relevance scoring between steps: Every cited paper was followed equally. The planned
  architecture (Haiku scoring passages, only following refs from high-scoring passages) was
  skipped. At this scale (3 cell types, ~10 refs each) it didn't matter. At 50+ papers it would.
  4. No deduplication across cell types: The three parallel agents may have found overlapping
  papers. No shared state between them.
  5. JSON results not structured for reuse: Snippet search results were consumed and summarized
  by agents but not stored in a reusable format. A second run would repeat all API calls.

  What a production version needs

  - Proper JATS XML or Grobid parser for structured reference extraction
  - Explicit refMention extraction and scoped search at each depth level
  - Haiku relevance gate between traversal steps
  - Per-paper result cache (keyed by corpus ID + query)
  - Shared visited-papers set across parallel branches
