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

## Makefile notes

- Quotes around `ARGS` on the *variable definition* break it -- make passes one
  token. Quote only on the command line: `make run ARGS="index --k 10"`.
- `lint-strict: flake8` refers to a target that doesn't exist; make errors.
  V.2 wants lint-strict to run **both** `flake8 .` and `mypy . --strict`.
- `debug` runs `python -m pdb .` which points pdb at a directory.

---

# TO BE DONE

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

## Stage 1 -- Ingest -> Chunk handoff (plumbing, no algorithm yet)

Get one chunk coming out the other end before writing any `ast` logic. Getting
the plumbing visible first is much easier to debug than finding it afterwards
inside a splitter.

- [ ] Fix `chunk()` signature in `chunking/chunk.py`: add `self`, add
      annotations, accept `max_chunk_size` at construction not per call
- [ ] `ChunkData` in `src/models.py`, extending `MinimalSource` with `text`
- [ ] Suffix dispatch: `.py` -> `ChunkCode`, `.md` -> `ChunkMarkdown`,
      `.txt` -> text strategy. Decide whether the rule lives in `Manager.index`
      or as a factory in the chunking package
- [ ] Rewrite `ingest()` -- it currently discards the text. Either return it, or
      drop the separate method and let `Manager.index` walk and read in one pass
- [ ] Handle `read_file` returning `str | None` -- skip unreadable files, never
      pass `None` to a chunker
- [ ] Keep walk and read in ONE loop. Do not call `collect_files()` per file
- [ ] Build one chunker holding `max_chunk_size`, loop all files through it
- [ ] `Manager.index` prints a confirmation + chunk count -- `Cli.index`
      currently discards the return, so success is invisible
- [ ] Confirm the plumbing with `ChunkCode`'s body still empty

## Stage 2 -- Chunking algorithms

- [ ] Line-start table per file (converts `ast.lineno` -> character offset)
- [ ] `ChunkCode`: parse, top-level def/class, decorator-aware
      (`node.decorator_list[0].lineno`, not `node.lineno`)
- [ ] Oversized-node split: equal parts, line-aligned, `overlap_lines = 1`
      (see "Oversized nodes" above)
- [ ] Assert on every emitted part: `last - first <= max_chunk_size`
- [ ] Assert round-trip: `original[first:last] == chunk.text`
- [ ] Determinism: two runs -> byte-identical output. The defense re-runs the
      pipeline
- [ ] `ChunkMarkdown` -- headings, front matter, code fences. 71% of docs spans
      start at a line boundary, so headings genuinely align there
- [ ] `ChunkText` -- fixed-size windows (3 docs questions target `CMakeLists.txt`)
- [ ] Run across the whole corpus, **time it** (5 min budget)

## Stage 3 -- Persistence

- [ ] Pick format: pickle / JSON / SQLite
- [ ] Write to `data/processed/`
- [ ] Assert on load that no span exceeds 2000
- [ ] Round-trip check against the original files after reload
- [ ] Determinism of the persisted artifact

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

## Stage 5 -- Evaluate (build early -- it's standalone and testable)

- [ ] Port the recall rule faithfully: true IoU, `inter / (len1 + len2 - inter)`
- [ ] Half-open spans, `length = last - first`, no `+1`
- [ ] Strict `>` on IoU 0.05 -- exactly 0.05 must FAIL
- [ ] Per-source 0/1 with `break`, denominator `len(true_sources)`
- [ ] Empty ground-truth sources -> 1.0; empty predictions -> 0.0
- [ ] Omitted questions score 0 and still count in the denominator
- [ ] **Oracle test:** feed ground-truth `sources` back as `retrieved_sources`,
      must score 1.0. If not, the format is wrong and every other number is
      meaningless
- [ ] Complement test: empty `retrieved_sources` -> 0.0

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
| Where the suffix rule lives | Stage 1 | in `Manager.index`, or a factory in the chunking package |
| Index format | Stage 3 | pickle / JSON / SQLite |
| IDF variant | Stage 4 | Lucene `+1` (safer) vs Robertson (goes negative on code) |
| `b` and `k1` | Stage 4 | sweep; chunks vary ~40x in length so `b` will move recall |
| Retrieval `k` vs generation `k` | Stage 6 | same `k`, or wide retrieval + narrow context |
