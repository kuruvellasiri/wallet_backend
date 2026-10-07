from fastapi import FastAPI

from .database import engine, Base
from . import models
from .routes import router

Base.metadata.create_all(bind=engine)

app = FastAPI()

app.include_router(router)


@app.get("/")
def home():
    return {"message": "Wallet Backend is running"}