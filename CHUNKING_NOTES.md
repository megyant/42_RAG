# RAG Project — Notes on Chunking and Indexing

> Advisory notes from a discussion between the student and a professor. **These are not a design document and nothing here is mandatory.** The assignment subject is the authority; where these notes and the subject disagree, the subject wins.

**Sources reviewed for these notes:**
- `others_to_delete/en.subject.pdf` — the assignment subject (all 26 pages)
- `others_to_delete/README_RAG_Mou.md` — the moulinette / grader spec
- `src/cli.py`, `src/models.py`, `src/__main__.py`, `src/helpers/`, `Makefile`, `pyproject.toml`
- `data/datasets/datasets_public/public/` (AnsweredQuestions + UnansweredQuestions)
- `data/raw/vllm-0.10.1/`

---

## 0. Status: is chunking the right next step?

**Yes.** Subject VI.1 (Indexing the codebase) is a hard prerequisite for everything downstream, and the CLI signatures are already fixed by VI.6 — so there is nothing in `cli.py` worth completing that will survive the chunking work. Filling in `pass` bodies now would mean rewriting them once the index exists.

### Three decisions that are actually chunking decisions

These belong to the CLI surface, but the chunker cannot be designed without them:

1. **Where does the index live?** → `data/processed/` (required by VI.7.1). **What format?** pickle / JSON / SQLite. *Why it matters:* it constrains whether you can re-read character offsets cheaply later.
2. **What text do you store per chunk?** Just the chunk body, or chunk body + `file_path` + enclosing symbol name? *Why it matters:* subject VI.1 says it explicitly — *"What you keep at indexing time decides which of the two you can still match."*
3. **What is your `k`?** Not the default — your tuned value. The walkthrough uses `k=10`; the pass metric is recall@5.

### Note on dataset paths — RESOLVED, nothing to do

**This was wrong in an earlier revision of these notes.** The extra `datasets_public/public/` nesting no longer exists. Verified on disk:

```
data/datasets/AnsweredQuestions/dataset_code_public.json
data/datasets/AnsweredQuestions/dataset_docs_public.json
data/datasets/UnansweredQuestions/dataset_code_public.json
data/datasets/UnansweredQuestions/dataset_docs_public.json
```

That is exactly what subject VI.7.1 asks for. Do not move anything.

### Ground-truth paths are `data/raw/...` prefixed

Worth stating once because it is a silent, total failure mode if you get it wrong:

```
data/raw/vllm-0.10.1/vllm/model_executor/layers/fused_moe/fused_batched_moe.py
data/raw/vllm-0.10.1/docs/features/lora.md
```

Your indexer walks `data/raw/`, so if you store paths as returned by `rglob` and stringify them, you get this format for free. If you ever store `str(path.relative_to(...))` or a bare basename, you score **0.0 on every question** with no error message. See `RECALL_NOTES.md` §8.

---

## 1. The metric — read this before designing anything

Subject VII.1.1, verbatim:

> A correct source counts as found when one of your results is in the same file and overlaps its character range. The overlap bar is low (an IoU of 0.05), so you do not need to match the reference span exactly: retrieving a chunk that covers the right region of the right file is enough. A result in a different file never counts, which is why `file_path` must be exact.

Two consequences:

**a) You do not need to reproduce the reference segmentation exactly.** A chunk that overlaps the right region is enough.

**b) The hard part is getting the right *file* into your top-k.** A perfect chunk in the wrong file scores zero.

Also, every public ground-truth record has exactly **one** source. So recall@k here behaves like a **per-question hit rate**, not partial credit:

> One source. One question. Hit or miss.

Remember this when reading §2. The question is not *"how precise are my spans?"* It is **"how often does the right file appear in my top 5?"**

Other hard constraints (VI.1 / VII.1.2):
- `max_chunk_size` default **2000 characters**, configurable via CLI
- **Never emit a source wider than 2000 chars.** One over-long source makes your *entire* output invalid. A correctness constraint, not a quality preference.
- Indexing the whole corpus: **≤ 5 minutes**
- Retrieving 200 questions: **≤ 90 seconds**
- Both on CPU-only campus hardware

