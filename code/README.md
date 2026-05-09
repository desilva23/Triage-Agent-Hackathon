# Support Triage Agent: Engineering & Architecture

This directory contains the implementation of a production-grade, agentic support triage system. Designed for the HackerRank Orchestrate hackathon, it prioritizes **Groundedness**, **Deterministic Safety**, and **Autonomous Reasoning**.

## Key Architectural Decisions

### 1. ReAct Agent Pattern (`react_agent.py`)
We chose the **ReAct (Reason + Act)** pattern over a linear pipeline. This allows the LLM to:
- Dynamically formulate search queries based on the issue.
- Observe search results and "think" before acting again.
- Critically reflect on its own drafts (Reflexion) before finalizing a response.

### 2. Hybrid Retrieval with Cross-Encoder Reranking (`retriever.py`)
To ensure zero-hallucination responses, we implemented a multi-stage retrieval pipeline:
- **Semantic Chunking**: Documents are split by markdown headers to preserve context boundaries.
- **Hybrid Search**: Combines BM25 keyword matching with Dense Embeddings (`all-MiniLM-L6-v2`) for high recall.
- **Cross-Encoder Reranking**: Uses `ms-marco-MiniLM-L-6-v2` as a final judge to select the top 2 absolute best context chunks.

### 3. Efficiency & Cost Optimization
- **Semantic Cache (`semantic_cache.py`)**: Persistently caches semantically similar queries to disk using local embeddings, saving significant API costs and latency.
- **Local Compute**: Embedding and reranking are performed locally on the host machine; external LLMs are used strictly for high-level reasoning.

### 4. Enterprise-Grade Safety (`safety.py`)
A deterministic, non-LLM safety layer intercepts every ticket before processing. It uses strict matching for high-risk categories (Fraud, Legal, PII, Outages) to ensure 100% reliable escalation for sensitive issues.

---

## Technical Features

- **Sentiment Analysis**: Dynamic tone adjustment and empathetic routing for frustrated customers.
- **Confidence Scoring**: Automatic abstention (escalation) if the agent's confidence drops below 75%.
- **ROI & Token Analytics**: Built-in telemetry tracks API costs, token usage, and semantic cache savings.
- **Reasoning Trace Export**: Every ticket generates a detailed Markdown trace in the `traces/` folder for 100% observability.

## How to Run

### Installation
```bash
pip install -r code/requirements.txt
```

### Execution
Run the high-performance triage pipeline from the project root:
```bash
python3 code/main.py support_issues/support_issues.csv support_issues/output.csv
```

### Performance & Quality
- **Indexing**: Run `python3 code/index.py` to pre-compute embeddings for instant inference.
- **Audit**: Run `python3 code/evaluate.py` to generate the AI-Verified Accuracy Report.
- **Playground**: Run `python3 code/chat.py` for a live interactive demonstration.

## System Requirements
- Python 3.9+
- Groq Cloud API Key (set in `.env` or system environment)
- Local disk space for embedding model weights (~100MB)
