# RAG Project — Notes on Phases 2 to 6 (Retrieval, Answering, Evaluation, Bonus, Submission)

> Companion to `CHUNKING_NOTES.md`, which covers indexing (subject VI.1). **Advisory notes, not a design document.** The assignment subject is the authority.

---

## 0. Build order — get a number before you optimise

Retrieval quality is the thing you are graded on (subject VI.2: 80% recall@5 on docs, 50% on code). Everything in this file is speculation until you have a **baseline number**.

Recommended sequence:

1. **Count the corpus.** See §6 for the measurement — it is already done for you in this file's companion notes.
2. **Profile the ground-truth ranges.** See `CHUNKING_NOTES.md` §3. Highest-value hour available.
3. **Build the dumbest thing that works.** Fixed-size windows, a plain inverted index, textbook BM25. Get a recall@k number.
4. **Classify your failures.** Wrong file, or right file wrong region? These need opposite fixes.
5. **Tune deliberately.** Chunk size, tokenizer, field boosting — one variable at a time, measuring each.
6. **Only then build answer generation.** It is graded separately and does not block retrieval.

Step 6 is worth emphasising: you can hit both pass thresholds with mediocre answers, because subject VI.3 says grading *"prioritises retrieval quality, grounding and prompt strategy over perfect final phrasing."* Do not let answer generation block a passing retrieval score.

---

## 1. Retrieval (subject VI.2)

### 1.1 What is required

- Return the top-k most relevant snippets.
- Each result is `file_path` + `first_character_index` + `last_character_index`.
- At most **2000 characters** wide.
- Must work for a single query **and** in batch over a whole dataset.
- Implement **TF-IDF or BM25** (at least one). BM25 is your stated reference.
- ≤ **90 seconds for 200 questions** on CPU-only hardware.

That throughput budget is worth converting into an engineering constraint immediately:

> 90 s / 200 questions = **450 ms per question**

Now consider the naive approach: scoring a query against every chunk requires tokenising every chunk, every time. If your index holds ~50 000 chunks, that is 50 000 tokenisations per query, 10 million across the dataset. You will blow the budget by orders of magnitude.

**Conclusion: precompute at index time.** Build a real inverted index — `term -> [(chunk_id, term_frequency), ...]` — and store per-chunk length. Query time then touches only chunks containing query terms.

**Question for you:** how many chunks will your corpus produce? That number times 200 is the naive cost, and it is the whole argument for the inverted index. Get it before choosing a data structure.

### 1.2 The BM25 formula, and the two parameters you will actually tune

```
score(Q, D) = Σ  IDF(q) · ( f(q,D) · (k1 + 1) )
              q∈Q        ─────────────────────────────────
                          f(q,D) + k1 · (1 - b + b · |D|/avgdl)
```

Three terms, and each one has a failure mode specific to your corpus:

**`f(q,D)` — term frequency.** Saturating, unlike raw TF. Chunks are short (200–2000 chars) so raw TF would be dominated by one repeated identifier.

**`|D|/avgdl` — length normalisation, controlled by `b`.** Default `b ≈ 0.75`.
- `b = 0` → no length penalty; a 2000-char chunk matches everything, a 50-char chunk matches nothing.
- `b = 1` → full normalisation; a chunk is scored as though it were average length.

**Your chunks vary in length by roughly 40×.** So `b` is not a default to accept here, it is a parameter that will visibly move your recall. Sweep it.

**`k1`** (≈1.2–1.5) controls how quickly term frequency saturates. Lower `k1` makes the scorer closer to a boolean "does this term appear"; higher `k1` rewards repeated mentions. For code, where an identifier may repeat many times in one chunk, `k1` is worth checking.

### 1.3 The IDF trap — this will silently cost you recall

There are two IDF variants in common use:

```
Robertson/Sparck Jones:   ln( (N - df + 0.5) / (df + 0.5) )
BM25 (Lucene) variant:    ln( (N - df + 0.5) / (df + 0.5) + 1 )
```

**The difference matters enormously for your corpus.** In a Python codebase, the most frequent terms — `return`, `self`, `def`, `class`, `None`, `vllm`, `default`, `import` — appear in a large fraction of all chunks. Often more than half.