---

## 2. The core tension in chunk size

Three forces pulling in different directions. Every chunk-size decision trades off between them.

### Small chunks
- **+** more independent shots at overlapping a ground-truth range
- **+** if the right file is in your top-k, more of its chunks surface, so better odds one lands inside the IoU-0.05 window

### Large chunks
- **+** carry more surrounding context, which helps BM25 discriminate
- **+** a short slice of `sampler.py` may not contain the tokens that distinguish it from every other file in the repo
- **+** matters for the **answer** stage: Qwen needs actual context to ground a response in

### The top-k cap (the one people forget)
- if a file has 400 chunks, only 5 of yours surface
- splitting finer does not help if the right file gets pushed out of top 5
- more candidates competing for the same 5 slots
- BM25 length normalization treats every chunk as a short document, flattening the length signal you'd normally rely on

### The question to sit with

> Given that ground truth is one source per question (so recall@k ≈ hit rate), what chunk size maximises the probability that the **right file** appears in your top 5?

Note this is a question about **file-level ranking**, not chunk-level precision.

There is no obvious answer. But you can measure one cheaply.

### Measure before you tune

Build a deliberately dumb chunker. Run retrieval. Look at where the failures are:

| Failure mode | Diagnosis |
|---|---|
| Wrong chunks in the **right** file | chunking granularity problem |
| **Right** chunks in the **wrong** file | ranking / scoring problem |

These need **opposite** fixes. Find out which one you have before optimising anything.

---

## 3. Ground-truth profiling — DONE, results below

Earlier revisions of these notes kept recommending this as future work. It is done. Here is what it found, and one of the findings changes the design.

### Q1: Are ground-truth ranges aligned to natural boundaries?

**Mostly no.** Measured across every question in both datasets:

| | starts at a line boundary | starts mid-line |
|---|---|---|
| code | 20 / 99 (20%) | **79 / 99 (80%)** |
| docs | 71 / 100 (71%) | 29 / 100 (29%) |

Actual code spans, first 8 records verbatim:

```
'@property\n    def activation_formats(\n        self\n    ) -> tuple[mk...   (559)
'FP8_MIN: tl.constexpr = float8_info.min,\n    FP8_MAX: ...'                (93)
'else:\n            raise ValueError(f"Unsupported sampling type...')       (1012)
'"""\n        '                                                             (12)
'cudagraph_capture_sizes = self.vllm_config.compilation_config\\...         (897)
'if prefill_meta is None and decode_meta.use_cuda_graph:\n     ...'          (998)
'def __init__(self, *, vllm_config: VllmConfig, prefix: str = ""):\n ...'    (963)
```

**The consequence is direct: a splitter that only emits `def` / `class` / heading-start chunks cannot match most code questions.** It would emit clean boundaries that sit tens of characters away from where the ground truth begins. That is the "right file, wrong region" failure bucket, produced by the chunker itself.

This also retires the assumption in `RECALL_NOTES.md` §2.5 that *"structural boundaries are what produce nesting."* Nesting helps — but **only if your boundaries land near the reference ones**, and here they demonstrably do not.

### Q2: Span-length distribution

```
code  n=99   min=12  median=878    max=1578
docs  n=100  min=40  median=1154.5 max=1997

code: <100: 2 | 100-400: 6 | 400-800: 28 | 800-1200: 61 | 1200-1600: 2
docs: <100: 4 | 100-400: 11 | 400-800: 16 | 800-1200: 22 | 1200-1600: 17 | 1600-2000: 30
```

Spans are **large and clustered high**. Nearly two thirds of code questions have spans over 800 chars; 30% of docs questions are over 1600. Combined with the mid-line finding, this says the reference spans are **broad windows over a region of interest**, not tight semantic units.

### Q3: How many distinct files?

```
code  99 questions  ->  91 distinct .py files
docs 100 questions  ->  56 distinct files (55 .md + 1 .txt)
```

