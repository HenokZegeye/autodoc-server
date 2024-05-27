from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from src.config import set_llm_model, set_embed_model
from dotenv import load_dotenv
from contextlib import asynccontextmanager
import os


directories_to_create = [
    "data/documentation",
    "data/mr-changes",
    "indexes/docs",
    "indexes/mr-change-summary"
]

@asynccontextmanager
async def lifespan(app):
    for directory in directories_to_create:
        os.makedirs(directory, exist_ok=True)
        print(f"Directory {directory} created or already exists.")
    yield

app = FastAPI(lifespan=lifespan)


origins = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

load_dotenv()
set_llm_model()
set_embed_model()



import src.routes
