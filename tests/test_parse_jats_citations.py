"""Tests for parse_jats_citations.py — unit tests with inline XML, integration tests against EuropePMC."""

from __future__ import annotations

import xml.etree.ElementTree as ET

import pytest

from paperqa2_cyberian.parse_jats_citations import (
    CitedSentence,
    ResolvedRef,
    _assign_citations_to_sentences,
    _clean_xml,
    _expand_ref_range,
    _parse_ref_list,
    _parse_single_ref,
    _reconstruct_paragraph,
    _split_sentences,
    _strip_namespace_from_tree,
    parse_jats_citations,
)


# ============================================================================
# Fixtures: minimal JATS XML fragments
# ============================================================================

MINIMAL_REF_ELEMENT_CITATION = """\
<ref id="CR1">
  <element-citation publication-type="journal">
    <person-group person-group-type="author">
      <name><surname>Smith</surname><given-names>J</given-names></name>
    </person-group>
    <article-title>A great paper</article-title>
    <year>2020</year>
    <pub-id pub-id-type="doi">10.1234/test</pub-id>
    <pub-id pub-id-type="pmid">12345678</pub-id>
    <pub-id pub-id-type="pmcid">PMC9999999</pub-id>
  </element-citation>
</ref>
"""

MINIMAL_REF_MIXED_CITATION = """\
<ref id="bib7">
  <mixed-citation publication-type="journal">
    <person-group person-group-type="author">
      <name><surname>Jones</surname><given-names>A</given-names></name>
    </person-group>
    <article-title>Another paper</article-title>
    <year>2019</year>
    <pub-id pub-id-type="doi">10.5678/test2</pub-id>
  </mixed-citation>
</ref>
"""

# Nature-style: <sup> wrapping xrefs
PARAGRAPH_SUP_STYLE = """\
<p>The brain has many cell types<sup><xref ref-type="bibr" rid="CR1">1</xref>,<xref ref-type="bibr" rid="CR2">2</xref></sup> and regions.</p>
"""

# PLOS-style: inline xrefs with ref-type="ref"
PARAGRAPH_INLINE_STYLE = """\
<p>Alzheimer's disease is common (Smith, <xref rid="bib1" ref-type="ref">2020</xref>). It affects many people (Jones, <xref rid="bib2" ref-type="ref">2019</xref>).</p>
"""

# Range citation: CR1–CR3
PARAGRAPH_RANGE = """\
<p>Several studies<sup><xref ref-type="bibr" rid="CR1">1</xref>–<xref ref-type="bibr" rid="CR3">3</xref></sup> show this.</p>
"""

# Mixed content in paragraph: italic, bold, fig xref
PARAGRAPH_MIXED = """\
<p>The <italic>Mus musculus</italic> brain (see <xref ref-type="fig" rid="F1">Fig. 1</xref>) has been studied<sup><xref ref-type="bibr" rid="CR5">5</xref></sup>.</p>
"""

# Full minimal document
MINIMAL_DOCUMENT = """\
<article>
  <front>
    <article-meta>
      <abstract>
        <p>We studied cells<sup><xref ref-type="bibr" rid="CR1">1</xref></sup>.</p>
      </abstract>
    </article-meta>
  </front>
  <body>
    <sec>
      <title>Introduction</title>
      <p>Cell types matter<sup><xref ref-type="bibr" rid="CR1">1</xref>,<xref ref-type="bibr" rid="CR2">2</xref></sup>. This is important.</p>
    </sec>
    <sec>
      <title>Results</title>
      <sec>
        <title>Neuronal types</title>
        <p>We found neurons<sup><xref ref-type="bibr" rid="CR3">3</xref></sup>.</p>
      </sec>
    </sec>
  </body>
  <back>
    <ref-list>
      <ref id="CR1">
        <element-citation>
          <person-group><name><surname>Alpha</surname></name></person-group>
          <article-title>Paper one</article-title>
          <year>2020</year>
          <pub-id pub-id-type="doi">10.1/one</pub-id>
        </element-citation>
      </ref>
      <ref id="CR2">
        <element-citation>
          <person-group><name><surname>Beta</surname></name></person-group>
          <article-title>Paper two</article-title>
          <year>2021</year>
          <pub-id pub-id-type="doi">10.1/two</pub-id>
          <pub-id pub-id-type="pmid">11111111</pub-id>
        </element-citation>
      </ref>
      <ref id="CR3">
        <element-citation>
          <person-group><name><surname>Gamma</surname></name></person-group>
          <article-title>Paper three</article-title>
          <year>2022</year>
          <pub-id pub-id-type="doi">10.1/three</pub-id>
        </element-citation>
      </ref>
    </ref-list>
  </back>
</article>
"""

