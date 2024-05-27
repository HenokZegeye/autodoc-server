import subprocess
from typing import List, Optional
from fastapi import Body, Depends, FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import requests
from sqlalchemy import Column, Integer, String, Boolean
from main import load_doc, add_index, create_summary_index, create_summary_engine
import os
from dotenv import load_dotenv
from sqlalchemy.orm import Session
from llama_index.core import Document
from llama_index.core.schema import MetadataMode
from llama_index.core import StorageContext, load_index_from_storage, Settings
from llama_index.llms.openai import OpenAI
from llama_index.embeddings.openai import OpenAIEmbedding
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
import nest_asyncio
from llama_index.core import SimpleDirectoryReader
from llama_index.llms.fireworks import Fireworks
from default_prompts import get_default_updated_doc_prompt, DEFAULT_SUMMARY_PROMPT


load_dotenv()

Settings.llm = OpenAI(temperature=0, model="gpt-3.5-turbo")
Settings.embed_model = OpenAIEmbedding(model="text-embedding-3-large")



# class MergeRequestChange(Base):
#     __tablename__ = "merge_request_changes"
#     id= Column(Integer, primary_key=True, index=True)
#     old_path= Column(String, nullable=False)
#     new_path= Column(String, nullable=False)
#     new_file= Column(Boolean, nullable=False)
#     renamed_file= Column(Boolean, nullable=False)
#     deleted_file= Column(Boolean, nullable=False)
#     diff= Column(String, nullable=False)
#     exclude= Column(Boolean, nullable=False)

# Base.metadata.create_all(bind=engine)

# Models
class IndexPayload(BaseModel):
    path: str
    suffix: Optional[str] = None

class PromptPayload(BaseModel):
    mr_id: int
    prompt_text: Optional[str] = None

class MrChangeResponse(BaseModel):
    old_path: str
    new_path: str
    new_file: bool
    renamed_file: bool
    deleted_file: bool
    diff: str
    exclude: bool

class MergeRequestResponse(BaseModel):
    id: int
    iid: int
    title: str
    author: str
    created_at: str
    state: str

app = FastAPI()

origins = ["*"]

def get_headers():
    return {
        "Authorization": f"Bearer {os.environ['GITLAB_ACCESS_TOKEN']}"
    } if os.environ['GITLAB_ACCESS_TOKEN'] else {}

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# def get_db():
#     db = SessionLocal()
#     try:
#         yield db
#     finally:
#         db.close()

@app.get("/")
def read_root():
    return {"Server is running"}


# @app.get("/mrs", response_model=None)
# def get_mrs(db: Session = Depends(get_db)):
#     items = db.query(MergeRequestChange).all()
#     return items



@app.get("/open_merge_requests", response_model=list[MergeRequestResponse])
def get_open_merge_requests():
    headers = get_headers()

    mr_url = f"{os.environ['GITLAB_API_BASE_URL']}/projects/{os.environ['GITLAB_PROJECT_ID']}/merge_requests?state=opened"
    
    response = requests.get(mr_url, headers=headers)

    if response.status_code != 200:
        raise HTTPException(status_code=response.status_code, detail="Failed to fetch merge requests")

    merge_requests = response.json()

    return [
        MergeRequestResponse(
            id=mr["id"],
            iid=mr["iid"],
            title=mr["title"],
            author=mr["author"]["name"],
            created_at=mr["created_at"],
            state=mr["state"]
        )
        for mr in merge_requests
    ]

            
@app.post("/setup")
def setup(bg_tasks: BackgroundTasks=[]):
    try:
        subprocess.run(['bash', 'setup.sh'], check=True)
        path = f"../data/{os.environ['DOC_TARGET_FOLDER']}"
        docs = load_docs(path)
        bg_tasks.add_task(add_index, docs, '../Indexes/doc_index', select_embed_model())
        return {"message": f"Setup Successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to setup: {e}")


@app.post("/summary")
def get_summary(data: PromptPayload):
    path = f'../Indexes/Summary/{data.mr_id}'
    index = load_index_from_storage(StorageContext.from_defaults(persist_dir=path))
    summary_engine = create_summary_engine(index)
    prompt = data.prompt_text if data.prompt_text else DEFAULT_SUMMARY_PROMPT
    print("Prompt String", prompt)
    response = summary_engine.query(prompt)
    return response



@app.post("/get_updated_documentation")
def get_updated_documentation(data: PromptPayload):
    path = f"../Indexes/Docs/{os.environ['EMD_MODEL_PROVIDER']}"
    index = load_index_from_storage(StorageContext.from_defaults(persist_dir=path))
    query_engine = index.as_query_engine(llm=select_llm_model())
    with open(f'../MrChanges/{data.mr_id}.txt') as file:
        mr_changes = file.read()
    prompt = data.prompt_text if data.prompt_text else get_default_updated_doc_prompt(mr_changes)
    print("Prompt String", prompt)
    response = query_engine.query(prompt)
    return response




