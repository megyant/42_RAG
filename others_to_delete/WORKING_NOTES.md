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

1. `ChunkData` in models.py
2. line-start table (converts `ast.lineno` -> character offset)
3. `ChunkCode` on **one small file** -- check round-trip, cap, determinism
4. whole `.py` corpus + **time it** (5 min budget)
5. `ChunkMarkdown`
6. persist to `data/processed/`
7. one query, **no scoring** -- does the right file come back?

Step 7 before BM25. Cheapest signal on whether chunking is sane.

**Open decision:** the oversized-node fallback. A function > `max_chunk_size`
must still be split or the whole submission is invalid. Options: recurse into
nested defs, fixed-size windows, merge siblings.

## Open lint state

`flake8` clean. `mypy` reports missing return annotations on the Manager stub
methods and an untyped `chunk()` in `chunking/chunk.py`. Subject V.1 requires
both to pass; V.2 makes `lint` mandatory.

## Makefile notes

- Quotes around `ARGS` on the *variable definition* break it -- make passes one
  token. Quote only on the command line: `make run ARGS="index --k 10"`.
- `lint-strict: flake8` refers to a target that doesn't exist; make errors.
  V.2 wants lint-strict to run **both** `flake8 .` and `mypy . --strict`.
- `debug` runs `python -m pdb .` which points pdb at a directory.