# Document with xmlns namespace
NAMESPACED_DOCUMENT = """\
<article xmlns:xlink="http://www.w3.org/1999/xlink">
  <body>
    <sec>
      <title>Main</title>
      <p>A claim<sup><xref ref-type="bibr" rid="CR1">1</xref></sup>.</p>
    </sec>
  </body>
  <back>
    <ref-list>
      <ref id="CR1">
        <element-citation>
          <article-title>Test</article-title>
          <year>2023</year>
        </element-citation>
      </ref>
    </ref-list>
  </back>
</article>
"""


# ============================================================================
# Unit tests: _clean_xml
# ============================================================================

class TestCleanXml:
    def test_strips_doctype(self):
        xml = '<!DOCTYPE article PUBLIC "-//NLM//DTD JATS">\n<article></article>'
        assert "<!DOCTYPE" not in _clean_xml(xml)
        assert "<article>" in _clean_xml(xml)

    def test_passthrough_no_doctype(self):
        xml = "<article><body/></article>"
        assert _clean_xml(xml) == xml


# ============================================================================
# Unit tests: _strip_namespace_from_tree
# ============================================================================

class TestStripNamespace:
    def test_removes_xmlns(self):
        root = ET.fromstring('<root xmlns:xlink="http://example.com"><child xlink:href="x"/></root>')
        _strip_namespace_from_tree(root)
        child = root.find("child")
        assert child is not None
        assert "href" in child.attrib


# ============================================================================
# Unit tests: _parse_single_ref
# ============================================================================

class TestParseSingleRef:
    def test_element_citation(self):
        elem = ET.fromstring(MINIMAL_REF_ELEMENT_CITATION)
        ref = _parse_single_ref(elem)
        assert ref.ref_id == "CR1"
        assert ref.doi == "10.1234/test"
        assert ref.pmid == "12345678"
        assert ref.pmcid == "PMC9999999"
        assert ref.title == "A great paper"
        assert ref.year == 2020
        assert ref.first_author == "Smith"

    def test_mixed_citation(self):
        elem = ET.fromstring(MINIMAL_REF_MIXED_CITATION)
        ref = _parse_single_ref(elem)
        assert ref.ref_id == "bib7"
        assert ref.doi == "10.5678/test2"
        assert ref.pmid is None
        assert ref.title == "Another paper"
        assert ref.year == 2019
        assert ref.first_author == "Jones"

    def test_empty_ref(self):
        elem = ET.fromstring('<ref id="CR99"></ref>')
        ref = _parse_single_ref(elem)
        assert ref.ref_id == "CR99"
        assert ref.doi is None
        assert ref.title is None
        assert ref.year is None

    def test_chapter_title_fallback(self):
        xml = """<ref id="CR1">
          <element-citation>
            <chapter-title>A chapter</chapter-title>
            <year>2018</year>
          </element-citation>
        </ref>"""
        ref = _parse_single_ref(ET.fromstring(xml))
        assert ref.title == "A chapter"


# ============================================================================
# Unit tests: _parse_ref_list
# ============================================================================

class TestParseRefList:
    def test_parses_all_refs(self):
        root = ET.fromstring(MINIMAL_DOCUMENT)
        refs = _parse_ref_list(root)
        assert len(refs) == 3
        assert "CR1" in refs
        assert "CR2" in refs
        assert "CR3" in refs
        assert refs["CR1"].doi == "10.1/one"
        assert refs["CR2"].pmid == "11111111"


