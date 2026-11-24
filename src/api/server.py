from fastapi import FastAPI, HTTPException
from fastapi.responses import RedirectResponse
from ..retrieval import load_index, retrieve_sources
from ..generation import read_sources, LLM
from ..parser import SearchArgs, AnswerArgs
from ..helpers import (Const, SearchResponse,
                       AnswerResponse)
import uuid


app = FastAPI()
retriever, chunk_list = load_index()
llm = LLM()


def check_k(k: int) -> None:
    """
    Reject a k larger than the number of chunks in the index.

    Args:
        k (int): The number of sources requested.

    Raises:
        HTTPException: With status 400 if k is too large.
    """
    if k > len(chunk_list):
        raise HTTPException(status_code=400,
                            detail=f"k={k} is larger than the "
                                   f"{len(chunk_list)} chunks in the index")


def warning_message(warning: str | None) -> str | None:
    """
    Turn a retrieval warning code into a readable sentence.

    Args:
        warning (str | None): The code returned by retrieve_sources.

    Returns:
        str | None: The sentence, or None when there is no warning.
    """
    if warning == Const.WORD_ERROR:
        return "The question has no searchable words"
    if warning == Const.CHUNK_ERROR:
        return "No chunk matches this question"
    return None


@app.get("/", include_in_schema=False)
def home() -> RedirectResponse:
    """Send a browser opening the base address to the /docs page."""
    return RedirectResponse("/docs")


@app.post("/search")
def search(args: SearchArgs) -> SearchResponse:
    """Return the top-k sources for one query."""
    check_k(args.k)
    sources, warning = retrieve_sources(args.query, args.k,
                                        retriever, chunk_list)

    return SearchResponse(question_id=str(uuid.uuid4()),
                          question=args.query,
                          retrieved_sources=sources,
                          warning=warning_message(warning))


@app.post("/answer")
def answer(args: AnswerArgs) -> AnswerResponse:
    """Retrieve the top-k sources for one query and answer it."""
    check_k(args.k)
    sources, warning = retrieve_sources(args.query, args.k,
                                        retriever, chunk_list)

    message = warning_message(warning)
    if message is not None:
        return AnswerResponse(question_id=str(uuid.uuid4()),
                              question=args.query,
                              retrieved_sources=sources,
                              answer=message,
                              warning=message)

    texts = read_sources(sources)
    response = llm.generate_response(args.query, sources, texts)

    return AnswerResponse(question_id=str(uuid.uuid4()),
                          question=args.query,
                          retrieved_sources=sources,
                          answer=response)
