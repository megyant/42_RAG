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

### Note on dataset paths (reconcile later, low priority)

The datasets were unzipped from `datasets_public.zip`, which explains where they are — but the extra nesting does not go away by being unzipped.

| | |
|---|---|
| Subject VI.7.1 wants | `data/datasets/AnsweredQuestions/` |
| Actually present | `data/datasets/datasets_public/public/AnsweredQuestions/` |

Three extra path segments. Since paths are CLI arguments the pipeline still runs, but VI.7.1 says a structure mismatch means *"the corresponding checks are considered failed by design."* Moving the directories or symlinking is a two-minute job. Do it before the defense, not now.

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

## 3. Highest-value investigation: profile the ground truth

Do this **before** writing the splitter. It is the single most useful hour you will spend, and it makes every other decision cheaper.

### Question to answer

**Are the ground-truth character ranges aligned to a natural boundary, or arbitrary?**

### How to find out

Write a small script that:
1. loads the first ~30 records from `data/datasets/datasets_public/public/AnsweredQuestions/dataset_code_public.json`
2. for each, reads the file at `file_path`
3. slices `content[first_character_index:last_character_index]`
4. prints the text plus surrounding context

Then look at the shapes:
- Does `first_character_index` land on the start of a line?
- Does the slice start with `def `, `class `, an assignment, a docstring? Or does it start mid-expression?

Watch for suspiciously small ranges. Example from the real dataset:

```
vllm/entrypoints/llm.py  ->  64076 to 64088  =  12 CHARACTERS
```

That is one identifier, not a function body. Something chose that span.

Repeat for the docs dataset (`dataset_docs_public.json`). Then compare: do code and docs have visibly **different** segmentation styles? If yes, that directly informs your two required chunkers.

### Why this isn't cheating

The spec tells you the metric and the overlap bar. Working out what the reference implementation did is legitimate reverse-engineering of the evaluation. It is the kind of thing that separates 55% from 85%. Use the information; document the method honestly in the README.

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

### `models.py:37` — field name typo (silent, and it will cost everything)

```python
class StudentSearchResults(BaseModel):
    search_reults: List[MinimalSearchResults]   # TYPO: "reults"
    k: int
```

Subject VI.4 specifies `search_results`. You have `search_reults`. Pydantic will **not** warn you — it serialises exactly what you wrote, and the moulinette will not find the field.

Note line 42 (`StudentSearchResultsAndAnswer`) spells it **correctly**, so this is a copy-paste slip.

**Guard against recurrences:** construct the model, `model_dump()`, assert the keys match the subject's JSON exactly.

### Retracted — two things flagged earlier that were wrong

- **`MinimalAnswer(MinimalSearchResults)` is CORRECT.** Subject VI.4 mandates that inheritance verbatim. Do not "fix" it.
- **The `evaluate` question is ANSWERED.** Subject VI.6 says `evaluate` is for your own iteration, the official metric comes from the moulinette, and *"Your solution must never import or call the moulinette."* So `evaluate` **is** a genuine reimplementation of recall@k on your side.

### `pyproject.toml:18-19` — broken source path (could fail the whole defense)

```toml
[tool.uv.sources]
llm-sdk = {path = "llm_sdk"}
```

But `llm_sdk` lives at `/mnt/HDD/42lisboa/call_me_maybe/llm_sdk` — **outside** the `RAG/` project. This path does not resolve. And `llm-sdk` is not listed in `[project.dependencies]` either.

Subject V.4: *"the reviewer and the moulinette only run `uv sync`."* So a broken resolution here is a **hard failure** at the defense. **Verify `uv sync` succeeds from a clean state.**

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
| `pyproject.toml` + `uv.lock` at root | OK (but see the `uv sync` bug) |
| `README.md` at root | present, **not compliant** |
| `data/raw/` | OK |
| `data/processed/` | **MISSING** — index output goes here |
| `data/datasets/UnansweredQuestions/` | **MISSING** — wrong nesting (§0) |
| `data/datasets/AnsweredQuestions/` | **MISSING** — wrong nesting (§0) |
| `data/output/search_results/<Scope>/` | **MISSING** — `search_dataset` output |
| `data/output/search_results_and_answer/<Scope>/` | **MISSING** — `answer_dataset` output |

All input/output paths must be CLI args and **never hard-coded**: *"If the structure or the command interface is not respected, the reference scripts cannot run and the corresponding checks are considered failed by design."*

### Answer generation (VI.3)

Model required: **Qwen/Qwen3-0.6B** (you may use others as long as it still works with this one). Pass retrieved context within token budget, produce JSON per the pydantic models. Grading prioritises retrieval quality, grounding and prompt strategy over perfect phrasing.

### Makefile `lint` target

Yours matches the subject's required flags. Good.

---

## 10. What to read, in priority order

1. **Profile the ground-truth ranges (§3).** Do this first — it determines your target and makes everything else cheaper. Cheap to do, highly informative.
2. **`ast` docs** — `lineno`, `col_offset`, `end_lineno`, `end_col_offset`. Settle the line-vs-character question and the multi-line-string problem. Plus the Twig code-splitting article (both already in your README).
3. **BM25** — the Robertson/Sparck Jones IDF formulation, *not* a library docstring. Your chunks have wildly varying lengths; the length-normalization term does the heavy lifting when one chunk is 40 chars and its neighbour is 1900.
4. **Sweep the chunk size empirically.** Index at several sizes, measure recall@5 on **both** datasets. This is a **deliverable**, not just debugging: subject VI.1 explicitly says *"Smaller chunks are fine; report the effect on your recall@k."* That sweep also fills your README's Performance analysis section.
5. **mP25 / learned sparse retrieval** — only after BM25 works. Use as a comparison point for whether lexical retrieval is your ceiling.

---

## 11. Questions still open

**Q1.** How many files and how many total characters are in `data/raw/vllm-0.10.1`? That is your 5-minute indexing budget **and** your 90-second retrieval budget. Both currently unknown. Countable in a minute. Start here if you want one cheap, immediately useful thing to do.

**Q2.** Do the ground-truth ranges look like they were produced by a specific segmentation strategy? (§3 — the big one.)

**Q3.** For a Python chunker, how do you get **character** offsets from `ast`, and what happens to them when a decorator or a multi-line string spans lines? (§4.)

---

## 12. What was deliberately not done

No chunker, indexer, tokenizer, or retrieval code was written. No project files were modified.

These notes describe problems and the questions that expose them. **The design is yours.** If you write it, you will have to defend it — and that is the point: subject X.1 says a few minutes of live modification may be requested to verify you understand the project.