Concentration to note: `supported_models.md` alone is the target for **7** docs questions; `openai_compatible_server.md` for 6. Files are almost all distinct targets (only 3 code files appear twice), so this is a **broad-shallow** retrieval problem, not a hub problem.

Note the single `.txt` file in docs ground truth — `ingest.py` already includes `.txt` in its suffix list. Keep it.

### Q4: What chunk size does the IoU rule actually permit?

This is the decisive measurement, and it revises the advice in earlier revisions of these notes. I computed, for each candidate chunk size, **the fraction of questions where *some* chunk of that size placed anywhere in the file would satisfy IoU > 0.05** — i.e. the ceiling on recall achievable regardless of how good your ranking is:

| chunk size | code ceiling | docs ceiling |
|---|---|---|
| 150 | 100% | 100% |
| 200 | 100% | 100% |
| 300 | 99% | 100% |
| 400 | 99% | 100% |
| 600 | 99% | 100% |
| 800 | 99% | 99% |
| 1000 | 99% | 99% |
| 1500 | 99% | 97% |
| 2000 | 98% | 96% |

**Read this table carefully — it is the whole chunk-size decision.** Anything from 150 to 600 characters is essentially free. The IoU rule does **not** pick your chunk size for you; it only rules out the extremes. Past ~800 chars you start losing the tight spans (the 12- and 40-char ones) to the `20·L` upper bound, and by 2000 you have thrown away 4% of docs questions.

So: **choose chunk size on retrieval-quality grounds.** The IoU arithmetic only forbids a very large chunk, and even at 2000 the cost is ~4 points of ceiling — not fatal, but real.

---

## 4. Code chunking

Subject VI.1 requires a distinct Python chunking strategy (and a distinct Markdown one). Both are graded requirements, not preferences.

### The `ast` trap

The natural instinct is to use `ast`. You already bookmarked the docs. Here is the problem.

`ast` nodes expose `lineno` and `col_offset`:

- `lineno` is **1-indexed**
- `col_offset` is **0-indexed bytes in UTF-8**, not characters, and only for the start of the node's **first line**
- **Neither is an absolute character offset**

To get a character offset you must sum the lengths of all preceding lines. That works until you hit a multi-line string: `ast` reports a `lineno` for a triple-quoted string that started 40 lines earlier, and the naive sum gives you the wrong answer.

The subject's own source list includes both:
- `docs.python.org/3/library/ast.html`
- `twig.so/dev/rag-scenarios-and-solutions/chunking/code-splitting`

That pairing is a deliberate hint. Read both.

### Questions to answer

**Q1.** Do you split only at function/class boundaries, or do you descend into them? A single 2000-line method exceeds your hard limit, so you need a fallback either way. **What is your fallback?**

**Q2.** Decorators: inside the function's range, or outside it? `ast` reports `lineno` at the `def`, not at the `@`. Ground-truth ranges that start at a decorator would never be matched by a naive implementation.

**Q3.** What does your splitter do with a 12-character target like `trust_remote_code = False`? If your minimum chunk size is 300, that question is lost **before retrieval ever runs**.

### Action item

Bucket the ground-truth ranges by **size** and look at the distribution. If a meaningful fraction are under 200 characters, you need a splitter that can emit small chunks without falling apart structurally.

---

## 5. Markdown chunking

Your docs corpus is mkdocs-structured:
- `.md` files with YAML front matter
- `.inc.md` **partials** included into other pages at build time (`s390x.inc.md`, `cuda.inc.md`, `rocm.inc.md` all appear in ground truth)

### Header-hierarchy splitting

The obvious approach; you bookmarked `MarkdownHeaderTextSplitter`.

**But check what it returns first:** does it give you **character positions**, or only strings?

If only strings, you must locate each chunk in the original text to recover offsets — and every `str.find` is a chance for off-by-one drift.

### Front matter and code fences

- A YAML block at the top of a vLLM doc is not a section header. What does your splitter do with it?
- A fenced code block containing `# comment` lines will fool naive heading detection. Do you strip fences before splitting?
- If you **do** strip them, how do you map positions back to the original?

### The `.inc.md` problem

