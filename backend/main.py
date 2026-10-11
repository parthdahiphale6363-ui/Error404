"""FastAPI Application for Risk Radar Scoreboard.

Strict architectural guard:
- Frontend communicates ONLY with FastAPI.
- FastAPI reads only from local models/database, never directly calling external APIs.
- External calls are encapsulated exclusively inside backend/apigateway/.
"""

import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.api import router as api_router

app = FastAPI(
    title="Corporate Risk Radar API",
    description="Automated Corporate Risk Radar (Fintech PS 01)",
    version="0.1.0",
)

# Enable CORS for dashboard UI
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount API Router containing all contract endpoints
app.include_router(api_router)


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("backend.main:app", host="0.0.0.0", port=port, reload=True)
