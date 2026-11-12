RAW_PATH: str = "data/raw"
PROCESSED_PATH: str = "data/processed"
CHUNK_FILE: str = "chunks.json"
BM25_FOLDER: str = "bm25"
OVERLAP: float = 0.10
MAX_CHUNK_SIZE: int = 2000
WORD_ERROR: str = "WORD_ERROR"
CHUNK_ERROR: str = "CHUNK_ERROR"
SYSTEM_PROMPT: str = ("You answer questions about the vLLM codebase. Use "
                      "only the context below. If the context does not "
                      "contain the answer, say you don't know. Be brief and "
                      "name the source file you used")
MAX_CONTEXT: int = 32768
MAX_NEW_TOKENS: int = 512