Partials get included into other pages at build time. If a question's answer lives in an include, the ground truth may point at **either** the partial **or** the including file.

**Question:** do you index both? If so, does that duplicate content in your index and distort BM25 term frequencies?

---

## 6. Tokenization is a chunking decision

You noted BM25 as your reference. BM25 needs a tokenizer, and on a Python corpus the obvious choice is quietly harmful.

### The problem

A regex like `\w+` or `\b\w\w+\b` turns:

```
skip_sampler_cpu_output
          -> skip, sampler, cpu, output
```

Those four tokens appear in **hundreds** of files. You destroyed the one term that identifies this file and replaced it with noise.

Meanwhile the question is phrased in prose:

> *"What determines whether the sampler returns Pythonized results?"*

...which shares almost no tokens with the identifier form.

Subject VI.1 says it directly: *"a question may paraphrase an idea or quote an identifier verbatim"* — you need to handle **both** forms.

### Questions

**Q1.** Does your tokenizer keep underscores and dots intact, or split on them?

**Q2.** If you keep `skip_sampler_cpu_output` as **one** term, does BM25's IDF weight it appropriately? A term in one document gets an absurd IDF that can swamp the common terms carrying real signal. How do you stop that?

**Q3.** What about camelCase? And note: many questions in this dataset are synthetic and lifted from the code's own naming — helpful information. How do you exploit it?

### Likely direction

Index the whole identifier **and** its subparts. But that has a cost. Decide it on purpose rather than discovering the problem at recall@5 = 47%.

---

## 7. Properties any chunker must hold

**Determinism.** Same input → same output, byte for byte. The defense **re-runs** your pipeline. If your chunker walks a `set` or depends on dict ordering, offsets shift between runs and your numbers will not reproduce.

**Round-trip fidelity.** `content[first:last] == the chunk text you indexed`. Verify on **real files**, not toy unit-test strings. This is where encoding and newline handling betray you.

**Hard width limit.** Every emitted span is ≤ 2000 characters. Not "usually." Assert it. One violation invalidates the whole submission.

**Graceful degradation.** Handle binary files, empty files, a `.png` someone committed, CRLF line endings, unreadable permissions, malformed JSON. Subject VI.6: the CLI *"must never crash with an unhandled traceback."*

---

## 8. Confirmed bugs in current code

### `models.py:37` — field name typo — RETRACTED, this was never a bug

**An earlier revision of these notes claimed `StudentSearchResults` had `search_reults` instead of `search_results`. That was wrong.** Verified on disk, both models are spelled correctly:

```python
class StudentSearchResults(BaseModel):
    search_results: List[MinimalSearchResults]
    k: int

class StudentSearchResultsAndAnswer(BaseModel):
    search_results: List[MinimalAnswer]
    k: int
```

`models.py` matches subject VI.4 verbatim. **Do not "fix" anything here.** The general lesson still stands — after building a result writer, construct the model, `model_dump()`, and assert the keys match the subject's JSON exactly. That check is cheap and catches this whole class of error.

### Retracted — two things flagged earlier that were wrong

- **`MinimalAnswer(MinimalSearchResults)` is CORRECT.** Subject VI.4 mandates that inheritance verbatim. Do not "fix" it.
- **The `evaluate` question is ANSWERED.** Subject VI.6 says `evaluate` is for your own iteration, the official metric comes from the moulinette, and *"Your solution must never import or call the moulinette."* So `evaluate` **is** a genuine reimplementation of recall@k on your side.

### `pyproject.toml:18-19` — dead `[tool.uv.sources]` entry (harmless today, remove it)

```toml
[tool.uv.sources]
llm-sdk = {path = "llm_sdk"}
```

`llm_sdk` does not exist in this repo (it lives in the `call_me_maybe` project) and `llm-sdk` is **not** in `[project.dependencies]`. So uv has nothing to resolve for it.

**An earlier revision of these notes claimed this would break `uv sync` and therefore fail the defense. That was overstated.** Verified by copying `pyproject.toml`, `uv.lock`, `README.md` and `src/` into an empty directory and running `uv sync --frozen`: it completes with exit 0. uv ignores source entries whose package is not a dependency.

