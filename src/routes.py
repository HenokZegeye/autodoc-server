from fastapi import HTTPException, BackgroundTasks
from fastapi.responses import StreamingResponse
import requests
import os
from llama_index.core import StorageContext, load_index_from_storage

from src.default_prompts import get_default_updated_doc_prompt, DEFAULT_SUMMARY_PROMPT
from src.config import get_headers
from src.models import ChatPayload, MergeRequestResponse, MrChangeResponse, PromptPayload
from src.utils import add_index, create_documents, create_summary_engine, create_summary_index, fetch_mrchanges_from_gitlab, format_mr_changes, get_filtered_changes, load_docs
from src.main import app
from src.store_doc_repo import clone_and_replace


# Routes

@app.get("/")
def read_root():
    return {"Server is running, Hello"}

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
        clone_and_replace()
        path = f"../data/documentation/{os.environ['DOC_TARGET_FOLDER']}"
        docs = load_docs(path)
        bg_tasks.add_task(add_index, docs, f'../indexes/docs')
        return {"message": f"Documentation Setup Successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to setup: {e}")


@app.post("/summary")
async def get_summary(data: PromptPayload):
    path = f'../indexes/mr-change-summary/{data.mr_id}'
    index = load_index_from_storage(StorageContext.from_defaults(persist_dir=path))
    summary_engine = create_summary_engine(index)
    prompt = data.prompt_text if data.prompt_text else DEFAULT_SUMMARY_PROMPT
    print("Prompt String", prompt)
    response = summary_engine.query(prompt)
    return StreamingResponse(response.response_gen, media_type='text/event-stream')


@app.post("/mrchat")
async def mr_chat(data: ChatPayload):
    path = f'../indexes/mr-change-summary/{data.mr_id}'
    index = load_index_from_storage(StorageContext.from_defaults(persist_dir=path))
    chat_engine = index.as_chat_engine()
    print("Question String", data.question)
    response = chat_engine.stream_chat(data.question)
    return StreamingResponse(response.response_gen, media_type='text/event-stream')


@app.post("/get_updated_documentation")
def get_updated_documentation(data: PromptPayload):
    path = f"../indexes/docs"
    index = load_index_from_storage(StorageContext.from_defaults(persist_dir=path))
    query_engine = index.as_query_engine(streaming=True)
    
    with open(f'../data/mr-changes/{data.mr_id}.txt') as file:
        mr_changes = file.read()
    prompt = data.prompt_text if data.prompt_text else get_default_updated_doc_prompt(mr_changes)
    print("Prompt String", prompt)
    try:
        response = query_engine.query(prompt)
        return StreamingResponse(response.response_gen, media_type='text/event-stream')
    except Exception as e:
        return HTTPException(status_code=500, detail=e)


@app.get("/merge_request_changes", response_model=list[MrChangeResponse])
def get_merge_request_changes(mr_id: int, bg_tasks: BackgroundTasks=[]):
    merge_request_changes = fetch_mrchanges_from_gitlab(mr_id)['changes']
    filtered_changes = get_filtered_changes(merge_request_changes)
    format_mr_changes(filtered_changes, mr_id)
    documents = create_documents(filtered_changes)
    bg_tasks.add_task(create_summary_index, documents, f'../indexes/mr-change-summary/{mr_id}')
    
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
        for mr_change in filtered_changes
    ]
