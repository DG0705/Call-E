from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
import logging

# Local imports
from app.call_engine import run_support_call
from app.database import save_call_log, engine
from app import models

# Generate SQLite tables on startup if they don't exist
models.Base.metadata.create_all(bind=engine)

# Setup internal logger
logger = logging.getLogger("calle_main")

app = FastAPI(
    title="Call-E AI Support Core",
    description="Autonomous Voice Agent Engine replacing legacy call centers",
    version="1.1"
)

# Initialize templates folder
templates = Jinja2Templates(directory="templates")

# Pydantic schema for strict inbound validation
class CallRequest(BaseModel):
    customer_name: str = "Customer"

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """Health dashboard route."""
    return templates.TemplateResponse(
        request=request, 
        name="index.html", 
        context={"customers": []}
    )

@app.post("/start_call")
async def start_call(request: CallRequest):
    """
    Triggers the autonomous voice agent and saves to SQLite.
    """
    try:
        logger.info(f"Initiating autonomous support session for: {request.customer_name}")
        
        # 1. Execute the async voice state machine loop
        call_summary = await run_support_call(customer_name=request.customer_name)
        
        # 2. Extract metrics and save to SQLite
        inserted_id = await save_call_log(
            customer_name=request.customer_name,
            status=call_summary["status"],
            final_sentiment=call_summary["final_sentiment"],
            turns=call_summary["turns"],
            transcript=call_summary["history"]
        )
        
        if inserted_id:
            logger.info(f"Session data successfully saved to SQLite. Record ID: {inserted_id}")
            call_summary["database_id"] = inserted_id
        else:
            logger.warning("Voice loop finished, but SQLite save operation failed.")
            
        return {
            "status": "success",
            "message": "Call completed and successfully persisted in database.",
            "summary": call_summary
        }
        
    except Exception as e:
        logger.error(f"Critical execution failure inside /start_call router: {e}")
        raise HTTPException(status_code=500, detail="Internal Voice Engine Runtime Error")