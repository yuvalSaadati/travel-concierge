from fastapi import FastAPI, HTTPException
from .models.schemas import TripRequest, TripPlan
from .graph import app_graph, TripState
from .rag.ingest import PERSIST_DIR
import os

app = FastAPI(title="Travel Concierge API", version="0.1.0")

@app.get("/health")
def health():
    return {"ok": True, "vectorstore_exists": os.path.exists(PERSIST_DIR)}

@app.post("/ingest")
def ingest_endpoint():
    # Run ingestion as a subroutine
    from .rag import ingest as ingest_mod
    ingest_mod.main()
    return {"status": "ok"}

@app.post("/plan", response_model=TripPlan)
def plan(req: TripRequest):
    if not os.path.exists(PERSIST_DIR):
        raise HTTPException(status_code=400, detail="Vector store not found. Run /ingest first.")

    # initial state
    state = TripState(**req.model_dump())

    # run the graph
    result = app_graph.invoke(state)

    # 🔧 normalize to TripState no matter what invoke returns
    if isinstance(result, TripState):
        final_state = result
    elif isinstance(result, dict):
        final_state = TripState(**result)
    else:
        # last resort: try to dump from any pydantic-like object
        final_state = TripState(**getattr(result, "model_dump", lambda: result)())

    return TripPlan(
        trip_id=final_state.trip_id or "na",
        finalized_plan=final_state.finalized_plan or "",
        budget_breakdown=final_state.budget_breakdown,
        ics_path=final_state.ics_path,
        notes=final_state.working_notes,
    )
