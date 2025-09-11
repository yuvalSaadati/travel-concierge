# Travel Concierge & Itinerary Optimizer (LangGraph + LangChain)

A project that demonstrates **LangGraph orchestration**, **LangChain RAG** over a local **Chroma** vector store, **multi-agent style workflow**, simple **memory**, and **tool-using nodes** (weather, FX). It produces a day-by-day itinerary and an `.ics` calendar export.

## Features
- LangGraph state machine with nodes: research → plan → budget → critic → finalize
- RAG over curated city guides (Markdown) using **Chroma** + **sentence-transformers**
- Tools: **Open-Meteo** (weather, no key), **Frankfurter** (FX, no key)
- Optional tool: **OpenTripMap** (POIs — needs free API key; falls back without it)
- Memory: saves simple user preferences in a local JSON file
- FastAPI endpoints (`/ingest`, `/plan`, `/health`)
- Works without paid LLMs; if you have **Ollama** installed, it will use it automatically

## Quickstart

### 0) Requirements
- Python 3.11+ recommended
- (Optional) **Ollama** with a local model (e.g., `llama3.1:8b`) for nicer plans
- Internet access for the free APIs (Open-Meteo, Frankfurter)

### 1) Create & activate a venv
```bash
python -m venv .venv
# Windows PowerShell
. .venv/Scripts/Activate.ps1
# macOS/Linux
source .venv/bin/activate
```

### 2) Install deps
```bash
pip install -r requirements.txt
```

### 3) Ingest the sample guides into the vector store
```bash
python -m apps.api.rag.ingest
```

This builds a Chroma store under `./vectorstore` from the Markdown files in `./data/guides`.

### 4) Run the API
```bash
uvicorn apps.api.main:app --reload
```

Open: http://127.0.0.1:8000/docs for Swagger.

### 5) Plan a trip
```bash
curl -X POST "http://127.0.0.1:8000/plan" -H "Content-Type: application/json" -d @- <<'JSON'
{
  "user": "yuval",
  "city": "Rome",
  "start_date": "2025-09-10",
  "end_date": "2025-09-12",
  "budget": 600,
  "currency": "USD",
  "interests": ["history", "food", "art"],
  "pace": "relaxed"
}
JSON
```

You’ll get:
- `finalized_plan` (Markdown)
- a generated `ics_path` you can download

### Optional: Ollama & OpenTripMap
- To use **Ollama**, set env vars:
  - `OLLAMA_MODEL=llama3.1:8b` (or another local model name)
- To use **OpenTripMap** for POIs:
  - Get a free key at https://opentripmap.io/
  - Set `OPENTRIPMAP_API_KEY=your_key`

### Project layout
```
apps/api/
  main.py        # FastAPI entry
  graph.py       # LangGraph state machine
  models/schemas.py
  tools/{weather.py,fx.py,calendar.py,trips.py}
  rag/{ingest.py,retriever.py}
  memory/long_term.py
data/guides/     # sample RAG data
vectorstore/     # created at runtime for Chroma persistence
```

## Talking points for interviews
- How LangGraph nodes & conditional edges orchestrate the workflow
- Why Chroma + sentence-transformers for local, zero-cost RAG
- Tool calling (weather/FX/POI) and guardrails (fallbacks if APIs fail)
- Memory: how user preference JSON is read back to bias planning
- Extension ideas: budget optimizer, multi-city routing, web UI, MCP bridge
