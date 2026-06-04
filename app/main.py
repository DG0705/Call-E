from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
import logging

# Local imports from our asynchronous architecture
from app.call_engine import run_support_call
from app.database import save_call_log

# Setup internal logger
logger = logging.getLogger("calle_main")

app = FastAPI(
    title="Call-E AI Support Core",
    description="Autonomous Voice Agent Engine replacing legacy call centers",
    version="1.1"
)

# Initialize templates folder for our eventual frontend dashboard integration
templates = Jinja2Templates(directory="templates")

# Pydantic schema for strict inbound validation (mimicking incoming webhooks)
class CallRequest(BaseModel):
    customer_name: str = "Customer"

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """
    Health dashboard route.
    Later, frontend will fetch data from MongoDB to populate this.
    """
    return templates.TemplateResponse("index.html", {"request": request, "customers": []})

@app.post("/start_call")
async def start_call(request: CallRequest):
    """
    Task 4 Core Endpoint (Fixed for MongoDB ObjectId Serialization):
    Triggers the autonomous voice agent, runs the conversation loop,
    and streams the structured payload safely to MongoDB.
    """
    try:
        logger.info(f"Initiating autonomous support session for: {request.customer_name}")
        
        # 1. Execute the async voice state machine loop
        call_summary = await run_support_call(customer_name=request.customer_name)
        
        # 2. Enrich payload with caller profile metrics
        call_summary["customer_name"] = request.customer_name
        
        # 3. Stream data asynchronously to local MongoDB instance
        inserted_id = await save_call_log(call_summary)
        
        # FIX: MongoDB adds a native '_id' of type ObjectId to the dict. 
        # Convert it to a plain string so FastAPI can serialize it back to the web browser.
        if "_id" in call_summary:
            call_summary["_id"] = str(call_summary["_id"])
        
        if inserted_id:
            logger.info(f"Session data successfully saved to MongoDB cluster. Document ID: {inserted_id}")
        else:
            logger.warning("Voice loop finished, but MongoDB save operation failed.")
            
        return {
            "status": "success",
            "message": "Call completed and successfully persisted in MongoDB.",
            "document_id": inserted_id,
            "summary": call_summary
        }
        
    except Exception as e:
        logger.error(f"Critical execution failure inside /start_call router: {e}")
        raise HTTPException(status_code=500, detail="Internal Voice Engine Runtime Error")