from typing import Optional
from pydantic import BaseModel
from sqlalchemy import Column, Integer, String, Boolean


class IndexPayload(BaseModel):
    path: str
    suffix: Optional[str] = None

class ChatPayload(BaseModel):
    mr_id: int
    question: str

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

# # Base.metadata.create_all(bind=engine)

# def get_db():
#     db = SessionLocal()
#     try:
#         yield db
#     finally:
#         db.close()