When `df > N/2`, the plain Robertson/Sparck Jones numerator `N - df + 0.5` goes **negative**, and the logarithm produces a **negative IDF**. A negative IDF means matching that term *subtracts* from a chunk's score.

So a chunk containing many occurrences of a common word gets **penalised** for containing it. On a code corpus this is not a subtle degradation — the corpus is dense in exactly the terms that trigger it.

**The `+1` variant keeps IDF non-negative for all terms and is the safer default.**

**Question:** compute, in your index, the fraction of chunks where `df > N/2`. If it is non-trivial, print the IDF of your ten most common terms and check for negatives before anything else. This is a five-minute check that can be the difference between passing and failing.

### 1.4 The paraphrase gap — the central difficulty

Subject VI.1 names it: *"a question may paraphrase an idea or quote an identifier verbatim."*

Ground truth example:

> *"What's the default value of trust_remote_code in vLLM's LLM class constructor?"*

The tokens `trust_remote_code` may never appear in the question at all. And BM25 scores **zero** for any query term absent from a chunk — so a question phrased entirely in prose about an identifier you never mention is unanswerable by lexical retrieval alone.

Look at the actual ground truth and classify: how many questions quote identifiers verbatim, and how many purely paraphrase? That ratio tells you how much this gap will cost you.

**Measured — questions containing a snake_case identifier:**

| | with identifier | without |
|---|---|---|
| code | **70 / 99** | 29 |
| docs | **9 / 100** | 91 |

**This inverts the assumption in §1.5 and §1.6.** The paraphrase gap is not mainly a code problem — it is a **docs** problem. 91% of docs questions are pure prose, while 71% of code questions quote an identifier verbatim.

That matters because your thresholds are 80% docs and 50% code. The harder dataset is already the harder one. Concretely:

- **On code**, identifier-preserving tokenization (§6 of `CHUNKING_NOTES.md`) is likely to be decisive. Keep `trust_remote_code` whole as well as split.
- **On docs**, the paraphrase gap is the whole game, and pure BM25 has little to grip. This is the strongest argument in the whole project for the hybrid/embedding bonus (§4) — but only after the mandatory part validates.
- Stopword handling should be measured **separately per dataset**, not globally: removing English stopwords probably helps docs and does nothing useful for code.

### 1.5 Mitigations, cheapest first

**A. Index document-level context alongside the chunk body.** This is the highest-value cheap trick, and it is really a *chunking* decision (see `CHUNKING_NOTES.md` §0, decision 2). Prepend `file_path` and the enclosing symbol name to each chunk's indexed text.

For `vllm/entrypoints/llm.py`, the question above about the "LLM class constructor":
- the body may never contain `trust_remote_code` near the top of the file
- but the **path** contributes `vllm`, `entrypoints`, `llm`
- the **enclosing symbol** contributes `LLM`, `__init__` / `constructor`

Now the question has terms that actually match. This is standard IR field weighting.

**Question:** does adding the path to the indexed text help or hurt? It is not obviously good — every chunk in `llm.py` inherits `vllm` and `llm`, so it adds low-IDF terms to every chunk in that file. Measure, do not assume.

**B. Weight fields differently.** Once you have path/symbol/body as separate fields, you can score them with different weights. That is still BM25 with a boost on one field. Defensible as "BM25 implemented"; describe it accurately in the README.

**C. Index identifiers twice — whole and split.** `skip_sampler_cpu_output` as one term *and* `skip`, `sampler`, `cpu`, `output`. This bridges prose phrasing to identifier naming. But recall the IDF interaction from §1.3: the whole-identifier form has `df = 1`, giving it an enormous IDF that can swamp everything else. **How do you stop a df=1 term dominating?** Consider capping or flooring IDF, and test it.

**D. Bigram / phrase scoring.** Cheap and effective on code, where `def load_lora_adapter` is far more informative than its unigrams. Costs index size.

**E. Semantic embeddings.** This is bonus item 1. It is the real answer to the paraphrase gap. Do it **after** lexical works, as a comparison — not as a replacement, because bonus is only graded if the mandatory part fully validates.

