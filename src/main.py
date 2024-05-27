from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from src.config import set_llm_model, set_embed_model
from dotenv import load_dotenv


app = FastAPI()

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
