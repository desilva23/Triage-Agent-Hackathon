from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import sys
import os

# Ensure the code directory is in the path so imports work
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from agent import SupportAgent

app = FastAPI(title="Support Triage API")

# Configure CORS for the frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all for local dev
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize the agent once
agent = SupportAgent()

class IssueRequest(BaseModel):
    issue_text: str
    subject: str = "Support Ticket"
    company: str = "Unknown"
    history: list = []

from fastapi.responses import StreamingResponse
import json
import asyncio

@app.post("/chat")
async def chat(req: IssueRequest):
    def event_generator():
        try:
            # Run the generator from the agent with history
            for event in agent.process_issue_stream(req.issue_text, req.subject, req.company, history=req.history):
                yield json.dumps(event) + "\n"
        except Exception as e:
            yield json.dumps({"type": "error", "message": str(e)}) + "\n"

    return StreamingResponse(event_generator(), media_type="application/x-ndjson")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
