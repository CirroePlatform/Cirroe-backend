import os
from fastapi import FastAPI, BackgroundTasks
from pydantic import BaseModel
from dotenv import load_dotenv
import uvicorn

from src.server.wrappers import query_wrapper, deploy_wrapper

load_dotenv()

app = FastAPI()

DEV_MOCK_MSG="Nothing to see here from this query. This is dev, switch to prod domain for actual testing"

# Define request models
class QueryRequest(BaseModel):
    user_query: str
    user_id: int
    chat_session_id: int

class DeployRequest(BaseModel):
    user_id: int
    chat_session_id: int

# Synchronous endpoints
@app.post("/query")
def query(request: QueryRequest):
    return {"result": DEV_MOCK_MSG}

@app.post("/deploy")
def deploy(request: DeployRequest):
    return {"result": DEV_MOCK_MSG}

# Asynchronous endpoints
@app.post("/query_async")
async def query_async(request: QueryRequest, background_tasks: BackgroundTasks):
    # background_tasks.add_task(query_wrapper, request.user_query, request.user_id, request.chat_session_id)
    return {"status": "Query task has been started in the background (not really. This is dev)"}

@app.post("/deploy_async")
async def deploy_async(request: DeployRequest, background_tasks: BackgroundTasks):
    background_tasks.add_task(deploy_wrapper, request.user_id, request.chat_session_id)
    return {"status": "Deploy task has been started in the background (not really. This is dev)"}

# Main entry point to run the server
if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)