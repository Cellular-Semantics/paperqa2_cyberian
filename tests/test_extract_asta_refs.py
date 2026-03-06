"""Tests for ASTA RefMention extractor."""

from __future__ import annotations

import json
import urllib.request

import pytest

from paperqa2_cyberian.extract_asta_refs import (
    ExtractionResult,
    RefMention,
    _extract_from_snippet,
    _find_sentence_for_ref,
    extract_ref_mentions,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SNIPPET_BODY = {
    "score": 0.57,
    "paper": {
        "corpusId": "2762329",
        "title": "Histology of the Salivary Glands",
        "authors": [{"name": "A. Author"}],
    },
    "snippet": {
        "text": (
            "The acinar cells secrete enzymes. "
            "Demilune cells [51] cap the mucous acini. "
            "They produce serous fluid."
        ),
        "snippetKind": "body",
        "section": "Acinus",
        "snippetOffset": {"start": 14152, "end": 15642},
        "annotations": {
            "refMentions": [
                {
                    "start": 50,
                    "end": 54,
                    "matchedPaperCorpusId": "22612890",
                },
            ],
            "sentences": [
                {"start": 0, "end": 35},
                {"start": 36, "end": 73},
                {"start": 74, "end": 99},
            ],
        },
    },
}

SNIPPET_ABSTRACT = {
    "score": 0.42,
    "paper": {"corpusId": "9999", "title": "Abstract Paper"},
    "snippet": {
        "text": "This is an abstract with no annotations.",
        "snippetKind": "abstract",
        "section": None,
        "snippetOffset": {"start": 0, "end": 40},
        "annotations": None,
    },
}

SNIPPET_UNRESOLVED = {
    "score": 0.3,
    "paper": {"corpusId": "1111", "title": "Unresolved Paper"},
    "snippet": {
        "text": "Some text [1] and [2] here.",
        "snippetKind": "body",
        "section": "Intro",
        "snippetOffset": {"start": 0, "end": 27},
        "annotations": {
            "refMentions": [
                {"start": 10, "end": 13, "matchedPaperCorpusId": None},
                {"start": 18, "end": 21, "matchedPaperCorpusId": None},
            ],
            "sentences": [{"start": 0, "end": 27}],
        },
    },
}

SNIPPET_MIXED = {
    "score": 0.5,
    "paper": {"corpusId": "5555", "title": "Mixed Paper"},
    "snippet": {
        "text": "Ref one [1] and ref two [2] in text.",
        "snippetKind": "body",
        "section": "Methods",
        "snippetOffset": {"start": 0, "end": 36},
        "annotations": {
            "refMentions": [
                {"start": 8, "end": 11, "matchedPaperCorpusId": "100"},
                {"start": 24, "end": 27, "matchedPaperCorpusId": None},
            ],
            "sentences": [{"start": 0, "end": 36}],
        },
    },
}


# ---------------------------------------------------------------------------
# TestFindSentenceForRef
# ---------------------------------------------------------------------------


class TestFindSentenceForRef:
    def test_sentence_found(self):
        annotations = {
            "sentences": [
                {"start": 0, "end": 35},
                {"start": 36, "end": 73},
            ]
        }
        text = "A" * 74
        result = _find_sentence_for_ref(annotations, 40, 44, text)
        assert result == text[36:73]

    def test_ref_at_boundary(self):
        annotations = {"sentences": [{"start": 0, "end": 10}]}
        text = "0123456789"
        # ref exactly at end boundary
        assert _find_sentence_for_ref(annotations, 8, 10, text) == text[0:10]
        # ref exactly at start boundary
        assert _find_sentence_for_ref(annotations, 0, 2, text) == text[0:10]

    def test_no_sentences_annotation(self):
        assert _find_sentence_for_ref(None, 5, 10, "some text") is None
        assert _find_sentence_for_ref({}, 5, 10, "some text") is None
        assert (
            _find_sentence_for_ref({"sentences": None}, 5, 10, "some text")
            is None
        )

    def test_ref_outside_all_sentences(self):
        annotations = {"sentences": [{"start": 0, "end": 5}]}
        assert _find_sentence_for_ref(annotations, 10, 15, "x" * 20) is None


# ---------------------------------------------------------------------------
# TestExtractFromSnippet
# ---------------------------------------------------------------------------


class TestExtractFromSnippet:
    def test_body_snippet_with_refs(self):
        mentions = _extract_from_snippet(SNIPPET_BODY, "test query")
        assert len(mentions) == 1
        m = mentions[0]
        assert m.corpus_id == "22612890"
        assert m.source_paper_corpus_id == "2762329"
        assert m.source_paper_title == "Histology of the Salivary Glands"
        assert m.section == "Acinus"
        assert m.char_start == 50
        assert m.char_end == 54
        assert m.snippet_score == 0.57
        # sentence containing the ref
        assert m.sentence == SNIPPET_BODY["snippet"]["text"][36:73]

    def test_abstract_snippet_null_annotations(self):
        mentions = _extract_from_snippet(SNIPPET_ABSTRACT, "q")
        assert mentions == []

    def test_all_refs_unresolved(self):
        mentions = _extract_from_snippet(SNIPPET_UNRESOLVED, "q")
        assert mentions == []

    def test_mixed_resolved_unresolved(self):
        mentions = _extract_from_snippet(SNIPPET_MIXED, "q")
        assert len(mentions) == 1
        assert mentions[0].corpus_id == "100"

    def test_no_ref_mentions_key(self):
        snippet = {
            "score": 0.1,
            "paper": {"corpusId": "42", "title": "T"},
            "snippet": {
                "text": "hello",
                "snippetKind": "body",
                "section": "X",
                "snippetOffset": {"start": 0, "end": 5},
                "annotations": {"sentences": [{"start": 0, "end": 5}]},
            },
        }
        assert _extract_from_snippet(snippet, "q") == []


# ---------------------------------------------------------------------------
# TestExtractRefMentions
# ---------------------------------------------------------------------------


class TestExtractRefMentions:
    def _make_response(self, *items):
        return {"result": {"data": list(items)}}

    def test_multi_snippet(self):
        resp = self._make_response(SNIPPET_BODY, SNIPPET_MIXED)
        result = extract_ref_mentions(resp, "test")
        assert isinstance(result, ExtractionResult)
        assert len(result.ref_mentions) == 2
        assert "22612890" in result.unique_corpus_ids
        assert "100" in result.unique_corpus_ids

    def test_dedup_corpus_ids(self):
        # Two snippets referencing the same corpus_id
        s2 = {
            "score": 0.4,
            "paper": {"corpusId": "AAA", "title": "P2"},
            "snippet": {
                "text": "dup ref [1]",
                "snippetKind": "body",
                "section": "S",
                "snippetOffset": {"start": 0, "end": 11},
                "annotations": {
                    "refMentions": [
                        {
                            "start": 8,
                            "end": 11,
                            "matchedPaperCorpusId": "22612890",
                        }
                    ],
                    "sentences": [{"start": 0, "end": 11}],
                },
            },
        }
        resp = self._make_response(SNIPPET_BODY, s2)
        result = extract_ref_mentions(resp, "q")
        assert result.unique_corpus_ids.count("22612890") == 1
        assert len(result.ref_mentions) == 2  # both mentions kept

    def test_empty_data(self):
        result = extract_ref_mentions({"result": {"data": []}}, "q")
        assert result.unique_corpus_ids == []
        assert result.ref_mentions == []
        assert result.stats["total_snippets"] == 0

    def test_stats_computation(self):
        resp = self._make_response(
            SNIPPET_BODY, SNIPPET_UNRESOLVED, SNIPPET_MIXED
        )
        result = extract_ref_mentions(resp, "q")
        assert result.stats["total_snippets"] == 3
        assert result.stats["total_ref_mentions"] == 5  # 1+2+2
        assert result.stats["resolved_refs"] == 2
        assert result.stats["unresolved_refs"] == 3  # 0+2+1
        assert result.unresolved_count == 3

    def test_source_papers_tracked(self):
        resp = self._make_response(SNIPPET_BODY, SNIPPET_ABSTRACT)
        result = extract_ref_mentions(resp, "q")
        assert "2762329" in result.source_papers
        assert "9999" in result.source_papers
        assert result.source_papers["2762329"] == "Histology of the Salivary Glands"

    def test_unique_corpus_ids_first_appearance_order(self):
        # Build two snippets: first has id "B", second has "A" then "B"
        s1 = {
            "score": 0.9,
            "paper": {"corpusId": "P1", "title": "P1"},
            "snippet": {
                "text": "ref [1]",
                "snippetKind": "body",
                "section": "S",
                "snippetOffset": {"start": 0, "end": 7},
                "annotations": {
                    "refMentions": [
                        {"start": 4, "end": 7, "matchedPaperCorpusId": "B"}
                    ],
                    "sentences": [{"start": 0, "end": 7}],
                },
            },
        }
        s2 = {
            "score": 0.8,
            "paper": {"corpusId": "P2", "title": "P2"},
            "snippet": {
                "text": "ref [1] and [2]",
                "snippetKind": "body",
                "section": "S",
                "snippetOffset": {"start": 0, "end": 15},
                "annotations": {
                    "refMentions": [
                        {"start": 4, "end": 7, "matchedPaperCorpusId": "A"},
                        {"start": 12, "end": 15, "matchedPaperCorpusId": "B"},
                    ],
                    "sentences": [{"start": 0, "end": 15}],
                },
            },
        }
        result = extract_ref_mentions({"result": {"data": [s1, s2]}}, "q")
        assert result.unique_corpus_ids == ["B", "A"]

    def test_flat_response_format(self):
        """Response without 'result' wrapper (just has 'data' at top level)."""
        resp = {"data": [SNIPPET_BODY]}
        result = extract_ref_mentions(resp, "q")
        assert len(result.ref_mentions) == 1


# ---------------------------------------------------------------------------
# Integration tests (require network + Semantic Scholar API)
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestIntegration:
    """Integration tests hitting ASTA snippet_search via MCP HTTP transport."""

    @staticmethod
    def _search(query: str, limit: int = 10, paper_ids: str | None = None) -> dict:
        from paperqa2_cyberian.extract_asta_refs import _call_snippet_search

        return _call_snippet_search(query, limit, paper_ids)

    def test_demilune_snippets_have_refs(self):
        resp = self._search("serous demilune", limit=10)
        data = resp.get("result", resp).get("data", [])
        assert len(data) > 0
        # At least one snippet should have resolved refs
        all_refs = []
        for item in data:
            annot = item.get("snippet", {}).get("annotations")
            if annot and annot.get("refMentions"):
                for rm in annot["refMentions"]:
                    if rm.get("matchedPaperCorpusId"):
                        all_refs.append(rm["matchedPaperCorpusId"])
        assert len(all_refs) > 0, "Expected at least one resolved ref mention"

    def test_scoped_search(self):
        # Use a known paper corpus ID (histology textbook)
        resp = self._search(
            "salivary gland", limit=5, paper_ids="CorpusId:2762329"
        )
        data = resp.get("result", resp).get("data", [])
        # All results should be from the scoped paper
        for item in data:
            assert str(item["paper"]["corpusId"]) == "2762329"

    def test_extraction_produces_corpus_ids(self):
        resp = self._search("tanycyte markers hypothalamus", limit=10)
        result = extract_ref_mentions(resp, "tanycyte markers hypothalamus")
        assert len(result.unique_corpus_ids) > 0
        assert result.stats["unique_refs"] > 0

    def test_unresolved_counted(self):
        resp = self._search("gene expression regulation", limit=20)
        result = extract_ref_mentions(resp, "gene expression regulation")
        # With enough snippets, there should be at least some unresolved refs
        # (this is a soft assertion — if all are resolved, the test still passes
        # but logs a note)
        if result.unresolved_count == 0:
            pytest.skip(
                "No unresolved refs found in this search — not a failure"
            )
        assert result.unresolved_count > 0
        assert result.stats["unresolved_refs"] == result.unresolved_count
