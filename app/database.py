import os
import logging
from motor.motor_asyncio import AsyncIOMotorClient
from datetime import datetime, timezone

# Setup clean internal logging for tracking db updates
logger = logging.getLogger("calle_db")
logging.basicConfig(level=logging.INFO)

# Default to local MongoDB port; easily changed to a cloud Atlas URI later via environment variables
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")

try:
    logger.info("Connecting to local MongoDB cluster...")
    client = AsyncIOMotorClient(MONGO_URI)
    
    # Establish our core database and collections
    db = client.calle_core
    calls_collection = db.support_calls
    logger.info("MongoDB Connection Interface initialized successfully.")
except Exception as e:
    logger.error(f"Critical failure initializing MongoDB connection: {e}")
    client = None
    db = None
    calls_collection = None

async def save_call_log(call_data: dict) -> str:
    """
    Asynchronously injects metadata and saves the full structural 
    call summary dictionary directly into the NoSQL cluster.
    """
    if calls_collection is None:
        logger.error("Database collection is offline. Cannot save record.")
        return None

    try:
        # Enforce exact UTC timestamp generation for accurate chronological indexing
        call_data["timestamp"] = datetime.now(timezone.utc)
        
        # Asynchronously stream the data payload straight to MongoDB
        result = await calls_collection.insert_one(call_data)
        
        inserted_id = str(result.inserted_id)
        logger.info(f"Successfully logged conversation data. Record ID: {inserted_id}")
        return inserted_id
        
    except Exception as e:
        logger.error(f"Database insertion crash occurred: {e}")
        return None