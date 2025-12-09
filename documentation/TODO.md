# 1-Week Improvement Plan: "The Edge"

This plan focuses on high-impact improvements to RAG quality, graph capabilities, and answer reliability to outpace competition.

## 📅 Days 1-2: Advanced GraphRAG & Retrieval

*   **Implement Parent Document Retrieval (PDR)**:
    *   *Current*: We retrieve individual articles.
    *   *Upgrade*: If >3 articles from the same Chapter are retrieved, fetch the *entire Chapter* as a single context block.
    *   *Benefit*: Better understanding of legal context and definitions applicable to the whole chapter.

*   **Hypothetical Document Embeddings (HyDE)**:
    *   *Action*: Add a `QueryExpansionNode` before retrieval. Generating a fake "perfect legal answer" and embedding *that* for search.
    *   *Benefit*: Drastically improves semantic matching for complex legal questions where exact keywords fail.

## 📅 Day 3: Answer Quality & Self-Correction

*   **Self-Correction Loop (Reflexion)**:
    *   *Action*: Add a `GraderNode` in LangGraph after generation.
    *   *Logic*: LLM asks itself: "Does this answer citation [X] actually support the claim?". If No, regenerate.
    *   *Benefit*: Reduces hallucinated citations to near-zero.

*   **Citation Precision**:
    *   *Action*: Force LLM to output precise snippet locations (e.g., "Article 14, paragraph 2") rather than just "Article 14".

## 📅 Day 4: Performance & Caching

*   **Redis Semantic Cache**:
    *   *Status*: Currently caching embeddings in JSON file (slow, unscalable).
    *   *Upgrade*: Move `embeddings_cache.json` to a Redis instance.
    *   *Benefit*: <50ms latency for repeated queries (FAQs).

*   **Parallel Execution**:
    *   *Action*: Run `History Retrieval` and `Current RAG` in parallel threads within the LangGraph node.

## 📅 Day 5: Observability & Evaluation

*   **Custom Phoenix Evaluations**:
    *   *Action*: Configure Phoenix to automatically score every interaction on:
        1.  **Relevance**: (0-1) Did we answer the specific legal question?
        2.  **Groundedness**: (0-1) Are all claims supported by retrieved articles?
    *   *Benefit*: Quantitative metrics to prove "The Edge" over competitors.