### 1.6 Stopwords on a code corpus

Standard English stopword lists are wrong for Python.

- `return`, `class`, `self`, `import`, `None`, `True`, `if`, `for` are **meaningful** here, not noise.
- But `the`, `is`, `a`, `of` appear constantly in your **docs** chunks, and they are genuinely uninformative there.

**So the right answer may be different stopword handling for code files and markdown files.** Or none at all — with proper IDF, common terms get down-weighted anyway, which is what §1.3's IDF discussion is about.

**Question:** does removing English stopwords help or hurt each dataset separately? Your two datasets have different thresholds (80% docs, 50% code) and different characteristics, so measure them separately.

### 1.7 File-level versus chunk-level ranking

Carried over from `CHUNKING_NOTES.md` §2, because it is the thing most likely to sink you:

> A result in a different file never counts.

Every public ground-truth record has **one** source, so recall@k is effectively a **per-question hit rate**. The only question that matters is: *does the right file appear in my top 5?*

This means your chunker and your scorer are coupled through the top-k cap. More chunks per file means more of them competing for the same 5 slots.

**Once you have a baseline, classify every failure:**
- correct file present in top 5 but no overlapping chunk → granularity / IoU problem
- correct file absent from top 5 → ranking problem

Fix them with completely different changes. Do not guess which one you have.

### 1.8 Query-side/index-side symmetry

A silent killer: if you tokenise queries differently from the index, every unmatched token contributes zero and you lose recall with no error message.

Make the tokenizer a **single shared function** used by both paths. Then assert it: tokenise a known identifier, assert you get the tokens you expect.

---

## 2. Answer generation (subject VI.3)

Required model: **Qwen/Qwen3-0.6B** (you may substitute, but it must still work with this one).

### 2.1 The tension between the two stages

This is the most important thing to understand about the answering stage:

| Stage | Wants |
|---|---|
| Retrieval | small, precise chunks → higher hit rate |
| Answering | more context → the model can actually ground an answer |

With `k = 10` sources at up to 2000 chars each, you could feed ~20 000 characters (roughly 5 000 tokens) into a **0.6-billion-parameter** model. That will produce confident nonsense. Small models degrade badly with long, noisy context.

**Question:** does the `k` used for scoring retrieval have to be the same `k` you feed the generator? The output schema wants both `retrieved_sources` and `answer` in one object, so there may be room to retrieve with a wide `k` for the recall metric and answer from a narrower selection. Check whether the spec allows that, and measure both.

### 2.2 Do not make the model emit JSON

The obvious implementation is to prompt Qwen to return JSON matching `MinimalAnswer`. A 0.6B model will not do this reliably — you will spend your time on JSON parse errors that are not retrieval problems.

**The decoupling:** generate plain text, then attach it to the pydantic model **in Python**:

```python
# illustrative shape only — not an implementation
answer_text = generate(context, question)      # free text
result = MinimalAnswer(**search_result, answer=answer_text)
```

The schema is enforced by pydantic, not by the model. This is more robust and far less work.

**Question:** what evidence do you have that the model must produce the JSON itself? Subject VI.3 says *"produce structured JSON following the provided pydantic models"* — but it does not say the model must be the one to serialise it. If you conclude the same thing, note the reasoning in your README's Design decisions section.

If you *do* want constrained generation, look into guided decoding libraries — `outlines`, `lm-format-enforcer`, `xgrammar`. Treat that as a separate experiment.

### 2.3 Prompt design for a weak model

Given a 0.6B model, the prompt does most of the work. Consider:

- **System role:** state that answers must come only from the provided context.
- **Refusal clause:** tell it what to do when the context does not contain the answer. Without this, a weak model confabulates.
- **Citation habit:** ask it to name the file it drew from. Cheap, and it makes hallucination visible during your own testing.
- **Few-shot:** for a small model, one or two examples often beat elaborate instructions.
- **Decoding:** greedy / temperature 0 for factual extraction. You want determinism — see `CHUNKING_NOTES.md` §7.