Still worth deleting, for one practical reason: the moment you *do* add `llm-sdk` as a real dependency, that path resolves against a directory that is not in the repo and breaks the build. Remove the block now; re-add a vendored `llm_sdk/` under this repo if you later want to reuse it from `call_me_maybe`.

Subject V.4 still holds — *"the reviewer and the moulinette only run `uv sync`"* — so keep re-verifying from a clean checkout before the defense. It works today.

### `Makefile:52` — `lint-strict` does not do what the subject requires

```make
lint-strict: flake8
	uv run mypy . --strict
```

`flake8` here is a **prerequisite name**, not a rule you defined, so make treats it as a missing file target and errors out. And flake8 never runs.

Subject V.2 requires lint-strict to execute **both**:
```
flake8 .
mypy . --strict
```

### `Makefile:39` — `debug` target is broken

```make
uv run python -m pdb .
```

That points pdb at a **directory**. What script is it supposed to debug? Subject V.2 requires `run` and `debug` to execute the main script.

### `__main__.py:10-11` — error handler discards your own message

```python
except CliError:
    print("TEMP")
```

You already have `CliError`; its message is being thrown away. Print the message to stderr and exit non-zero.

Also note: `fire` raises `FireExit` for bad args / usage errors. Those are **not** `CliError`, so they propagate. Be **deliberate** about that rather than accidental.

Subject VI.6: *"The CLI is tested with such edge cases and must never crash with an unhandled traceback."*

---

## 9. Graded requirements currently missing

### tqdm progress bars

Required by subject V.4 and VI.6 for long-running operations. **Not** in `pyproject.toml`, **not** used anywhere. Belongs in `index` and `search_dataset`.

### README is far from compliant

Yours is currently a bare link list. Subject Chapter VIII requires:

- [ ] first line italicised, reading exactly: `This project has been created as part of the 42 curriculum by <login>`
- [ ] Description (goal + brief overview)
- [ ] Instructions (install / compile / execute)
- [ ] Resources (classic references + how AI was used, specifying **for which tasks** and **which parts**)
- [ ] System architecture
- [ ] Chunking strategy
- [ ] Retrieval method
- [ ] Performance analysis (recall@k)
- [ ] Design decisions
- [ ] Challenges faced
- [ ] Example usage
- [ ] must be written in **English**

**Note on the AI disclosure + recode (X.1):** the README must state what AI was used for, and X.1 says you may be asked to modify code in a few minutes to verify you actually understand it. Those two requirements are in tension by design. Whatever you do, be able to **defend every line** — including the ones you did not write. (See subject Chapter III.)

### Required project layout (VI.7.1)

| Path | Status |
|---|---|
| `src/` | OK |
| `pyproject.toml` + `uv.lock` at root | OK — `uv sync --frozen` verified from a clean dir |
| `README.md` at root | present, **not compliant** |
| `data/raw/` | OK |
| `data/processed/` | **MISSING** — index output goes here |
| `data/datasets/UnansweredQuestions/` | **OK** — verified present |
| `data/datasets/AnsweredQuestions/` | **OK** — verified present |
| `data/output/search_results/<Scope>/` | **MISSING** — `search_dataset` output |
| `data/output/search_results_and_answer/<Scope>/` | **MISSING** — `answer_dataset` output |

All input/output paths must be CLI args and **never hard-coded**: *"If the structure or the command interface is not respected, the reference scripts cannot run and the corresponding checks are considered failed by design."*

### `src/chunking/__init__.py` — imports a module that does not exist

```python
from .parser import Parser   # src/chunking/parser.py does not exist
```

Verified: `import src.chunking` raises `ModuleNotFoundError: No module named 'src.chunking.parser'`. Nothing imports `src.chunking` yet, so this is dormant rather than fatal — but it will surface the moment `cli.py` or `manager.py` touches chunking, and it will look like a confusing error at that point. Delete the line or write the module.

