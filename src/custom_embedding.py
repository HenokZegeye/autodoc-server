import os
from typing import Any, List

from llama_index.embeddings.openai import OpenAIEmbedding
from openai import OpenAI
from llama_index.embeddings.openai.utils import create_retry_decorator
from itertools import islice
import tiktoken
import numpy as np


embedding_retry_decorator = create_retry_decorator(
    max_retries=6,
    random_exponential=True,
    stop_after_delay_seconds=60,
    min_seconds=1,
    max_seconds=20,
)



def batched(iterable, n):
    """Batch data into tuples of length n. The last batch may be shorter."""
    # batched('ABCDEFG', 3) --> ABC DEF G
    if n < 1:
        raise ValueError('n must be at least one')
    it = iter(iterable)
    while (batch := tuple(islice(it, n))):
        yield batch


@embedding_retry_decorator
def get_embedding_custom(client: OpenAI, tokens: str, engine: str, **kwargs: Any) -> List[float]:
    """Get embedding.

    NOTE: Copied from OpenAI's embedding utils:
    https://github.com/openai/openai-python/blob/main/openai/embeddings_utils.py

    Copied here to avoid importing unnecessary dependencies
    like matplotlib, plotly, scipy, sklearn.

    """
    return (
        client.embeddings.create(input=tokens, model=engine, **kwargs).data[0].embedding
    )

class CustomOpenAIEmbeddings(OpenAIEmbedding):

    def __init__(
        self,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)

    @classmethod
    def class_name(cls) -> str:
        return "customOpenAIEmbeddings"

    def _get_query_embedding(self, query: str) -> List[float]:
        """Get query embedding."""
        client = super()._get_client()
        max_tokens = os.environ['EMBEDDING_CTX_LENGTH']

        chunk_embeddings = []
        chunk_lens = []
        model=super()._query_engine
        for chunk in self.chunked_tokens(query, model, int(max_tokens)):
            chunk_embeddings.append(get_embedding_custom(client, chunk, engine = super()._query_engine))
            chunk_lens.append(len(chunk))

        chunk_embeddings = np.average(chunk_embeddings, axis=0, weights=chunk_lens)
        chunk_embeddings = chunk_embeddings / np.linalg.norm(chunk_embeddings)
        chunk_embeddings = chunk_embeddings.tolist()
        return chunk_embeddings
    
    def chunked_tokens(self, text, model, chunk_length):
        encoding = tiktoken.encoding_for_model(model)
        tokens = encoding.encode(text)
        chunks_iterator = batched(tokens, chunk_length)
        yield from chunks_iterator

    