**Question:** how will you *measure* grounding? Subject VI.3 grades "no major hallucination." With a 0.6B model you cannot trust an LLM judge. A lexical proxy — what fraction of the answer's content words appear in the retrieved context — is crude but measurable and honest. **Is that good enough evidence for your Performance analysis section?**

### 2.4 Check the tokenizer, do not assume

Before designing around a token budget, read the actual `tokenizer_config.json` / `config.json` for Qwen3-0.6B and find `max_position_embeddings`. Do not assume a number.

### 2.5 Throughput

`answer_dataset` runs over a whole dataset (~100 public questions). The Qwen3-0.6B weights are a few GB; loading once and batching matters. Consider whether batching prompts is worth the complexity, and measure.

`llm_sdk` from your `call_me_maybe` project already wraps a small HF causal LM with `Qwen/Qwen3-0.6B` as its default. Reusing it is legitimate — but note the path problem flagged in `CHUNKING_NOTES.md` §8, since `uv sync` must work from the repo root.

---

## 3. Evaluation (subject VII)

### 3.1 What `evaluate` has to be

Subject VI.6, verbatim:

> The `evaluate` command is for your own iteration. The official recall@k used during the defense is computed by the provided moulinette executable, not by your code. **Your solution must never import or call the moulinette.**

So `evaluate` is a **genuine reimplementation** of the overlap rule, written by you, for your own iteration.

### 3.2 The IoU arithmetic — read this before fixing your chunk size

Subject VII.1.1 says a source counts as found when it is in the same file and overlaps, with *"an IoU of 0.05"*.

Assuming that means intersection-over-union of the two character ranges:

```
inter = max(0, min(g1, r1) - max(g0, r0))      # ground truth, retrieved
union = max(g1, r1) - min(g0, r0)
IoU   = inter / union
```

Now consider the two extreme cases, with ground-truth length `L`:

**Retrieved chunk entirely inside the ground truth:**
```
IoU = |chunk| / L        →  need  |chunk| ≥ 0.05 · L
```

**Retrieved chunk entirely covering the ground truth:**
```
IoU = L / |chunk|        →  need  |chunk| ≤ 20 · L
```

Work out what these bounds mean in practice:

| Ground-truth span `L` | Chunk must be at least | Chunk must be at most |
|---|---|---|
| 12 chars (e.g. `trust_remote_code = False`) | 1 char | **240 chars** |
| 200 chars | 10 chars | 4000 chars (no real limit) |
| 1000 chars | 50 chars | 20 000 (no real limit) |
| 2000 chars (max possible) | **100 chars** | 40 000 (no real limit) |

**Two counter-intuitive consequences:**

1. **Tiny chunks are not safe.** A 50-char chunk scores `50/2000 = 0.025` against a maximum-length ground-truth span — **it fails**, because the union is huge. To be safe against *any* span up to 2000 chars, a chunk needs to be **at least ~100 characters**.

2. **Large chunks are not safe either.** A full 2000-char chunk scores `12/2000 = 0.006` against that 12-character ground truth — **it fails too**. To be safe against tiny spans, a chunk must be **at most 240 characters**.

So the IoU bar is a **squeeze from both sides**, and the safe window differs per question. This is the argument for chunk sizes around **150–500 characters** rather than at either extreme — and it is an argument you should verify empirically rather than trust, because I inferred the formula from a one-line description.

**Verify it two ways:**
- **Read the grader's source.** `others_to_delete/moulinette_RAG.zip` is in your repo. Unzip it and *read* the recall function. Note the distinction: subject VI.6 forbids **calling** the moulinette from your solution. Reading its source to understand the metric is not calling it.
- **Or calibrate empirically.** Construct a synthetic `StudentSearchResults` file with hand-chosen ranges against a real ground-truth dataset, and run the moulinette on it. This tells you the exact boundary without reading any source.

Do one of these before you finalise a chunk size.

### 3.3 The other failure modes your `evaluate` must handle

