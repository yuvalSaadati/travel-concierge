import os, uuid, math
from typing import List, Dict, Any
from langgraph.graph import StateGraph, START, END
from pydantic import BaseModel
from .rag.retriever import retriever
from .tools import weather as weather_tool
from .tools import fx as fx_tool
from .tools import trips as trips_tool
from .tools import calendar as ics_tool
from .memory import long_term as memory

from langchain.schema import HumanMessage, SystemMessage
from dotenv import load_dotenv
load_dotenv()  # now os.getenv("GROQ_API_KEY") works

class TripState(BaseModel):
    user: str
    city: str
    start_date: str
    end_date: str
    budget: float
    currency: str
    interests: List[str] = []
    pace: str = "relaxed"
    working_notes: List[str] = []
    candidate_plan: str | None = None
    budget_breakdown: Dict[str, Any] = {}
    critiques: List[str] = []
    finalized_plan: str | None = None
    trip_id: str | None = None
    ics_path: str | None = None

def _days(start: str, end: str) -> int:
    # Computes the inclusive number of days between two ISO dates
    from datetime import date
    s = date.fromisoformat(start); e = date.fromisoformat(end)
    return max((e - s).days + 1, 1)

def _rule_based_plan(city: str, days: int, pois: List[str], weather_lines: List[str]) -> str:
    # Generate a daily travel itinerary that includes:
    # A set number of POIs (Points of Interest) per day
    # The weather forecast for each day
    
    per_day = max(3, min(6, math.ceil(len(pois)/max(days,1)))) if pois else 4 # How many POIs to schedule per day
    lines = [f"# Itinerary for {city}", ""]
    idx = 0
    for d in range(days):
        lines.append(f"Day {d+1}:")
        for _ in range(per_day):
            if idx < len(pois):
                lines.append(f"- {pois[idx]}")
                idx += 1
        if weather_lines:
            lines.append(f"- Weather: {weather_lines[min(d, len(weather_lines)-1)]}")
        lines.append("")
    return "\n".join(lines)

# Nodes
def research_destinations(state: TripState) -> TripState:
    prefs = memory.get_prefs(state.user)
    if prefs:
        state.working_notes.append(f"Loaded user prefs: {prefs}")
        # optionally merge interests
        interests = set(state.interests or [])
        interests |= set(prefs.get("interests", []))
        state.interests = list(interests)

    chunks = retriever.search(state.city, state.interests, k=10)
    top = [c["content"].splitlines()[0].replace("#","").strip() for c in chunks[:12]]

    # Weather
    w = weather_tool.get_weather(state.city, state.start_date, state.end_date)
    wbrief = weather_tool.weather_brief(w).splitlines()[1:]  # skip "Forecast:"
    state.working_notes.append("RAG results gathered")
    state.working_notes += [f"POI candidates: {', '.join(top[:10])}"]

    # Optional: external POIs
    pois = []
    try:
        pois = trips_tool.list_poi(state.city, limit=10) or []
    except Exception as e:
        print("Error:", type(e).__name__, "-", e)
        pois = []

    # Combine POIs
    poi_list = [p for p in top if p]  # from RAG headings
    for p in pois:
        if p and p not in poi_list:
            poi_list.append(p)

    # FX estimate (if user currency not local; we'll skip local detection)
    est_local_budget, rate = fx_tool.convert(state.budget, state.currency, state.currency)
    state.budget_breakdown = {"budget_input": state.budget, "currency": state.currency, "fx_rate": rate}

    # store interim
    state.working_notes.append(f"Weather lines: {wbrief[:3]}")
    state.working_notes.append(f"Total POIs considered: {len(poi_list)}")
    state.working_notes.append(f"FX rate: {rate}")
    state.working_notes.append(f"Budget (input): {state.budget} {state.currency}")

    # stash for planner
    state.candidate_plan = _rule_based_plan(state.city, _days(state.start_date, state.end_date), poi_list, wbrief)
    return state

def draft_itinerary(state: TripState) -> TripState:
    messages = [
        SystemMessage(content="You are a travel planner. Produce concise, feasible day-by-day itineraries."),
        HumanMessage(content=f"City: {state.city}\nDates: {state.start_date} to {state.end_date}\n"
                                f"Pace: {state.pace}\nInterests: {', '.join(state.interests)}\n"
                                f"Draft based on notes:\n{state.candidate_plan}")
    ]
    try:
        from langchain_groq import ChatGroq
        llm = ChatGroq(model="llama-3.1-8b-instant")  # uses GROQ_API_KEY
        res = llm.invoke(messages)                      # returns AIMessage
        state.candidate_plan = res.content
    except Exception as e:
        state.working_notes.append(f"llama failed: {e}; using rule-based plan.")
    return state

def budget_check(state: TripState) -> TripState:
    days = _days(state.start_date, state.end_date)
    # naive budgeting
    per_day = 120 if state.pace == "packed" else 90
    total = per_day * days
    state.budget_breakdown.update({"days": days, "estimated_total": total, "estimated_per_day": per_day})
    return state

def critic_review(state: TripState) -> TripState:
    issues = []
    # simple heuristic: too many lines under any "Day" (>8 items)
    for block in state.candidate_plan.split("\n\n"):
        if block.lower().startswith("day "):
            items = [l for l in block.splitlines() if l.strip().startswith("- ")]
            if len(items) > 8:
                issues.append("Some days are overpacked (>8 items).")
    state.critiques = issues
    return state

def revise_plan(state: TripState) -> TripState:
    if not state.critiques:
        return state
    # very naive: drop last item from each day’s block
    lines = []
    for block in state.candidate_plan.split("\n\n"):
        if block.lower().startswith("day "):
            items = [l for l in block.splitlines() if l.strip().startswith("- ")]
            if len(items) > 8:
                items = items[:-1]
                lines.append("\n".join([block.splitlines()[0]] + items))
            else:
                lines.append(block)
        else:
            lines.append(block)
    state.candidate_plan = "\n\n".join(lines)
    return state

def finalize(state: TripState) -> TripState:
    state.finalized_plan = state.candidate_plan
    state.trip_id = str(uuid.uuid4())[:8]
    days = _days(state.start_date, state.end_date)
    state.ics_path = ics_tool.make_ics(state.finalized_plan, state.city, state.start_date, days)
    # write memory
    memory.upsert_prefs(state.user, {"interests": state.interests, "pace": state.pace})
    return state

# Build graph
graph = StateGraph(TripState)
graph.add_node("research", research_destinations)
graph.add_node("plan", draft_itinerary)
graph.add_node("budget", budget_check)
graph.add_node("critic", critic_review)
graph.add_node("revise", revise_plan)
graph.add_node("finalize", finalize)

graph.add_edge(START, "research")
graph.add_edge("research", "plan")
graph.add_edge("plan", "budget")
graph.add_edge("budget", "critic")

def _route(state: TripState):
    return "revise" if state.critiques else "finalize"

graph.add_conditional_edges("critic", _route, {"revise": "revise", "finalize": "finalize"})
graph.add_edge("revise", "finalize")
graph.add_edge("finalize", END)

app_graph = graph.compile()
