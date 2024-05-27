import os
from llama_index.core import Settings
from llama_index.embeddings.openai import OpenAIEmbedding
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
import httpx
from llama_index.llms.openai import OpenAI 
from llama_index.llms.fireworks import Fireworks
from src.custom_embedding import CustomOpenAIEmbeddings


def set_embed_model():
    provider = os.environ['EMD_MODEL_PROVIDER']
    emd_model = os.environ['EMD_MODEL']
    proxy = os.environ['PROXY']
    if provider == 'OpenAI':
        if proxy:
            Settings.embed_model = CustomOpenAIEmbeddings(model=emd_model, http_client=httpx.Client(proxy=proxy))
        else:
            Settings.embed_model = CustomOpenAIEmbeddings(model=emd_model)
    elif provider == 'Huggingface':
        return HuggingFaceEmbedding(model_name=emd_model)
    

def set_llm_model():
    provider = os.environ['LLM_MODEL_PROVIDER']
    llm_model = os.environ['LLM_MODEL']
    proxy = os.environ['PROXY']
    if provider == 'OpenAI':
        if proxy:
            Settings.llm = OpenAI(model=llm_model, temperature=0, http_client=httpx.Client(proxy=proxy))
        else:
            Settings.llm = OpenAI(model=llm_model, temperature=0) 
    elif provider == 'Fireworks':
        Settings.llm = Fireworks(model =  llm_model,temperature = 0)


def get_headers():
    return {
        "Authorization": f"Bearer {os.environ['GITLAB_ACCESS_TOKEN']}"
    } if os.environ['GITLAB_ACCESS_TOKEN'] else {}