- **Multiple ground-truth sources per question.** The public data has exactly one each, but recall is *"the share of its correct sources"* — plural is real. A question you answer correctly for source A but miss for source B scores 0.5, not 1.0. **Does your implementation average per-question or pool all sources?** These give different numbers.
- **Fewer than k results returned.** A question where retrieval returns nothing scores 0 and must not divide by zero.
- **Empty ground-truth `sources`.** Skip it, do not crash.
- **Order matters.** Recall@k truncates your ranked list. **Is your list sorted by score descending?** If you emit results in arbitrary order, recall@k is measured on an arbitrary subset.

### 3.4 `k` and the output field

Your output declares `k`. Subject VII.1.2 requires recall@1, @3, @5, @10, so the moulinette truncates. **The `k` you declare and the `k` you actually return must agree** — returning more sources than you declared is likely a validation failure. The walkthrough uses `--k 10`.

---

## 4. Bonus (subject IX)

**Gate:** the bonus is graded **only after the entire mandatory part validates**, and *"a bonus counts only if it is implemented and working, not merely described in the README."*

Do not start these until retrieval passes. But note the dependencies:

| # | Bonus | Depends on |
|---|---|---|
| 1 | Semantic embeddings (e.g. `all-MiniLM-L6-v2`) | a working index to attach vectors to |
| 2 | Hybrid retrieval | bonus 1; also your lexical ranker |
| 3 | Incremental indexing | a cache-key design (see below) |
| 4 | Caching | a cache-key design |
| 5 | Local HTTP API | the index and query path already working |

**On #2 — how to fuse.** Weighted score sums fail here because BM25 scores are unbounded and unnormalised while cosine similarities live in [-1, 1]. You would be tuning a meaningless weight. **Reciprocal Rank Fusion** sidesteps this by combining *ranks* rather than scores:

```
RRF(d) = Σ  1 / (c + rank_i(d))
```

with `c ≈ 60` as the usual damping constant. It needs no score calibration at all. Look it up before inventing something.

**On #3 and #4 — they share one design problem.** Both need a way to decide *what has changed*. Compare:
- **mtime + size** — cheap, but a checkout or a `touch` invalidates everything
- **content hash** — correct, costs a full read of every file

Subject VI.1 gives you a 5-minute index budget. If you hash every file anyway, have you already paid most of the cost? **What does your indexing loop read, and does that make hashing nearly free?**

**On #5 — scope it.** A read-only query and answer API is a small job. Exposing index building over HTTP is a much larger and riskier one. Which is it?

---

## 5. README and submission (subjects VIII, X)

### 5.1 Requirements

Chapter VIII requires, at minimum:

- [ ] First line italicised, exactly: `This project has been created as part of the 42 curriculum by <login>`
- [ ] Description
- [ ] Instructions
- [ ] Resources — classic references **plus how AI was used, for which tasks and which parts**
- [ ] System architecture
- [ ] Chunking strategy
- [ ] Retrieval method
- [ ] Performance analysis (recall@k)
- [ ] Design decisions
- [ ] Challenges faced
- [ ] Example usage
- [ ] Written in **English**

The chunk-size sweep from `CHUNKING_NOTES.md` §10 step 4 is what fills Performance analysis. The section is not optional decoration — subject VI.1 explicitly asks you to *"report the effect on your recall@k"* when you use smaller chunks.

### 5.2 Submission (subject X)

Required in the repository:
- `src/`, `pyproject.toml`, `uv.lock`, `Makefile`, `README.md`

Layout required by VI.7.1 — see `CHUNKING_NOTES.md` §9 for the full status table. Three of those paths are still missing or wrongly nested.

**Critical constraint from X:**

> Do not include large data files, model weights, or generated outputs in your repository. The evaluator will generate these during the evaluation process.

**Check `.gitignore` for a `data/` entry.** Your current `.gitignore` is the standard Python template and I saw no `data/` rule in it. `data/raw/vllm-0.10.1` is a full vLLM checkout — thousands of files. If that is tracked, it must not be. Verify before your first push.

Model weights are a separate concern: your `Makefile` already points `HF_HOME` at `/sgoinfre/$(USER)/huggingface` on campus machines, which is the right instinct. Confirm the weights are actually landing there and not in the repo.

### 5.3 Recode step (subject X.1)

A brief live modification may be requested, feasible in a few minutes, to verify you understand the project. Common shapes: change a function's behaviour, alter a display, adjust a data structure.

