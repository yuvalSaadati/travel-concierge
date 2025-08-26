from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field

class TripRequest(BaseModel):
    user: str = "demo"
    city: str
    start_date: str  # YYYY-MM-DD
    end_date: str
    budget: float = 0.0
    currency: str = "USD"
    interests: List[str] = Field(default_factory=list)
    pace: str = "relaxed"  # or "packed"

class TripPlan(BaseModel):
    trip_id: str
    finalized_plan: str
    budget_breakdown: Dict[str, Any]
    ics_path: Optional[str] = None
    notes: Optional[List[str]] = None

class RetrievalChunk(BaseModel):
    content: str
    metadata: Dict[str, Any] = Field(default_factory=dict)