@app.get("/merge_request_changes", response_model=list[MrChangeResponse])
def get_merge_request_changes(mr_id: int, bg_tasks: BackgroundTasks=[]):
    merge_request_changes = fetch_mrchanges_from_gitlab(mr_id)['changes']
    filtered_changes = get_filtered_changes(merge_request_changes)
    format_mr_changes(filtered_changes, mr_id)
    documents = create_documents(merge_request_changes)
    bg_tasks.add_task(create_summary_index, documents, f'../Indexes/Summary/{mr_id}')
    
    return [
        MrChangeResponse(
            old_path=mr_change["old_path"],
            new_path=mr_change["new_path"],
            new_file=mr_change["new_file"],
            renamed_file=mr_change["renamed_file"],
            deleted_file=mr_change["deleted_file"],
            diff=mr_change['diff'],
            exclude=False
        )
        for mr_change in merge_request_changes
    ]



@app.post('/create_index')
async def create_index(data:IndexPayload, bg_tasks: BackgroundTasks=[]):
    try:
        docs = load_doc(data.path)
        persist_path = f'../Indexes/doc_index_{data.suffix}' if data.suffix else '../Indexes/doc_index'
        bg_tasks.add_task(add_index, docs, persist_path)
        return {"message": f"Index created successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create index: {e}")


def fetch_mrchanges_from_gitlab(mr_id: int):
    headers = get_headers()

    changes_url = f"{os.environ['GITLAB_API_BASE_URL']}/projects/{os.environ['GITLAB_PROJECT_ID']}/merge_requests/{mr_id}/changes"
    
    response = requests.get(changes_url, headers=headers)

    if response.status_code != 200:
        raise HTTPException(status_code=response.status_code, detail="Failed to fetch merge request changes")
    
    return response.json()



# Add a method that responds to a refresh button from the client
# Usually the summary index will be created once and it will be used for summary
# But if there are new changes included to an open MR then a refresh button should trigger and re-index it
# Alternative solution will be to schedule a background job that fetches a new update


def get_filtered_changes(changes):
    exclude_list = ['examples/device-status.py', 'integration_tests/test_slice.py', 'tests/test_slice_mock.py', 'poetry.lock', 'pyproject.toml']
    return [
        change
        for change in changes
        if change["new_path"] not in exclude_list
    ]



def create_documents(changes):
    filtered_changes = get_filtered_changes(changes)
    return [Document(
            text=change['diff'],
            metadata={
                "new_path": change['new_path'],
                "old_path": change['new_path'],
                "new_file": change['new_file'],
                "renamed_file": change['renamed_file'],
                "deleted_file": change['deleted_file'],
            },
    ) for change in filtered_changes]
    

def format_mr_changes(changes, mr_id):
    line = ''
    for change in changes:
            # Extract non-diff attributes and format them as a CSV
            non_diff_attrs = f"old_path: {change['old_path']}, new_path: {change['new_path']}, new_file: {change['new_file']}, renamed_file: {change['renamed_file']}, deleted_file: {change['deleted_file']}"
            
            # Combine with the diff
            line = f"{line} \n\n {non_diff_attrs}\n diff: {change['diff']}"
    
    with open(f'../MrChanges/{mr_id}.txt', 'w') as file:
         file.write(line)

def clone_repository():
    try:
        subprocess.run(['bash', 'setup.sh'], check=True)
    except subprocess.CalledProcessError as e:
        raise Exception(detail=f"Failed to clone repository: {e}")


def load_docs(path):
    exclude_list = [f"{path}{p}" for p in os.environ['DOC_EXCLUDE_FILE_PATHS'].split(',')]
    reader = SimpleDirectoryReader(input_dir=path,recursive=True)
    flattened_docs = [doc for docs in reader.iter_data() for doc in docs]
    exclude_file_paths_resolved = [os.path.abspath(path) for path in exclude_list]
    filtered_docs = [
        doc for doc in flattened_docs
        if os.path.abspath(doc.metadata["file_path"]) not in exclude_file_paths_resolved
    ]
    return filtered_docs



def select_embed_model():
    provider = os.environ['EMD_MODEL_PROVIDER']
    emd_model = os.environ['EMD_MODEL']
    if provider == 'OpenAI':
        return OpenAIEmbedding(model=emd_model)
    elif provider == 'Huggingface':
        return HuggingFaceEmbedding(model_name=emd_model)
    

def select_llm_model():
    provider = os.environ['LLM_MODEL_PROVIDER']
    llm_model = os.environ['LLM_MODEL']
    if provider == 'OpenAI':
        return OpenAI(model=llm_model, temperature=0)
    elif provider == 'Fireworks':
        return Fireworks(model =  llm_model,temperature = 0)