**Practical implication:** keep a mental map of why each piece exists. In particular, be able to explain without looking:
- why your chunker splits where it does
- why your tokenizer treats identifiers the way it does
- why your `b` and `k1` values are what they are

Combine this with the Chapter III AI guidance and the README's AI-disclosure requirement: the two are in tension by design. **Be able to defend every line of your project, including lines you did not write.**

### 5.4 Robustness (subject VI.6)

> The CLI is tested with such edge cases and must never crash with an unhandled traceback.

Named cases to handle: empty query, nonsensical query, `k=0`, missing files, malformed JSON. Plus `k` larger than your index size, and paths outside `data/raw/`.

---

## 6. Corpus measurement — DONE

The open question from `CHUNKING_NOTES.md` §11 (Q1) is answered:

```
all files                                2867
.py + .md files                          1937
total chars in .py + .md        20,003,424
```

Derived budget numbers:

| Quantity | Value |
|---|---|
| Chunks at 400 chars | **~50,000** |
| Naive full-scan cost per query | 50,000 tokenisations |
| × 200 questions | 10,000,000 tokenisations |
| Your actual budget | 90 s total, 450 ms/query |

So §1.1's conclusion is not a preference, it is arithmetic: **you must precompute at index time.** A `term -> [(chunk_id, tf)]` inverted index touches only chunks containing query terms, typically a few hundred.

**On ingestion policy:** indexing only `.py` and `.md` matches 99% of ground truth (91/91 code files are `.py`; 55/56 docs files are `.md`). But note there is **one `.txt` file in docs ground truth**, so keep `.txt` in your suffix list — `ingest.py` already has it. Verify the corpus-to-ground-truth extension match yourself before you decide; the one `.txt` shows the sets are not perfectly identical.

---

## 7. Open questions

**Retrieval**
1. How many chunks does your corpus produce, and is your IDF non-negative across all terms (§1.3)? **Partly answered:** ~50,000 chunks at 400 chars. The IDF check is still yours.
2. ~~What is the ratio of questions quoting identifiers to paraphrasing?~~ **Answered:** 70/99 code, 9/100 docs. The gap is a **docs** problem. (§1.4)
3. When you have a baseline: are your failures wrong-file or right-file-wrong-region (§1.7)?
4. Does prepending `file_path` and the symbol name to the indexed text help or hurt (§1.5A)?

**Answering**
5. Can retrieval `k` differ from the `k` fed to the generator (§2.1)?
6. How will you measure grounding without a trustworthy LLM judge (§2.3)?

**Evaluation**
7. ~~Does your overlap rule match the moulinette's exactly?~~ **Answered:** yes — formula and conventions recovered and cross-verified (§3.2, `RECALL_NOTES.md` §2). Your job is to port it faithfully.
8. Does your recall average per-question or pool across all sources (§3.3)? **Per-question** — see `RECALL_NOTES.md` §2.3.

**Bonus**
9. Which of #3/#4 first, and does your indexing loop make hashing nearly free (§4)?

**Still open from `CHUNKING_NOTES.md`:**
10. ~~Do the ground-truth ranges reveal a specific segmentation strategy?~~ **Answered, and the answer is no** — 80% of code spans start mid-line. The open question is now: *what boundary rule do you use instead?* (`CHUNKING_NOTES.md` §3 Q4)

---

## 8. What was deliberately not done

No retrieval code, prompt, evaluation function, index format, or API was written. No project files were modified apart from these notes files.

These notes identify problems and the questions that expose them. The design is yours, and subject X.1 means you will be asked to defend it.

### Revision log

| Claim | Status |
|---|---|
| "Corpus measurement — run this first" (§6) | **DONE** — 1937 files, 20,003,424 chars, ~50k chunks |
| "Look at the ground truth and classify identifier vs paraphrase" (§1.4) | **DONE** — 70/99 code, 9/100 docs. The gap is a *docs* problem |
| `llm_sdk` path "will break `uv sync`" | **OVERSTATED** — `uv sync --frozen` verified clean. See `CHUNKING_NOTES.md` §8 |