Note the related stubs: `ChunkData(BaseModel)` is `...`, and `Chunk.chunk` is an abstractmethod with no annotations. `flake8` and `mypy` both currently fail on these files.

### Answer generation (VI.3)

Model required: **Qwen/Qwen3-0.6B** (you may use others as long as it still works with this one). Pass retrieved context within token budget, produce JSON per the pydantic models. Grading prioritises retrieval quality, grounding and prompt strategy over perfect phrasing.

### Makefile `lint` target

Yours matches the subject's required flags. Good.

---

## 10. What to read, in priority order

1. ~~**Profile the ground-truth ranges (§3).**~~ **DONE.** Findings: spans are large (median 878/1154) and **80% of code spans start mid-line**. Design your chunkers against that.
2. **`ast` docs** — `lineno`, `col_offset`, `end_lineno`, `end_col_offset`. Settle the line-vs-character question and the multi-line-string problem. Plus the Twig code-splitting article (both already in your README).
3. **BM25** — the Robertson/Sparck Jones IDF formulation, *not* a library docstring. Your chunks have wildly varying lengths; the length-normalization term does the heavy lifting when one chunk is 40 chars and its neighbour is 1900.
4. **Sweep the chunk size empirically.** Index at several sizes, measure recall@5 on **both** datasets. This is a **deliverable**, not just debugging: subject VI.1 explicitly says *"Smaller chunks are fine; report the effect on your recall@k."* That sweep also fills your README's Performance analysis section.
5. **mP25 / learned sparse retrieval** — only after BM25 works. Use as a comparison point for whether lexical retrieval is your ceiling.

---

## 11. Questions still open

**Q1.** ~~How many files and how many total characters?~~ **DONE.** 1937 `.py`/`.md` files, 20,003,424 chars. At 400 chars/chunk that is ~50k chunks. 5-minute indexing budget and 450ms/query retrieval budget both follow from this.

**Q2.** ~~Do the ground-truth ranges reveal a specific segmentation strategy?~~ **DONE, partially.** They are *not* aligned to structural boundaries (80% of code spans start mid-line) and they are *not* tight — median 878/1154 chars. They behave like broad windows placed around a region of interest. Whether they were produced by a reference chunker, by a human, or by an LLM is still unknown, and it does not change what you should build.

**Q3.** For a Python chunker, how do you get **character** offsets from `ast`, and what happens to them when a decorator or a multi-line string spans lines? (§4.) **Still open — this is yours to answer.**

**Q4.** If the reference spans are *not* structural, what boundary rule do you use instead? Overlapping windows? Line-aligned windows? A structural splitter plus a fallback merge for oversized nodes? The 80%-mid-line finding is the argument against a pure structural splitter, but it is not itself a prescription. **This is the main open design question, and it is the one subject X.1 will likely probe.**

---

## 12. What was deliberately not done

No chunker, indexer, tokenizer, or retrieval code was written. No project files were modified apart from these notes.

These notes describe problems and the questions that expose them. **The design is yours.** If you write it, you will have to defend it — and that is the point: subject X.1 says a few minutes of live modification may be requested to verify you understand the project.

---

## 13. Revision log

Kept so you can see which earlier advice was wrong, and not act on it.

| Claim | Status |
|---|---|
| Datasets nested under `datasets_public/public/` | **FALSE** — already at the VI.7.1 paths |
| `models.py:37` has a `search_reults` typo | **FALSE** — model is correct |
| `pyproject.toml` `[tool.uv.sources]` breaks `uv sync` and fails the defense | **OVERSTATED** — `uv sync --frozen` verified clean, exit 0. Still delete the dead entry |
| Ground-truth profiling is future work | **STALE** — done, §3 |
| "Structural boundaries are what produce nesting" (from `RECALL_NOTES` §2.5) | **MISLEADING** — 80% of code spans start mid-line, so clean structural boundaries will often miss |
| Recommend 400-char chunks as the unadorned baseline (`RECALL_NOTES` §5.3) | **STILL REASONABLE** — §3's ceiling table puts 400 at 99%/100%, so it costs nothing on IoU grounds. Whether it retrieves *well* is untested |