# ============================================================================
# Unit tests: _expand_ref_range
# ============================================================================

class TestExpandRefRange:
    def test_basic_range(self):
        assert _expand_ref_range("CR1", "CR3") == ["CR1", "CR2", "CR3"]

    def test_single_element(self):
        assert _expand_ref_range("CR5", "CR5") == ["CR5"]

    def test_different_prefix(self):
        assert _expand_ref_range("CR1", "bib3") == ["CR1", "bib3"]

    def test_reversed_range(self):
        assert _expand_ref_range("CR5", "CR2") == ["CR5", "CR2"]

    def test_non_numeric(self):
        assert _expand_ref_range("refA", "refB") == ["refA", "refB"]

    def test_bib_prefix(self):
        assert _expand_ref_range("bib10", "bib13") == ["bib10", "bib11", "bib12", "bib13"]


# ============================================================================
# Unit tests: _reconstruct_paragraph
# ============================================================================

class TestReconstructParagraph:
    def test_sup_style_citations(self):
        p = ET.fromstring(PARAGRAPH_SUP_STYLE)
        text, citations = _reconstruct_paragraph(p)
        assert "brain has many cell types" in text
        assert "[1,2]" in text
        rids = [rid for _, rids in citations for rid in rids]
        assert "CR1" in rids
        assert "CR2" in rids

    def test_inline_ref_style(self):
        p = ET.fromstring(PARAGRAPH_INLINE_STYLE)
        text, citations = _reconstruct_paragraph(p)
        assert "Alzheimer" in text
        rids = [rid for _, rids in citations for rid in rids]
        assert "bib1" in rids
        assert "bib2" in rids

    def test_range_expansion(self):
        p = ET.fromstring(PARAGRAPH_RANGE)
        text, citations = _reconstruct_paragraph(p)
        rids = [rid for _, rids in citations for rid in rids]
        assert "CR1" in rids
        assert "CR2" in rids
        assert "CR3" in rids

    def test_mixed_content_preserves_text(self):
        p = ET.fromstring(PARAGRAPH_MIXED)
        text, citations = _reconstruct_paragraph(p)
        assert "Mus musculus" in text
        assert "Fig. 1" in text  # fig xref rendered as text
        rids = [rid for _, rids in citations for rid in rids]
        assert "CR5" in rids
        # Fig xref should NOT appear in citations
        assert "F1" not in rids

    def test_no_citations(self):
        p = ET.fromstring("<p>Just plain text with no references.</p>")
        text, citations = _reconstruct_paragraph(p)
        assert text == "Just plain text with no references."
        assert citations == []


# ============================================================================
# Unit tests: _split_sentences
# ============================================================================

class TestSplitSentences:
    def test_two_sentences(self):
        result = _split_sentences("First sentence. Second sentence.")
        assert len(result) == 2
        assert result[0][0] == "First sentence."
        assert result[1][0] == "Second sentence."

    def test_single_sentence(self):
        result = _split_sentences("Only one sentence here.")
        assert len(result) == 1

    def test_protects_et_al(self):
        result = _split_sentences("Smith et al. found this. Another sentence.")
        # Should not split after "et al."
        assert len(result) == 2
        assert "et al." in result[0][0]

    def test_protects_fig(self):
        result = _split_sentences("See Fig. 3A for details. The result was clear.")
        assert len(result) == 2
        assert "Fig." in result[0][0]

    def test_empty(self):
        assert _split_sentences("") == []

    def test_question_mark(self):
        result = _split_sentences("What is this? It is a test.")
        assert len(result) == 2

    def test_offsets_are_correct(self):
        text = "First. Second. Third."
        result = _split_sentences(text)
        for sent, offset in result:
            assert text[offset : offset + len(sent)] == sent


# ============================================================================
# Unit tests: _assign_citations_to_sentences
# ============================================================================

