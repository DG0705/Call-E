"""FastAPI application for the call-orchestrator service."""

from call_e_shared import create_app


app = create_app("call-orchestrator")
