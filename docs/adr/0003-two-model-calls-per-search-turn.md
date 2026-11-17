# 3. Two model calls per search turn; ranking in code

**Status:** accepted (Phase 3)

## Context
The plan's search agent called a model to parse, to rerank and to answer. The free OpenRouter tier
and our own daily cap (300 calls) make three calls per turn expensive, and each adds 2-4 s.

## Decision
A searching turn makes two calls: `search_parse` and `search_respond`. Everything else is code:
slang ("thoda sasta" → budget × 0.9), locality and POI lookup, hybrid retrieval (pgvector +
full-text, reciprocal rank fusion), the relax ladder, commute, and ranking (`0.6 × relevance +
0.4 × soft-preference match`). Follow-ups ("the 2nd one") resolve against stored result IDs.

## Consequences
- About 150 search turns a day fit the cap; slang and numbers behave the same whatever the model says.
- No learned reranker; retrieval quality is measured instead (`evals/run_retrieval.py`), where
  hybrid beats either side alone.