class TestAssignCitations:
    def test_assigns_to_correct_sentence(self):
        ref_lookup = {
            "CR1": ResolvedRef(ref_id="CR1", doi="10.1/a"),
            "CR2": ResolvedRef(ref_id="CR2", doi="10.1/b"),
        }
        sentences = [("First sentence[1].", 0), ("Second sentence[2].", 20)]
        citations = [(14, ["CR1"]), (35, ["CR2"])]
        result = _assign_citations_to_sentences(sentences, citations, "Intro", ref_lookup)
        assert len(result) == 2
        assert result[0].ref_ids == ["CR1"]
        assert result[1].ref_ids == ["CR2"]
        assert result[0].section == "Intro"

    def test_empty_citations(self):
        result = _assign_citations_to_sentences(
            [("Some text.", 0)], [], "Main", {}
        )
        assert result == []

    def test_deduplicates_ref_ids(self):
        ref_lookup = {"CR1": ResolvedRef(ref_id="CR1")}
        # Two citation markers for same ref in one sentence
        sentences = [("Text[1][1].", 0)]
        citations = [(4, ["CR1"]), (7, ["CR1"])]
        result = _assign_citations_to_sentences(sentences, citations, "Main", ref_lookup)
        assert result[0].ref_ids == ["CR1"]


# ============================================================================
# Unit tests: full parse_jats_citations on synthetic documents
# ============================================================================

class TestParseJatsCitations:
    def test_minimal_document(self):
        sentences, refs = parse_jats_citations(MINIMAL_DOCUMENT)
        assert len(refs) == 3
        assert refs["CR1"].doi == "10.1/one"
        assert refs["CR2"].first_author == "Beta"

        # Should find citations in abstract + body
        assert len(sentences) >= 3

        # Check section assignment
        sections = {s.section for s in sentences}
        assert "Abstract" in sections
        assert "Introduction" in sections
        assert "Neuronal types" in sections

    def test_namespaced_document(self):
        sentences, refs = parse_jats_citations(NAMESPACED_DOCUMENT)
        assert len(refs) == 1
        assert len(sentences) == 1
        assert sentences[0].ref_ids == ["CR1"]

    def test_doctype_stripped(self):
        xml = '<!DOCTYPE article PUBLIC "-//NLM//DTD">\n' + MINIMAL_DOCUMENT
        sentences, refs = parse_jats_citations(xml)
        assert len(refs) == 3

    def test_empty_body(self):
        xml = "<article><body></body><back><ref-list></ref-list></back></article>"
        sentences, refs = parse_jats_citations(xml)
        assert sentences == []
        assert refs == {}


# ============================================================================
# Integration tests: live EuropePMC fetch (network required)
# ============================================================================

