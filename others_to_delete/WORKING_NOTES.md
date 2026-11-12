# Working notes — CLI, Manager, and the path to chunking

## Fire: what it does for you

`fire.Fire(Cli)` instantiates `Cli` with **no arguments**, finds the method
named after the first command word, and calls it with the remaining flags.

So there is **no parsing to write**. Fire is the parser. `main` does nothing
but call it and catch exceptions.

- Command name bare, flags with dashes: `python -m src index --max_chunk_size 500`
- `--max-chunk-size` also works (hyphens map to underscores)
- Docstrings become `--help` output; Fire parses Google-style `Args:`
- Missing required arg -> exits **2** with usage, no traceback
- **`--k notanint` does NOT error.** Annotations are a hint, not validation.
  You get the string. Validate yourself.
- Fire **prints whatever the method returns.** Return `None` where you'd rather
  write a file.

## The layering

```
__main__.py    fire.Fire(Cli) + catch CliError. Nothing else.
cli.py         one method per command. Thin. Already correct.
manager.py     stages of the pipeline. No parsing, no CLI knowledge.
```

`Cli` never validates, never reads files, never defaults. `Manager` owns
configuration and the actual stages.

### Why Manager isn't a copy of Cli

Commands mirror *stages*, not each other:

```
index              the indexing stage: ingest -> chunk -> persist
search             the retrieval stage: load index -> score -> rank
answer             search() + generate()
search_dataset     loops search()
answer_dataset     loops generate() -- sources already in the input file
evaluate           recall@k; touches neither index nor model
```

Test: **does the method do something the stage doesn't?** If a wrapper has one
caller and mirrors a CLI name, it's in the wrong place.

## Manager shape

```
Manager.__init__(raw_path="data/raw", processed_path="data/processed")

 ingest()                          exists, keep it
 index(max_chunk_size)             ingest -> chunk -> persist
 search(query, k)                  load index once -> score -> rank
 generate(question, sources)       context -> Qwen -> answer text
 evaluate(results_path, dataset)   recall@k

 search_dataset(path, k, dir)      loops search()
 answer(query, k)                  search() + generate()
 answer_dataset(path, dir)         loops generate()
```

`index` IS the indexing stage -- no separate `index_corpus`. It was the same
function; that wrapper was invented structure.

## Constructing a Manager per command

`Manager().search(query, k)` is fine. Measured: a config-only constructor costs
**0.41 us** vs ~121 ms if it did real work. The rule:

> **Configuration in `__init__`. Expensive work in the method that needs it.**

Never load the index in `__init__` -- that would force `index` to pay for it too.
Load once per process and cache:

```
function search(query, k):
    if self.index is None:
        self.index = load(processed_path)   # once, not per question
```

That's the difference between a 5-second and 400-second `search_dataset`.

A named variable is only needed if you use the object **twice**. Inside Manager,
`self` is that variable.

## Paths -- three kinds

| Kind | Values | Where |
|---|---|---|
| **CLI arguments** | `--dataset_path`, `--save_directory`, `--student_search_results_path` | per-command parameters, **no defaults** |
| **Fixed by VI.7.1** | `data/raw`, `data/processed`, `data/datasets/*`, `data/output/*` | `Manager.__init__` defaults |
| **Per-command values** | `--max_chunk_size`, `--k` | CLI defaults (2000, 10) |

`raw_path` = the corpus to index. `processed_path` = where the index lives.
Neither is a dataset file or an output dir. Dataset paths do NOT belong on
Manager -- they pass straight through as arguments.

**Why no default for `dataset_path`:** both scopes use the same filenames.
`UnansweredQuestions/dataset_docs_public.json` and
`AnsweredQuestions/dataset_docs_public.json` are different files, same name.
VI.7.2 warns about exactly this. A default would silently read the wrong one.

**Input must exist, output gets created.** Check inputs *before* creating
outputs, or a typo'd path still leaves an empty directory that hides the mistake
next run. Use `exist_ok=True` or the second run raises.

## What `answer_dataset` does (the confusing one)

It does **not** search.

```
search_dataset   questions -> retrieved_sources   (no answers)
answer_dataset   takes that file -> adds an answer to each record
```

