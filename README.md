*This project has been created as part of the 42 curriculum by mbotelho.*

# Rage Against the Machine

Implementation of Retrieval-Augmented Generation over the vLLM codebase.

## Description

Retrieval-Augmented Generation (RAG) is an AI approach that combines searching for relevant information with generating a response. In RAG, external sources - such as documents or databases - are provided to a model so it can produce a better, more grounded answer, instead of relying only on what it learned during training.

This project builds a RAG system that answers questions about the [vLLM](https://vllm.ai/) repository (version 0.10.1). Given a question, it finds the most relevant pieces of the codebase and documentation, and passes them to a small local language model, `Qwen/Qwen3-0.6B`, which writes an answer based on them.

The pipeline has four stages:

1. **Indexing** - read every `.py`, `.md` and `.txt` file under `data/raw/`, split each one into chunks, and save a searchable index under `data/processed/`.
2. **Retrieval** - match a question against the index with BM25 and return the top-k chunks as source locations (file path + character range).
3. **Augmentation** - read the text of those sources and place it in the model's prompt, within its token budget.
4. **Generation** - Qwen3-0.6B reads the context and answers the question.

Retrieval quality is measured with **recall@k**: the share of questions whose correct source appears in the top k results.

### System Architecture

```
data/raw/  ──►  index  ──►  data/processed/
                 │            ├── chunks.json   (every chunk: file_path, start, end, content)
                 │            └── bm25/         (BM25 index built from the chunks)
                 │
question ──► search ──► top-k sources ──► answer ──► Qwen3-0.6B ──► answer text
                │                           │
dataset  ──► search_dataset ──► StudentSearchResults JSON
                                            │
                              answer_dataset ──► StudentSearchResultsAndAnswer JSON
                                            │
                                 evaluate ──► recall@k against the ground truth
```

The code is organised by stage:

| Package | Responsibility |
|---|---|
| `src/pipeline/cli.py` | One method per CLI command (Python Fire). Validates arguments and calls the stages |
| `src/parser/` | Pydantic models for CLI arguments (`IndexArgs`, `SearchArgs`, ...) |
| `src/chunking/` | Collecting and reading files, and the three chunking strategies |
| `src/retrieval/` | Tokenizer, building/loading the BM25 index, retrieving sources |
| `src/generation/` | Reading source text, building the prompt, running Qwen3-0.6B |
| `src/pipeline/evaluate.py` | IoU and recall@k |
| `src/helpers/` | Pydantic data models, constants, colours and error classes |

All data exchanged between stages is validated with pydantic (`MinimalSource`, `MinimalSearchResults`, `StudentSearchResults`, `MinimalAnswer`, `StudentSearchResultsAndAnswer`, `RagDataset`). Every error a user can cause (bad arguments, missing or malformed files, empty queries) is raised as a subclass of `CliError` and printed as a one-line message, never as a traceback.

### Chunking strategy

Python files, Markdown pages and Text files don't break apart the same way, so each file type has its own strategy. Python and Markdown files use LangChain's `RecursiveCharacterTextSplitter` whereas Text files use a simple window. All work with a maximum of `--max_chunk_size` characters (default 2000) and an overlap of 10%.

- **Python (`.py`)** - `RecursiveCharacterTextSplitter.from_language(Language.PYTHON)`. It tries to split first at `class` and `def` boundaries, then at blank lines, then at single lines, so a chunk usually holds whole functions or classes instead of cutting through them.
- **Markdown (`.md`)** - `RecursiveCharacterTextSplitter.from_language(Language.MARKDOWN)`. It splits first at headings, then at code blocks and paragraphs, so a chunk usually covers one section of a page.
- **Plain text (`.txt`)** - fixed-size windows with overlap. Files such as `CMakeLists.txt` or requirement lists have no headings or functions to split on.

Every chunk keeps its exact position in the original file (`first_character_index`, `last_character_index`), using `add_start_index=True` from the splitter. I checked over the whole corpus that `text[first:last]` equals the chunk content for every chunk and that no chunk is longer than 2000 characters, because the grader rejects any source longer than that.

The 10% overlap means a sentence cut at a chunk boundary still appears whole in one of the two neighbouring chunks.

### Retrieval method

Retrieval uses **BM25** through the [`bm25s`](https://bm25s.github.io/) library.

BM25 scores each chunk by how many of the question's words it contains, weighted so that:
- rare words (e.g. `lora`, `speculative`) count much more than common ones (*IDF*),
- repeating a word helps, but with diminishing returns (`k1`),
- long chunks don't win just by containing more words (`b`, length normalisation).

The chunks are ranked by score and the top k are returned.

**Tokenizer.** Questions and code rarely use the same words. A question may say "skip the sampler CPU output" while the code says `skip_sampler_cpu_output`. My tokenizer (`code_splitter`) keeps each identifier whole **and** adds its parts:

```
skip_sampler_cpu_output  →  skip_sampler_cpu_output, skip, sampler, cpu, output
LLMEngine                →  llmengine, llm, engine
```

All tokens are lowercased and English stopwords are removed. The same tokenizer is used for the chunks and for the questions.

**File path in the index.** The text indexed for each chunk is its file path followed by its content (`docs/features/lora.md` + the chunk). Many questions name the topic that is also in the file path, so this helps BM25 find the right file. Only the indexed text changes: the stored chunk and its character range stay the same.

The index (`chunks.json` and the `bm25/` folder) is built once by `index` and loaded once per command, so searching 200 questions takes a few seconds.

### Performance analysis

Measured on the available datasets (100 docs questions, 99 code questions) with `--k 10`. The thresholds are recall@5 ≥ 0.80 for docs and ≥ 0.50 for code.

**Effect of chunk size** (`--max_chunk_size`), recall@1 / @3 / @5 / @10:

| max_chunk_size | Docs | Code |
|---|---|---|
| **2000** (default) | 0.64 / 0.80 / **0.86** / 0.87 | 0.49 / 0.75 / **0.80** / 0.88 |
| 1500 | 0.64 / 0.81 / 0.83 / 0.87 | 0.56 / 0.73 / 0.79 / 0.87 |
| 1000 | 0.64 / 0.82 / 0.84 / 0.88 | 0.55 / 0.75 / 0.79 / 0.87 |
| 500 | 0.61 / 0.75 / 0.82 / 0.86 | 0.49 / 0.71 / 0.79 / 0.91 |

- Smaller chunks rank the right chunk first slightly more often for code (recall@1: 0.49 → 0.56), because each chunk is more focused.
- At 500 characters, docs recall drops: one section is split across several small chunks, each with fewer of the question's words.
- Recall@5 is best at 2000, so it is the default.

**Effect of indexing the file path**, recall@5 at chunk size 2000:

| | Docs | Code |
|---|---|---|
| Content only | 0.82 | 0.67 |
| Path + content | **0.86** | **0.80** |

**Speed:**
- Indexing the 1,969 files (14,634 chunks at size 2000): about 5-8 seconds (limit: 5 minutes).
- `search_dataset` on 100 questions: about 2 seconds (limit: 90 seconds).
- Answer generation: about 30-35 seconds per question on CPU, mostly the model generating text.

### Design decisions

- **BM25 instead of TF-IDF** - BM25 handles chunk length and repeated words better, which matters here because chunks vary from a few lines to 2000 characters.
- **`bm25s`** - fast (sparse matrices), and it can save and load the index, so `search` doesn't rebuild it every time.
- **Custom tokenizer** - generic tokenizers keep `snake_case` names as one token, which can never match a question written in plain words.
- **Character offsets, not stored text, for answers** - search results only contain `file_path` and the character range, as the subject requires. `answer_dataset` re-reads the text from the original files using those offsets, so the output files stay small.
- **One JSON file for the chunks** - simple to inspect, and validated by pydantic when loaded.
- **Token budget** - before calling the model, the prompt is tokenized. If it is larger than the context window minus the space reserved for the answer, the lowest-ranked sources are dropped one at a time.
- **Qwen3 non-thinking mode** (`enable_thinking=False`) - the 0.6B model gives shorter, more direct answers without the reasoning step, and runs faster on CPU.
- **System prompt** - the model is told to answer only from the context, to say when the context doesn't contain the answer, and to name the source file, which reduces hallucination.
- **The model is loaded once** in `answer_dataset`, not once per question.
- **Argument validation with pydantic** - each command has an argument model (`k ≥ 1`, non-empty query, chunk size ≤ 2000), so invalid input gives a clear message.

### Challenges faced

- **Keeping character offsets exact.** Recall depends on the character range being correct, so I had to make sure the splitter's start index matched the original file. I verified it by comparing `text[first:last]` with every chunk's content.
- **Questions don't use the same words as the code.** Plain word splitting kept identifiers like `skip_sampler_cpu_output` as one token. Splitting `snake_case` and `CamelCase` while also keeping the whole identifier fixed this.
- **A score that was to close to passing threshold.** Docs recall@5 was 0.82 on the avaliable set, which was too close to the threshold. Looking at the misses showed the right file was often outranked by code files with the same keywords, and adding the file path to the indexed text fixed it.
- **Small model limits.** Qwen3-0.6B sometimes gives short or incomplete answers. Keeping the context focused (top-k sources within the token budget) and a strict system prompt helped keep answers grounded.

## Instructions

```bash
make install        # or: uv sync
```

The first `answer` or `answer_dataset` downloads Qwen3-0.6B (about 1.5 GB) from Hugging Face. On 42 machines, `make install` places the virtual environment and model cache in `/sgoinfre`.

The vLLM repository must be in `data/raw/vllm-0.10.1/`, and the datasets in `data/datasets/AnsweredQuestions/` and `data/datasets/UnansweredQuestions/`.

### Commands

Every command runs as `uv run python -m src <command> [options]`:

| Command | What it does |
|---|---|
| `index --max_chunk_size <int>` | Chunk `data/raw/` and build the index in `data/processed/` |
| `search <query> --k <int>` | Print the top-k sources for one question |
| `search_dataset --dataset_path <path> --k <int> --save_directory <dir>` | Search every question in a dataset and save a `StudentSearchResults` JSON |
| `answer <query> --k <int>` | Retrieve sources and answer one question |
| `answer_dataset --student_search_results_path <path> --save_directory <dir>` | Answer every question in a search results file |
| `evaluate --student_search_results_path <path> --dataset_path <path>` | Print recall@k against the ground truth |
| `server --host <host> --port <port>` | Starts local HTTP API server |

Other Makefile rules: `make lint`, `make lint-strict`, `make clean`, `make debug`.

### Example Usage

```bash
# 1. Build the index
uv run python -m src index --max_chunk_size 2000

# 2. Ask one question
uv run python -m src search "How do I load a LoRA adapter dynamically?" --k 5
uv run python -m src answer "How do I load a LoRA adapter dynamically?" --k 5

# 3. Search a whole dataset
uv run python -m src search_dataset \
    --dataset_path data/datasets/UnansweredQuestions/dataset_docs_public.json \
    --k 10 \
    --save_directory data/output/search_results/UnansweredQuestions

# 4. Measure recall
uv run python -m src evaluate \
    --student_search_results_path data/output/search_results/UnansweredQuestions/dataset_docs_public.json \
    --dataset_path data/datasets/AnsweredQuestions/dataset_docs_public.json

# 5. Generate answers for the dataset
uv run python -m src answer_dataset \
    --student_search_results_path data/output/search_results/UnansweredQuestions/dataset_docs_public.json \
    --save_directory data/output/search_results_and_answer/UnansweredQuestions
```

### Local HTTP API
Besides the CLI, the system can be driven over a small local HTTP API built
with [FastAPI](https://fastapi.tiangolo.com/) and served by
[uvicorn](https://www.uvicorn.dev/). The index and the LLM are loaded once
at startup and reused by every request, so answers skip the model loading
time of the CLI.

**Start the server** (the index must exist, run `index` first):

```bash
uv run python -m src server                  # http://127.0.0.1:8000
uv run python -m src server --port 8001      # custom port (1024-65535)
make server
```

Opening `http://127.0.0.1:8000` redirects to `/docs`, an interactive page
where every route can be tried from the browser ("Try it out" → "Execute").

**Routes**

| Method | Route     | Body                 | Returns                                             |
|--------|-----------|----------------------|-----------------------------------------------------|
| POST   | `/search` | `{"query": str, "k": int}` | `question_id`, `question`, `retrieved_sources`, `warning` |
| POST   | `/answer` | `{"query": str, "k": int}` | the same fields plus `answer`                        |

`k` is optional (default 10). `warning` is `null` normally, or a sentence when
the question has no searchable words or no chunk matches; in that case
`/answer` skips the LLM and returns the warning as the answer.

**Example**

```bash
curl -X POST http://127.0.0.1:8000/answer \
     -H "Content-Type: application/json" \
     -d '{"query": "What HTTP endpoint is used to dynamically load a LoRA adapter in vLLM?", "k": 3}'
```

```json
{
  "question_id": "3c398dc6-b9f7-42b2-9f90-76a557156512",
  "question": "What HTTP endpoint is used to dynamically load a LoRA adapter in vLLM?",
  "retrieved_sources": [
    {"file_path": "data/raw/vllm-0.10.1/docs/features/lora.md",
     "first_character_index": 4695, "last_character_index": 6098}
  ],
  "answer": "The HTTP endpoint used to dynamically load a LoRA adapter in vLLM is `/v1/load_lora_adapter`.",
  "warning": null
}
```

**Errors** never stop the server; each bad request gets its own reply:

| Case                         | Status | Reply                                             |
|------------------------------|--------|---------------------------------------------------|
| empty query, `k` < 1         | 422    | validation details from the pydantic models       |
| `k` larger than the index    | 400    | `k=... is larger than the ... chunks in the index` |
| missing index at startup     | -      | the server does not start: `Index not found ... Run 'python -m src index'` |

## Resources

- https://en.wikipedia.org/wiki/Retrieval-augmented_generation
- https://weaviate.io/blog/introduction-to-rag
- https://medium.com/data-science/llm-rag-based-question-answering-6a405c8ad38a
- https://jillanisofttech.medium.com/optimizing-chunking-strategies-for-retrieval-augmented-generation-rag-applications-with-python-c3ab5060d3e4
- https://community.databricks.com/t5/technical-blog/the-ultimate-guide-to-chunking-strategies-for-rag-applications/ba-p/113089
- https://www.pinecone.io/learn/chunking-strategies/
- https://weaviate.io/blog/chunking-strategies-for-rag
- https://www.twig.so/dev/rag-scenarios-and-solutions/chunking/code-splitting
- https://arxiv.org/pdf/2506.15655
- https://docs.langchain.com/oss/python/langchain/overview
- https://reference.langchain.com/python/langchain-text-splitters/markdown/MarkdownHeaderTextSplitter
- https://github.com/xhluca/bm25s
- https://en.wikipedia.org/wiki/Okapi_BM25
- https://theaidatabaseblog.com/learn/measure-recall-k/
- https://krishnapullak.medium.com/understanding-precision-recall-and-f-score-at-k-in-recommender-systems-7146a0dce68e
- https://huggingface.co/Qwen/Qwen3-0.6B
- https://www.youtube.com/watch?v=A0K3K4fOvY8
- https://www.youtube.com/watch?v=pvCabUerwss
- https://www.youtube.com/watch?v=sVcwVQRHIc8
- https://www.youtube.com/watch?v=T-D1OfcDW1M
- https://www.youtube.com/watch?v=_HQ2H_0Ayy0
- https://fastapi.tiangolo.com/
- https://www.uvicorn.dev/

### Use of Artificial Intelligence

Claude was used to optimize the development workflow of this project. Some usages included:
- Learn the necessary concepts
- Assist with testing the program
- Logical improvement of functions
- Improve understanding of the constrained decoding concepts
- Give ideas of implementations
- Quick and small debug checks througout the making of this program
- Improve the wording of this README