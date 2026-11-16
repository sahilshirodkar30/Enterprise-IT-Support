from fastapi import Depends,FastAPI,Header,HTTPException,Request,status
from pydantic import BaseModel,Field
import logfire


app = FastAPI(title="Enterprise IT Support",description="An enterprise IT support system that leverages AI and vector databases to provide efficient and accurate solutions to IT-related issues.",version="1.0.0")

@app.on_event("startup")
async def startup_event():
    from app.observability import configure_observability
    configure_observability()
    logfire.info("Application startup complete")