`retrieved_sources` are copied from the input, not re-fetched. No `--k`, no
`--dataset_path`, because there's nothing to retrieve and no questions to look
up.

```
StudentSearchResults  ->  StudentSearchResultsAndAnswer
  question_id             question_id
  question                question
  retrieved_sources    +  retrieved_sources   (copied)
  answer               +  answer              (new)
```

## Validation -- where it goes

In `Manager`, never `Cli`. `ParseError(CliError)` for bad values, caught once in
`main` -> stderr -> `exit 1`.

| Value | Rule |
|---|---|
| `k` | integer, >= 1 |
| `max_chunk_size` | integer, 1-2000 |
| `query` | non-empty |
| dataset / results paths | must exist |

Verified: non-numeric strings, `k=0`, and the 2000 cap all behave correctly.

Hand-rolled over pydantic for this layer: **pydantic accepts `True` as `1`**
(bool is an int subclass), and its messages don't name the field. V.4 explicitly
exempts orchestration classes from pydantic.

## Errors

`main` catches `CliError` -> prints to stderr -> `exit 1`. `FireExit` (bad flags)
exits 2 on its own. Non-zero exit on failure is correct -- don't `|| true` it
away in normal use.

## The chunker

Separate class, not a Manager function. VI.1 requires two distinct strategies;
`max_chunk_size` is needed for every file, so it belongs on the object.

```
src/chunking/chunk.py           Chunk(ABC), abstract chunk()
src/chunking/chunk_code.py      ChunkCode      -> .py
src/chunking/chunk_markdown.py  ChunkMarkdown  -> .md
```

`Manager` builds one chunker, loops files through it. Dispatch:

```
.py   -> ChunkCode
.md   -> ChunkMarkdown
.txt  -> ChunkText (fixed-size windows)
```

`.txt` matters: 3 docs questions target `CMakeLists.txt`. No headings in CMake,
so heading-splitting fails on it.

**Configuration in `__init__`, work in the method:**

```
chunker = ChunkCode(max_chunk_size)     # once
for path in files:
    chunks = chunker.chunk(path, text)  # per file
```

## ChunkData

```
class ChunkData(MinimalSource):
    text: str          # the ONLY addition
```

- Passes straight into `MinimalSearchResults` -- accepted as `MinimalSource`
- `text` does **not** leak into output JSON; pydantic serialises per the
  *declared* model
- Adding `text` to `MinimalSource` directly is also legal (VI.4 allows extra
  fields) but emits `text` on every source, and an optional default still emits
  `"text": ""`. Would need `exclude_defaults`.

Put it in `src/models.py`, not `chunk.py` -- avoids an import edge.

## Two invariants to assert in code

```
original_text[c.first:c.last] == c.text     # round-trip
c.last - c.first <= 2000                    # hard cap
```

Offsets must come from slicing the **original** text. `.strip()` or re-tokenizing
shifts every offset and silently scores 0. Pydantic validates on load, so bad
persisted data fails loudly instead of retrieving wrongly.

## Measured facts about your data

```
1937 .py/.md files        20,003,424 chars        ~50k chunks at 400
```

| | code | docs |
|---|---|---|
| questions | 99 | 100 |
| sources per question | 1 | 1 |
| distinct target files | 91 | 56 |
| span min/median/max | 12 / 878 / 1578 | 40 / 1154.5 / 1997 |
| **spans starting mid-line** | **79 (80%)** | 29 (29%) |

**The 80% mid-line finding is the big one.** A pure structural splitter emits
clean boundaries tens of chars from where the reference starts -- IoU punishes
that (straddle failure). Structural splitting is still *required* by VI.1; this
is about what you do around it.

**recall@k is a hit rate.** One source per question -> each question is 1.0 or
0.0, no partial credit. `length = last - first`, spans half-open, strict `>` on
IoU 0.05.

**IoU ceiling by chunk size** (any chunk of that size, regardless of ranking):

| size | code | docs |
|---|---|---|
| 150-600 | 99-100% | 100% |
| 2000 | 98% | 96% |

The overlap rule doesn't pick your chunk size. Only the 2000 cap is hard.

