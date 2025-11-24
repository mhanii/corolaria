# Two-Week Development Plan: Coloraria Legal Agent

## Week 1: Building the "Brain" (Knowledge Base)

**Goal**: Ensure the agent has a reliable, structured, and semantic understanding of the laws.

### Day 1-2: Neo4j Optimization
- [ ] **Neo4j Batch Insert**: Optimize the Neo4j batch insert process to handle large volumes of data efficiently.

### Day 3-4: Embedding & Indexing Optimization
- [ ] **Vector Quality Check**: Manually inspect a few generated embeddings/retrievals to ensure semantic relevance.
- [ ] **Qdrant Integration**: Finalize the `QdrantIndexer` to ensure we have a specialized Vector DB ready for high-speed queries (alongside Neo4j).
- [ ] **Hybrid Indexing**: Ensure Neo4j has both Fulltext (Keyword) and Vector indexes enabled.


## Week 2: Building the "Mind" (Reasoning & Interface)

**Goal**: Enable the agent to answer questions using the knowledge base.

### Day 6-7: Retrieval Logic (The "R" in RAG)
- [ ] **Retrieval Service**: Create a `RetrievalService` in `src/domain/services/`.
- [ ] **Hybrid Search Strategy**: Implement logic to combine Vector Similarity + Keyword Search + Graph Traversal (e.g., "Find articles about X in Title Y").
- [ ] **Context Windowing**: Implement logic to fetch "surrounding" articles (e.g., if Article 5 is found, also fetch 4 and 6 for context).

### Day 8-9: LLM Integration (The "G" in RAG)
- [ ] **Gemini Pro Integration**: Connect `src/ai/llm/gemini_client.py` to Google Gemini Pro.
- [ ] **Prompt Engineering**: Design system prompts for the Legal Agent (e.g., "You are an expert Spanish lawyer...").
- [ ] **Answer Synthesis**: Implement the flow: Query -> Retrieve -> Synthesize Answer.

### Day 10: Copilot Interface (MVP)
- [ ] **CLI / Simple API**: Build a simple command-line interface or FastAPI endpoint to chat with the agent.
- [ ] **Demo**: Verify the agent can answer a complex legal question citing specific articles.