@pytest.mark.integration
class TestIntegrationEuropePMC:
    """Integration tests that fetch real JATS XML from EuropePMC.

    These require network access and are marked with @pytest.mark.integration.
    Run with: pytest -m integration
    Skip with: pytest -m "not integration"
    """

    @pytest.fixture
    def allen_brain_xml(self):
        """Fetch PMC10719114 (Allen Brain Atlas, Nature 2023) once per test class."""
        from paperqa2_cyberian.parse_jats_citations import _fetch_jats_xml
        return _fetch_jats_xml("PMC10719114")

    @pytest.fixture
    def plos_xml(self):
        """Fetch PMC7294781 (PLOS, ref-type='ref', mixed-citation)."""
        from paperqa2_cyberian.parse_jats_citations import _fetch_jats_xml
        return _fetch_jats_xml("PMC7294781")

    # -- Allen Brain Atlas (Nature, sup-wrapped xrefs, element-citation) --

    def test_allen_ref_count(self, allen_brain_xml):
        _, refs = parse_jats_citations(allen_brain_xml)
        assert len(refs) >= 140, f"Expected >=140 refs, got {len(refs)}"

    def test_allen_refs_have_dois(self, allen_brain_xml):
        _, refs = parse_jats_citations(allen_brain_xml)
        with_doi = sum(1 for r in refs.values() if r.doi)
        assert with_doi >= 125, f"Expected >=125 refs with DOI, got {with_doi}"

    def test_allen_refs_have_pmids(self, allen_brain_xml):
        _, refs = parse_jats_citations(allen_brain_xml)
        with_pmid = sum(1 for r in refs.values() if r.pmid)
        assert with_pmid >= 125, f"Expected >=125 refs with PMID, got {with_pmid}"

    def test_allen_cited_sentences(self, allen_brain_xml):
        sentences, _ = parse_jats_citations(allen_brain_xml)
        assert len(sentences) >= 80, f"Expected >=80 cited sentences, got {len(sentences)}"

    def test_allen_tanycyte_refs(self, allen_brain_xml):
        """Tanycyte sentences should cite CR76 (known from the experiment)."""
        sentences, _ = parse_jats_citations(allen_brain_xml)
        tanycyte_sentences = [s for s in sentences if "tanycyte" in s.text.lower()]
        assert len(tanycyte_sentences) >= 1, "Should find at least one tanycyte sentence"
        all_rids = [rid for s in tanycyte_sentences for rid in s.ref_ids]
        assert "CR76" in all_rids, f"Tanycyte sentences should cite CR76, got {all_rids}"

    def test_allen_range_expansion(self, allen_brain_xml):
        """At least one sentence should have 3+ consecutive CR refs from range expansion."""
        sentences, _ = parse_jats_citations(allen_brain_xml)
        found_range = False
        for s in sentences:
            if len(s.ref_ids) >= 3:
                # Check if any 3 consecutive refs form a sequence
                for i in range(len(s.ref_ids) - 2):
                    try:
                        nums = [int(rid.replace("CR", "")) for rid in s.ref_ids[i : i + 3]]
                        if nums == [nums[0], nums[0] + 1, nums[0] + 2]:
                            found_range = True
                            break
                    except ValueError:
                        continue
            if found_range:
                break
        assert found_range, "Should find at least one sentence with expanded range citations"

    def test_allen_section_titles(self, allen_brain_xml):
        """Should extract meaningful section titles, not just 'Main'."""
        sentences, _ = parse_jats_citations(allen_brain_xml)
        sections = {s.section for s in sentences}
        assert len(sections) > 1, f"Expected multiple sections, got {sections}"
        assert any(s != "Main" for s in sections), "Should have named sections"

    def test_allen_cr1_metadata(self, allen_brain_xml):
        """CR1 should be Yuste 2020 community transcriptomics paper."""
        _, refs = parse_jats_citations(allen_brain_xml)
        cr1 = refs["CR1"]
        assert cr1.first_author == "Yuste"
        assert cr1.year == 2020
        assert cr1.doi == "10.1038/s41593-020-0685-8"
        assert cr1.pmid == "32839617"

    # -- PLOS paper (inline xrefs, ref-type="ref", mixed-citation) --

    def test_plos_ref_count(self, plos_xml):
        _, refs = parse_jats_citations(plos_xml)
        assert len(refs) >= 50, f"Expected >=50 refs, got {len(refs)}"

    def test_plos_cited_sentences(self, plos_xml):
        sentences, _ = parse_jats_citations(plos_xml)
        assert len(sentences) >= 40, f"Expected >=40 cited sentences, got {len(sentences)}"

    def test_plos_ref_type_ref_works(self, plos_xml):
        """PLOS uses ref-type='ref' not 'bibr' — verify these are captured."""
        sentences, _ = parse_jats_citations(plos_xml)
        assert len(sentences) > 0, "Should capture sentences with ref-type='ref'"
        # Verify ref IDs are the PLOS-style bib IDs
        all_rids = {rid for s in sentences for rid in s.ref_ids}
        assert any("bib" in rid or "acel" in rid for rid in all_rids), (
            f"PLOS refs should have bib-style IDs, got {list(all_rids)[:5]}"
        )

    def test_plos_refs_have_dois(self, plos_xml):
        _, refs = parse_jats_citations(plos_xml)
        with_doi = sum(1 for r in refs.values() if r.doi)
        assert with_doi >= 50, f"Expected >=50 refs with DOI, got {with_doi}"