**Identifier density in questions:** 70/99 code quote a snake_case identifier;
9/100 docs do. **The paraphrase gap is a docs problem** -- and docs has the
higher threshold (80% vs 50%).

## Build order

See "TO BE DONE" at the bottom of this file for the staged breakdown.

Short version: plumbing before algorithms, one file before the corpus, and
one real query before any scoring.

**DECIDED -- oversized-node split:** equal parts, line-aligned, `overlap_lines = 1`.
See "Oversized nodes" below.

### DECIDED -- `evaluate` jumps Stage 2 and Stage 4, but not Stage 1

Stage 5 runs **before Stage 2** (chunking algorithms) and **before Stage 4**
(retrieval).

Why: **it is the only stage that can be finished and proved correct while no
retrieval system exists**, and every number collected afterwards depends on it
being right.

It does **not** depend on Stage 1. Nothing here reads `data/raw/`, builds a
chunker, or calls `ingest` -- `evaluate` reads a results JSON and a ground-truth
dataset and touches neither the index nor the model. The two stages are
independent; either order is valid.

**Finish Stage 1 first, then Stage 5, then start chunking algorithms.** Stage 1
is nearly closed and mechanical, and Stage 5 is no reason to leave it
half-finished. The value of Stage 5 being early is *fail-fast* on the oracle --
catch a format fault before the chunker, tokenizer and BM25 exist to hide it --
and running it immediately after Stage 1 serves that just as well.

```
Stage 1  Ingest->Chunk  plumbing        <-- finish this first
Stage 5  Evaluate       self-contained  <-- then this, before any algorithm
Stage 2  Chunking       algorithms
Stage 3  Persistence
Stage 4  Retrieval      first real recall number
```

Four sub-steps, in order:

1. `src/evaluating/` -- faithful port of the recall rule
2. dataset IO -- load `RagDataset`, keyed on `question_id`
3. oracle writer -> assert **1.0**; complement -> assert **0.0**
4. wire `Manager.evaluate` (`Cli.evaluate` already exists and is correct)

`evaluate` reads a results JSON and a ground-truth dataset. It touches neither the
index nor the model, so the oracle file -- ground truth submitted as results --
scores 1.0 with no chunker, no BM25 and no `k` tuning involved.

**The oracle is a hard stop, not a smoke test.** If it does not score exactly
1.0, stop there. The overlap rule is no longer an inference: it was recovered
from the moulinette bytecode and recompiled to a byte-exact match
(`RECALL_NOTES.md` 2). There is no "maybe I misread the rule" branch left. Every
number gathered after a failed oracle is tuning blind, and no amount of chunker
or BM25 work would reveal it.

The complement (same file, `"retrieved_sources": []`, must score 0.0) brackets
the metric from the other end for the cost of one loop.

## Oversized nodes -- DECIDED

### Why it had to be decided

`max_chunk_size` caps what you **emit**. It does not cap the size of `ast`
nodes you **find**. A node of 13,388 characters cannot be emitted as one chunk.

Measured on the real corpus:

```
sampled 60 .py files -> 444 nodes examined -> 72 over 2000 chars (16%)
files affected: 28 / 60
largest: create_argument_parser, 13388 chars, benchmarks/benchmark_serving.py
```

And among files the ground truth actually targets:

```
87 / 91 ground-truth code files contain >=1 oversized node
  flashinfer.py: 11      datasets.py: 16      common.py: 13
```

**This is not an edge case. It is the primary path.**

### The algorithm

```
split oversized node:
  1. nparts = ceil(node_size / cap); target = ceil(node_size / nparts)
  2. greedy fill on LINE boundaries up to `target`
  3. HARD GUARANTEE: any part still > cap gets windowed on char boundaries
  4. overlap: pull the previous part's last whole line forward --
     ONLY if the result still fits under the cap
```

### Why steps 3 and 4 are mandatory, not defensive

**Step 3:** step 2 can overshoot. A first attempt produced a 2,488-char part and
only an assertion caught it. Without the windowing pass you emit an invalid span
and the whole submission is rejected.

