from fastapi import FastAPI
import uvicorn

from app.api.v1.auth import router as auth_router


app = FastAPI(title="ReSort")
app.include_router(auth_router, prefix="/api/v1")


if __name__ == "__main__":
     uvicorn.run("main:app", reload=True)
