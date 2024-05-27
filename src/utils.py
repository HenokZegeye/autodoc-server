import os
import pdb
from fastapi import HTTPException
from llama_index.core.schema import Document
from llama_index.core.node_parser import SentenceSplitter
import requests

from src.config import get_headers
from llama_index.core import SimpleDirectoryReader, Settings, VectorStoreIndex, StorageContext, load_index_from_storage, SummaryIndex

from src.mdx_docs_reader import MdxDocsReader
from IPython.display import Markdown, display
from llama_index.core import PromptTemplate
import difflib
import tiktoken




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
    def should_exclude_file(file_path):
        if file_path.split('.')[-1] in os.environ['CODE_CHANGE_EXCLUDE_FILE_EXT']:
            return True
        for folder_path in os.environ['CODE_CHANGE_EXCLUDE_FOLDER_PATHS'].split(','):
            if folder_path in file_path.split('/'):
                return True
        return False
    return [change for change in changes if not should_exclude_file(change['new_path'])]


def create_documents(changes):
    return [Document(
            text=change['diff'],
            metadata={
                "new_path": change['new_path'],
                "old_path": change['new_path'],
                "new_file": change['new_file'],
                "renamed_file": change['renamed_file'],
                "deleted_file": change['deleted_file'],
            },
    ) for change in changes]
    

def format_mr_changes(changes, mr_id):
    line = ''
    for change in changes:
            # Extract non-diff attributes and format them as a CSV
            non_diff_attrs = f"old_path: {change['old_path']}, new_path: {change['new_path']}, new_file: {change['new_file']}, renamed_file: {change['renamed_file']}, deleted_file: {change['deleted_file']}"
            
            # Combine with the diff
            line = f"{line} \n\n {non_diff_attrs}\n diff: {change['diff']}"
    
    with open(f'data/mr-changes/{mr_id}.txt', 'w') as file:
         file.write(line)

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



def load_mdx_docs(filepath):
    return SimpleDirectoryReader(
        input_dir=filepath,
        file_extractor={'.mdx': MdxDocsReader(base_path=filepath)},
        recursive=True,
    ).load_data()


# Load Code docs
def load_code_data(filepath):
    return SimpleDirectoryReader(
        input_dir=filepath,
        exclude_hidden=True,
        required_exts=['.py'],
        recursive=True,
    ).load_data()


def add_index(documents, persist_dir):
    index = VectorStoreIndex.from_documents(documents)
    index.storage_context.persist(persist_dir=persist_dir)
    return index


def prepend_emotion_prompt(stimuli_str, query_engine):
    QA_PROMPT_KEY = "response_synthesizer:text_qa_template"
    qa_tmpl_str = """\
        Context information is below. 
        ---------------------
        {context_str}
        ---------------------
        Given the context information and not prior knowledge, \
        answer the query.
        {stimuli_str}
        Query: {query_str}
        Answer: \
    """

    qa_tmpl = PromptTemplate(qa_tmpl_str)
    partial_prompt_tmpl = qa_tmpl.partial_format(stimuli_str=stimuli_str)
    query_engine.update_prompts({QA_PROMPT_KEY: partial_prompt_tmpl})
    return query_engine.get_prompts()





# Improve the metadata Information
def refine_metadata_format(docs):
    text_template = "Content Metadata:\n{metadata_str}\n\nContent:\n{content}"

    metadata_template = "{key}: {value},"
    metadata_seperator= " "

    for doc in docs:
        doc.text_template = text_template
        doc.metadata_template = metadata_template
        doc.metadata_seperator = metadata_seperator
        doc.excluded_llm_metadata_keys = ['File Name', 'Links', 'file_path', 'file_name', 'file_size', 'creation_date', 'last_modified_date']
        doc.excluded_embed_metadata_keys = ['File Name', 'Links', 'file_path', 'file_name', 'file_size', 'creation_date', 'last_modified_date']

# Improve the metadata Information
def refine_code_metadata_format(premr_path, postmr_path, premr_code, postmr_code):
    def add_short_path(doc, path, type):
        doc.metadata['Short Path'] = doc.metadata['file_name'].split(path)[-1]
        doc.metadata['type'] = type
        return doc
    premr_code = list(map(lambda doc: add_short_path(doc, premr_path, 'before-new-merge-request'),premr_code))
    postmr_code = list(map(lambda doc: add_short_path(doc, postmr_path, 'after-new-merge-request'),postmr_code))

def load_doc(path: str):
    full_path = f'data/{path}'
    return SimpleDirectoryReader(input_dir=full_path, recursive=True).load_data()




def create_summary_index(documents, persist_dir):
    node_parser = SentenceSplitter(chunk_size=1024, chunk_overlap=20)
    nodes = node_parser.get_nodes_from_documents(documents)
    storage_context = StorageContext.from_defaults()
    storage_context.docstore.add_documents(nodes)
    summary_index = SummaryIndex(nodes, storage_context=storage_context)
    summary_index.storage_context.persist(persist_dir=persist_dir)
    return summary_index

def create_summary_engine(summary_index):
    summary_query_engine = summary_index.as_query_engine(
        response_mode="tree_summarize",
        use_async=True,
        streaming=True
    )
    return summary_query_engine



# define prompt viewing function
def display_prompt_dict(prompts_dict):
    for k, p in prompts_dict.items():
        text_md = f"**Prompt Key**: {k}" f"**Text:** "
        display(Markdown(text_md))
        print(p.get_template())
        display(Markdown(""))

def compare_folders(folder1, folder2):
    diffs = []
    extensions = ['.py']
    for root, dirs, files in os.walk(folder1):
        rel_path = os.path.relpath(root, folder1)
        for file in files:
            if extensions and not file.endswith(tuple(extensions)):
                continue
            file1 = os.path.join(root, file)
            file2 = os.path.join(folder2, rel_path, file)
            if os.path.exists(file2):
                with open(file1, 'r') as f1, open(file2, 'r') as f2:
                    diff = difflib.unified_diff(f1.readlines(), f2.readlines(), fromfile=file1, tofile=file2)
                    diffs.extend(diff)
    return diffs



def num_tokens(prompt):
    encoding = tiktoken.encoding_for_model("gpt-3.5-turbo")
    return len(encoding.encode(prompt))