**Step 4:** extending a part's start backward *grows its width*. Overlap is
itself capable of pushing a part over the cap. A second attempt hit exactly
this. So the overlap is conditional on the widened part still fitting.

### Verified

```
223 oversized nodes split across 120 real files
largest emitted chunk: 2000 (cap 2000)  OK
no part exceeds cap, none escapes its node

overlap_lines=0: 66/67 = 99%
overlap_lines=1: 66/67 = 99%
overlap_lines=2: 66/67 = 99%
```

### Why overlap_lines = 1

0, 1 and 2 all give 99%, so overlap does not move recall *on average* --
reference spans (median 878) sit comfortably inside 2000-char parts, so padding
mostly just grows the union.

But overlap removes a real failure mode. Without it, a span landing just past a
cut boundary is lost entirely:

```
truth [63,110), part 1 ends at 60  ->  captures 0  ->  IoU = 0  FAIL
truth [63,110), part 2 starts at 40 ->  captures 47 ->  IoU = 0.59  PASS
```

One line of overlap costs nothing and eliminates the boundary miss. Two is
redundant.

**Note:** "repeat the last sentence" does not translate to code -- there are no
sentences. The unit is a **line**, and cutting mid-identifier
(`add_argum` / `ent(...)`) is what to avoid.

### Carry into your implementation

Assert both, in code, not comments:

```
assert part_end - part_start <= max_chunk_size     # hard subject constraint
assert original[first:last] == chunk.text          # round-trip
```

`flake8` clean. `mypy` reports missing return annotations on the Manager stub
methods and an untyped `chunk()` in `chunking/chunk.py`. Subject V.1 requires
both to pass; V.2 makes `lint` mandatory.

## Retrieval with bm25s -- DECIDED (2026-11-04)

### What `index` does now

`Cli.index` -> `save_index(chunks)` -> `create_indexable_data(chunks)`
(`src/retrieval.py`). BM25 is built **once** in `index` and saved to
`data/processed/bm25/`. `search` only loads it.

- `make_tokenizer()` is the single definition of "text -> words". `index`
  and `search` both call it, never two implementations
- `code_splitter` keeps each identifier whole AND adds its parts:
  `LLMEngine` -> `llmengine`, `llm`, `engine`;
  `get_kv_cache_spec` -> whole word + `get`, `kv`, `cache`, `spec`
- `lower=False` is required, otherwise bm25s lowercases before the splitter
  sees the capitals
- `texts` must be in the same order as `chunks`: BM25 returns **positions**,
  and `chunks[pos]` turns a position back into file path + indices
- Verified: LoRA dataset question -> `docs/features/lora.md [4695:6098]` first

### The three `tokenize` arguments that matter

| Argument | What it does | Where |
|---|---|---|
| `return_as="tuple"` | also returns the word list, so bm25s matches words by spelling. Without it `index` crashes on save with `Dict key must be str` | `index` and `search` |
| `update_vocab=True` | adds new words on every call, not only the first | queries (`search`, `search_dataset`) |
| `show_progress=False` | hides bm25s's own progress bar | optional |

### Problem 1 -- reusing one tokenizer loses words

The tokenizer only adds new words while its dictionary is **empty** (default
`update_vocab="if_empty"`). Reusing it for a second question silently drops
every word the first question didn't have:

```
"How do I load a LoRA adapter?"  -> words found
"What is the kv cache spec?"     -> kv, cache, spec MISSING
```

**Fix:** `update_vocab=True` on the query side. One rule, works for 1 or 200
questions. Safe because of `return_as="tuple"`: the query dictionary is
temporary and never touches the saved index. `index` is fine as is (all chunks
tokenized in one call into an empty dictionary).

### Problem 2 -- bad questions (subject: "empty query, nonsensical query")

Measured on the real index:

| Question | Words left after tokenizing | Top scores |
|---|---|---|
| `"   "`, `"the"`, `"?!"` | none (only `""`) | 5.59, 5.59 -- **fake** |
| `"zzzqqq"` | `zzzqqq` | 0.0, 0.0 |
| `"how to load lora"` | `how`, `load`, `lora` | 4.91, 4.77 |

No library needed: only the tokenizer and bm25s's output know what the index
can use.

- **Case A -- no real words** (only `""` in the tuple's `vocab`): the 5.59
  results come from chunks that also contain the empty word. They look real
  but are not. -> **warn, return an empty list of sources**
- **Case B -- real words, top score 0**: nothing in the corpus matches.
  -> **warn, still return the k results**

Decided: always answer, warn the user. In `search_dataset` the question still
gets its entry (empty sources in case A), so the output file keeps its shape.
Don't print 200 warnings -- count them and print one line at the end.

Flow per question:

```
1. tokenize the question
2. only "" left?      -> warn, no sources
3. retrieve
4. top score == 0?    -> warn, return results anyway
```

Open: which file holds these checks so `search` and `search_dataset` share
them without copying.

### Still to fix (from the 2026-11-04 review)

- `cli.py`: `print(args)` in `search` is debug code
- `search` checks `data/processed/` exists; it should check
  `data/processed/bm25/` (and `chunks.json`), and the message should say
  `python -m src index`
- `retrieval.py`: the `try` wraps tokenize + build too; only `retriever.save`
  raises `OSError`
- mypy: `bm25s`, `tqdm`, `fire` have no type info -- install stubs or ignore
  those modules in `pyproject.toml`
- Subject: "All input and output paths must be configurable CLI arguments and
  never hard-coded" -- `create_indexable_data` always writes to
  `PROCESSED_PATH`
- tqdm is required for long-running operations; bm25s's bars are tqdm, or use
  your own step bar with `show_progress=False`

## Makefile notes

- Quotes around `ARGS` on the *variable definition* break it -- make passes one
  token. Quote only on the command line: `make run ARGS="index --k 10"`.
- `lint-strict: flake8` refers to a target that doesn't exist; make errors.
  V.2 wants lint-strict to run **both** `flake8 .` and `mypy . --strict`.
- `debug` runs `python -m pdb .` which points pdb at a directory.

---

# TO BE DONE

## Next steps -- status as of 2026-11-02 (commit `9e8026c`)

**Where things stand:** chunking is done with `langchain_text_splitters`
(`Chunk` class, `.py` / `.md` / `.txt`), and `index` writes
`data/processed/chunks.json` through pydantic. Measured on the full corpus:
14,634 chunks in ~0.8 s, every `text[first:last] == content`, and no chunk wider
than 2000. Stages 0-2 below describe the earlier Manager + `ast` plan; there is
no `Manager` and no `ChunkCode` in `src/` now, so read them as history, not as
TODOs.

### A. Tidy up what was just written (small, do first)

- [x] mypy: 3 missing return types -- `Cli.index` (`cli.py:30`),
      `Chunk.chunk_markdown` (`chunk.py:62`), `load_json` (`json.py:11`).
      flake8 is clean
- [x] `__main__.py`: the `except Exception` branch prints but exits **0**. Add
      `sys.exit(1)` so a failure is a failure (KeyboardInterrupt too, usually
      `130`)
- [x] `.gitignore`: add `data/processed/` and `data/output/`. `chunks.json` is
      currently untracked and not ignored, so one `git add .` commits ~30 MB
- [x] Rename `src/json.py` (shares the stdlib name) -> e.g. `storage.py`, and
      `load_json` -> `save_index`, since it writes. The real loader comes next
- [x] `Cli.search` still does the manual `int(k)` checks -- switch it to
      `SearchArgs`, with the same `try/except ValidationError` as `Cli.index`
- [ ] Edge cases to test by hand once `search` uses `SearchArgs`:
      `search "   "` (whitespace-only query passes `min_length=1`),
      `search 123` (Fire passes an int, pydantic rejects it as "not a valid
      string"), `search hi --k` (Fire passes `True`; `strict=True` on `k`
      already rejects it)
- [x] Decide the chunk model: `MinimalSource` carries `size` + `content`,
      `ChunkData` adds `text` (duplicate of `content`). Suggested: keep
      `MinimalSource` exactly as the subject defines it, put `content` on
      `ChunkData`, store `ChunkData` in the index, emit plain `MinimalSource`
      in search output (otherwise every retrieved source carries 2000 chars)
- [x] Makefile: `lint-strict: flake8` depends on a target that doesn't exist

### B. Finish persistence (Stage 3)

- [x] `load_index(processed_path) -> list[ChunkData]` next to `save_index`:
      `model_validate_json`, catch `OSError` / `ValidationError`, and a missing
      file -> `CliError("No index found, run 'index' first")`
- [x] On load, assert no span exceeds 2000 (`last - first`) -- one oversized
      source invalidates the whole output for the moulinette

### C. Retrieval (Stage 4) -- the next real feature

- [x] Tokenizer shared by index and query; split `snake_case` / `CamelCase` AND
      keep the whole identifier (70/99 code questions quote identifiers) --
      `make_tokenizer()` in `src/retrieval.py`
- [x] BM25 with `bm25s`, built and saved in `index` to `data/processed/bm25/`
      (see "Retrieval with bm25s -- DECIDED")
- [x] Query side: `update_vocab=True` (problem 1) and the two bad-question
      checks (problem 2)
- [x] Load the index once per process, never per question (90 s / 200 q budget)
- [ ] `search <query> --k`: print ranked `file_path` + span
- [ ] `search_dataset`: read `RagDataset`, one entry for **every** question,
      write `StudentSearchResults` to `<save_directory>/<dataset filename>`,
      tqdm over questions, `indent=4`
- [ ] Run the moulinette on docs + code: targets recall@5 >= 0.80 docs,
      >= 0.50 code

### D. Then

- [ ] Stage 5 `evaluate` (own recall@k, rules listed below)
- [ ] Stage 6 answer generation with Qwen3-0.6B
- [ ] Stage 7 edge cases, Stage 8 README + chunk-size sweep, Stage 9 bonus

## Stage 0 -- Foundations (do first, nothing else is testable without these)

- [x] `ChunkData` in `src/models.py`, extending `MinimalSource` with `text`
- [ ] Line-start table: absolute char offset of every `\n` per file
- [x] Fix `src/chunking/__init__.py` -- it imports `from .parser import Parser`,
      a module that does not exist, so `import src.chunking` raises
      `ModuleNotFoundError`
- [x] Fill in `chunk()` signature with annotations: `chunk(self, path: Path,
      text: str) -> list[ChunkData]`
- [ ] mypy: return annotations on the Manager methods (8 errors currently)
- [x] flake8: missing newline in `chunk_code.py`
- [x] Print a confirmation + chunk count from `Manager.index` -- `Cli.index`
      currently discards the return, so success is invisible


## Stage 4 -- Retrieval

- [ ] Tokenizer: shared between index and query (never two implementations)
- [ ] Keep `skip_sampler_cpu_output` whole AND split -- 70/99 code questions
      quote identifiers verbatim
- [ ] Inverted index: `term -> [(chunk_id, tf)]`, precomputed at index time
- [ ] BM25 with Lucene IDF variant (`+1`) -- Robertson/Sparck Jones goes
      negative when `df > N/2`, which is common on a code corpus
- [ ] `Manager` caches the loaded index -- once per process, not per question
- [ ] Validate `k`, check `dataset_path` exists, create `save_directory`
- [ ] Sort results by descending score -- the grader never sorts for you
- [ ] Emit an entry for **every** question; omission is a silent zero
- [ ] Write `StudentSearchResults` with exact `data/raw/...` paths

## Stage 5 -- Evaluate (**after Stage 1, before Stage 2**, see Build order)

The rule itself -- port it, do not re-derive it:
- [ ] True IoU, `inter / (len1 + len2 - inter)`. Not `inter / len(gt)`, not
      `inter / len(retrieved)`
- [ ] Half-open spans, `length = last - first`, no `+1`
- [ ] Strict `>` on IoU 0.05 -- exactly 0.05 must FAIL
- [ ] Per-source 0/1 with `break` on first hit, denominator `len(true_sources)`
- [ ] Empty ground-truth sources -> 1.0; empty predictions -> 0.0
- [ ] Omitted questions score 0 and still count in the denominator
- [ ] Unknown `question_id` reported clearly -- do NOT paper it over as a zero,
      the real grader raises `KeyError` and the run dies

Plumbing it needs:
- [ ] `src/evaluating/` -- new package, keeps the metric out of `manager.py`
- [ ] Dataset IO: load `RagDataset` from `AnsweredQuestions/*.json`
- [ ] Key on `question_id`, **not** position. The four dataset files do line up
      positionally today (identical id sets, identical order, 99/99 and
      100/100), but the private set may not oblige, and a wrong key is fatal
- [ ] Report recall@1, @3, @5, @10. The moulinette reports exactly these
      (`k_values = [1, 3, 5, 10]`) and VI.1 demands a chunk-size sweep, so a
      single number is never the deliverable
- [ ] **No import from `others_to_delete/` anywhere under `src/`.** Reading the
      grader is not calling it -- VI.6 forbids the latter. Keeping the recovered
      code outside the solution tree makes that structural, not a promise

The two bracketing tests:
- [ ] **Oracle:** feed ground-truth `sources` back as `retrieved_sources`, write
      to `data/output/search_results/AnsweredQuestions/`, assert **1.0**. If not
      1.0, the format is wrong and every other number is meaningless
- [ ] **Complement:** same file with `"retrieved_sources": []` -> assert **0.0**
- [ ] Pre-flight on the oracle file before scoring: every `question_id` present
      in the ground truth, and no span wider than 2000 by `last - first`
- [ ] Wire `Manager.evaluate`. `Cli.evaluate` is already correct and needs no
      change

## Stage 6 -- Answer generation

- [ ] Qwen/Qwen3-0.6B, weights outside the repo (`HF_HOME` already points to
      `/sgoinfre` on campus)
- [ ] Do NOT make the model emit JSON -- generate plain text, attach it to
      `MinimalAnswer` in Python
- [ ] Read `max_position_embeddings` from the config; don't assume
- [ ] Refusal clause in the system prompt; ask it to name the source file
- [ ] Greedy / temperature 0 for determinism
- [ ] Load the model ONCE, not per question
- [ ] `answer_dataset` copies `retrieved_sources` from its input file
- [ ] Output `StudentSearchResultsAndAnswer`

## Stage 7 -- Robustness (VI.6 edge cases)

- [ ] Empty query
- [ ] Nonsensical query
- [ ] `k=0`, `k` larger than the index
- [ ] Missing files, malformed JSON
- [ ] Unreadable / binary / CRLF files during ingestion
- [ ] No unhandled traceback in any path; non-zero exit on failure
- [ ] tqdm progress bars on `index` and `search_dataset` (V.4 requires them,
      and `tqdm` is not yet in `pyproject.toml` dependencies)

## Stage 8 -- Submission

- [ ] README: italic first line, Description, Instructions, Resources
- [ ] README: System architecture, Chunking strategy, Retrieval method,
      Performance analysis, Design decisions, Challenges faced, Example usage
- [ ] **Chunk-size sweep** -- VI.1 requires reporting the effect on recall@k.
      This is what fills Performance analysis
- [ ] README: how AI was used, for which tasks and which parts
- [ ] `data/output/` directories created as the layout requires
- [ ] `uv sync` verified from a clean checkout
- [ ] Remove the dead `[tool.uv.sources] llm-sdk` entry
- [ ] `make lint-strict` actually runs both tools
- [ ] `make debug` points at a runnable script

## Stage 9 -- Bonus (only after the mandatory part fully validates)

- [ ] 1. Semantic embeddings (`all-MiniLM-L6-v2`) alongside the lexical index
- [ ] 2. Hybrid retrieval -- **RRF** (`1/(c + rank)`), not weighted score sums;
      BM25 is unbounded while cosine is [-1, 1]
- [ ] 3. Incremental indexing -- content hash vs mtime+size; hashing is
      nearly free if the indexing loop already reads every file
- [ ] 4. Caching -- index and query results; shares the cache-key design with 3
- [ ] 5. Local HTTP API -- read-only query and answer endpoints, not index build

---

## Open decisions (need your answer before the dependent stage)

| Decision | Blocks | Options |
|---|---|---|
| Oversized-node fallback | -- | **DECIDED** -- equal parts, line-aligned, 1 overlap line |
| Where the suffix rule lives | Stage 1 | **DECIDED** -- factory in the chunking package: `Chunk.selection` (`chunking/chunk.py:15-30`) already is one |
| Index format | Stage 3 | **DECIDED** -- JSON, one `data/processed/chunks.json` |
| IDF variant | Stage 4 | Lucene `+1` (safer) vs Robertson (goes negative on code) |
| `b` and `k1` | Stage 4 | sweep; chunks vary ~40x in length so `b` will move recall |
| Retrieval `k` vs generation `k` | Stage 6 | same `k`, or wide retrieval + narrow context |



Almost. The idea is right, but there's one trap in reusing it exactly as it is. I measured retrieve_sources in its two parts on your index:

loading the index + chunks.json   0.37 s
searching one question            0.003 s

Right now retrieve_sources does both every time it's called. If search_dataset calls it once per question:

200 questions × 0.37 s ≈ 74 s of loading     (the subject's limit: 90 s)
200 questions × 0.003 s ≈ 0.6 s of searching

That's 99% of the time spent reloading the same files 200 times. It might still pass, but only just, and the private dataset or a slower school computer could push it over. Your working notes already say it: "Load the index once per process, never per question."

The "minor change"

Split the loading from the searching:

1. A load function opens the index and chunks.json and runs the num_docs check. It returns the retriever and the chunk list. This is the top half of your current retrieve_sources.
2. retrieve_sources receives the retriever and the chunk list as parameters, instead of loading them. Everything from make_tokenizer() onwards stays as it is.

Then:

- search calls load once and retrieve_sources once.
- search_dataset calls load once, then loops retrieve_sources over the questions with tqdm.

The loop in search_dataset also builds a MinimalSearchResults for each question: its question_id, its question, and what retrieve_sources returned. After the loop it wraps them in a StudentSearchResults with k and saves the file.

One design question: the tokenizer is cheap to create, but should retrieve_sources still create a new one on every call? update_vocab=True makes reusing one safe, but there are arguments both ways.




Here's the plan for answer_dataset, in words. You already have every building block.

The key difference from answer

answer_dataset does no search. Its input is the JSON file that search_dataset already wrote (a StudentSearchResults), so every question already comes with its retrieved_sources. So:

- no prepare_retrieval;
- no retrieve_sources;
- no bm25s at all.

The steps, in order

1. Validate the arguments. You already have this with AnswerDataArgs. While you're there, remove the debugging print(args) on line 175.
2. Load the input file into the model. Read the JSON at student_search_results_path and turn it into a StudentSearchResults with model_validate, the same pydantic method you used in build_sources. You get two things for free:
   - a check: a malformed file raises an error you can turn into a clean message;
   - real objects: each entry is already a MinimalSearchResults holding real MinimalSource objects, ready for read_sources.

   Remember k from that file too, because the output needs it.
3. Load the LLM once, before the loop. Creating LLM() takes several seconds. Inside the loop, that would cost 100 × that.
4. Loop over search_results with tqdm. For each entry:
   - read_sources(entry.retrieved_sources) gives you the texts;
   - llm.generate_response(entry.question, entry.retrieved_sources, texts) gives you the answer string;
   - build a MinimalAnswer from the entry's three fields plus answer, and append it to a list.
5. Wrap up and save. Put the list and k into a StudentSearchResultsAndAnswer, then write it to save_directory, using the same file name as the input file. That's what the subject's walkthrough shows, and you already get the name with Path(...).name in search_dataset.

Two decisions for you

1. Empty sources. Some entries were saved with retrieved_sources empty, after a WORD_ERROR or CHUNK_ERROR in search_dataset. Should you still call the LLM for those? What answer should go in the file? The entry must still be written either way, so the question count stays the same.
2. Saving. save_search_results writes a StudentSearchResults. Would you make it more general, so it can save either model, or write a second save function? Look at what it actually does with its arguments before you decide.

A heads-up on time

At about 15 to 25 s per answer on CPU, 100 questions take 30 to 40 minutes. While you develop, test on a small file: copy the search results JSON and keep only 3 questions.
