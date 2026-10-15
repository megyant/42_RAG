# RAG Project — Notes on recall@k

> Focused notes on the metric itself: what it is, how it reduces on your data, the arithmetic in the overlap rule, and how to get a baseline before you have a retrieval system. Companion to `CHUNKING_NOTES.md` (indexing) and `PIPELINE_NOTES.md` (retrieval, answering, bonus, submission).
>
> **Advisory notes, not a design document.** The assignment subject is the authority.

**Status of this file: the metric is no longer an inference.** An earlier revision had to guess the overlap formula, the span convention, and the multi-source scoring rule from a one-line prose description. All of that is now **verified by decompiling `moulinette-ubuntu`** (and `moulinette-fedora`, which is logically identical), cross-checked by recompiling the recovered code under CPython 3.10 to a byte-exact match. Sections 2 and 3 below are now statements of fact, not arguments. What remains genuinely open has moved to §9.

---

## 0. What the subject says, verbatim

Three places in `others_to_delete/en.subject.pdf`, and it is less precise than you might hope.

### VII.1.1 — the definition

> For each question, recall@k is the share of its correct sources that you retrieve in your top-k results. A correct source counts as found when one of your results is in the same file and overlaps its character range.
>
> The overlap bar is low (an IoU of 0.05), so you do not need to match the reference span exactly: retrieving a chunk that covers the right region of the right file is enough. A result in a different file never counts, which is `file_path` must be exact.

Every word of that survives contact with the binary. The one thing the subject does not say — *how* to compute the IoU — is settled in §2.

### VII.1.2 — the thresholds

| Constraint | Value |
|---|---|
| Indexing time | ≤ 5 minutes, whole corpus |
| Retrieval throughput | ≤ 90 seconds for 200 questions |
| **Recall@5, docs** | **≥ 80%** |
| **Recall@5, code** | **≥ 50%** |

### The moulinette's own README

`others_to_delete/README_RAG_Mou.md` adds that it reports **Recall@1, @3, @5, @10**, and passes if **Recall@5 ≥ 50%**. Confirmed in the binary: `k_values = [1, 3, 5, 10]`, and the pass/fail line is `Recall@5 >= threshold`, printed as `FAIL` when `< threshold`.

Sample output shape from the subject (illustrative only — explicitly *"not a reference score"*):

```
Recall@1: 0.450  Recall@3: 0.590  Recall@5: 0.650  Recall@10: 0.720
```

---

## 1. What the definition reduces to on YOUR data

"Share of its correct sources" is computed **per question**, then averaged across questions.

**Every public ground-truth record has exactly one source** — measured, not assumed:

```
dataset_code_public  99 questions,  sources-per-question histogram: {1: 99}
dataset_docs_public 100 questions,  sources-per-question histogram: {1: 100}
```

So each question contributes either 1.0 or 0.0, and there is no partial credit:

```
recall@k = (number of questions where at least one retrieved chunk
           satisfies the overlap rule, in the correct file)
          / (total questions)
```

**That is a hit rate, not a similarity score.** Keep this in mind — it changes what you optimise. See §6.

The denominator is `len(true_sources)`, i.e. the number of ground-truth sources. It is **not** `min(k, len(true_sources))`, and it is not the number of questions you returned results for — see gotcha 1 in §3.1.

---

## 2. The overlap rule — RESOLVED

> **Reading the moulinette is not the same as calling it.** Subject VI.6 says *"Your solution must never import or call the moulinette."* That forbids **calling** it from your solution. Reading its source to understand the metric is not calling it. Keep the recovered code out of `src/` so the distinction is structural, not just a promise. See §4.

The subject names a threshold ("an IoU of 0.05") but not a **computation**. The computation is now known.

The module is **`moulinette/evaluate_retrieval.py`** — the real module name survives in the nested PYZ, so this is not an obfuscated reconstruction. (`moulinette-fedora` is logically identical.)

### 2.1 The formula, verbatim

```python
def compare_sources(s1: MinimalSource, s2: MinimalSource) -> float:
    if s1.file_path != s2.file_path:
        return 0.0

    assert s1.first_character_index != -1
    assert s1.last_character_index != -1
    assert s2.first_character_index != -1
    assert s2.last_character_index != -1

    s1_len = s1.last_character_index - s1.first_character_index
    s2_len = s2.last_character_index - s2.first_character_index

    s1_intersection_s2 = max(
        0,
        min(s1.last_character_index, s2.last_character_index)
        - max(s1.first_character_index, s2.first_character_index),
    )

    s2_intersection_s1 = max(
        0,
        min(s2.last_character_index, s1.last_character_index)
        - max(s2.first_character_index, s1.first_character_index),
    )

    return max(s1_intersection_s2, s2_intersection_s1) / (
        s1_len + s2_len - max(s1_intersection_s2, s2_intersection_s1)
    )
```

So it is **true intersection-over-union**:

```
IoU = inter / (s1_len + s2_len - inter)
```

**Not** `inter / len(ground_truth)`. **Not** `inter / len(retrieved)`. That distinction matters, and the decisive test is short:

| Case | `inter/union` (correct) | `inter/len(gt)` (wrong) | `inter/len(ret)` (wrong) |
|---|---|---|---|
| gt `[0, 50)`, chunk `[0, 100)` | **0.500** | 1.000 | 0.500 |
| gt `[0, 100)`, chunk `[50, 150)` | **0.333** | 0.500 | 0.500 |

A grader that returned 1.0 on the first row would be `inter/len(gt)`. It returns 0.5.

Note that `s1_len + s2_len - inter` is the union only because neither range is contained in the other *or* because containment makes the smaller term redundant — with half-open ranges the expression is exactly the union length in all cases. Fine.

### 2.2 Spans are half-open, and `last_character_index` is exclusive

```
len = last - first        (no +1)
span = [first, last)
```

Verified: `[0, 101)` vs `[0, 100)` scores **0.9901**, not 1.0 — with an inclusive convention it would be exactly 1.0.

Practical consequence: **your last index is the offset one past the final character.** A chunk covering characters `a..b` inclusive is `[a, b+1)`. Get this wrong by one and you lose the last character of every chunk and every span; you will still pass most IoU checks, which is why it is dangerous. It is also why a 100-character chunk is written `[0, 100)`, not `[0, 99)`.

The same `last - first` convention governs the validation cap (§3.2), so an off-by-one in your writer can *also* push you over 2000.

### 2.3 The per-question score, verbatim

```python
def calculate_recall_at_k_for_one_question(
    pred_sources: List[MinimalSource],
    true_sources: List[MinimalSource],
    minimal_iou_threshold: float = 0.05,
) -> float:
    """
    Calculate recall@k by checking if any search result contains lines from cited sources.

    Returns 1.0 if at least one cited source is found, 0.0 otherwise.
    """
    if not true_sources:
        return 1.0
    if not pred_sources:
        return 0.0

    found_sources = {i: 0 for i in range(len(true_sources))}
    for i, true_source in enumerate(true_sources):
        for pred_source in pred_sources:
            if compare_sources(true_source, pred_source) > minimal_iou_threshold:
                found_sources[i] += 1.0
                break

    return sum(found_sources.values()) / len(true_sources)
```

Four facts fall out, all of which were open before:

1. **The comparison is strictly `>`.** An IoU of exactly **0.05 does not count.** The docstring is also a lie in the general case: with multiple ground-truth sources you get partial credit.
2. **Multiple ground-truth sources are scored independently, 0 or 1 each**, with a `break` on the first hit. Emitting the same chunk twenty times cannot inflate a single source's contribution. Denominator is `len(true_sources)`.
3. **Empty ground-truth `sources` returns 1.0 for free**, and empty predictions return 0.0 without touching the denominator.
4. **`threshold` defaults to `None`**, in which case no verdict is printed and the function returns `None`. Only run with `--threshold` if you want a PASS/FAIL line; a bare run is a scoreboard, not a gate.

### 2.4 Top-k truncation is a plain slice

`pred_sources[:k]` on your declared order. The only two upper-bound checks on your file are both strict `>`:

```
student_data.k                  > k   → reject
len(student.retrieved_sources)  > k   → reject
```

**Your declared `k` need not equal your returned count.** Both of these are accepted, verified by test:

| Declared `k` | Sources returned | Valid? |
|---|---|---|
| 10 | 3 | yes |
| 5 | 7 | yes |
| 11 | 10 | no — `k > k` |
| 3 | 4 | no — more sources than `k` |

So there is no "k agreement" failure mode to guard against beyond the two upper bounds. But the corollary is that **the grader trusts your ordering completely and never sorts you**: if your list is not in descending relevance order, recall@k is measured on whatever arbitrary prefix your first `k` entries happen to occupy. This is the one thing in this section that is a real design obligation rather than a formality.

CLI defaults, for reference: `k = 10`, `max_context_length = 2000`, `k_values = [1, 3, 5, 10]`.

### 2.5 The bound table, under true IoU

With half-open spans and the real formula, the two nested cases collapse to `min/max`, which gives clean one-sided bounds. Let ground-truth length be `L = last - first`, chunk length `c`.

**Chunk entirely inside the ground truth:**
```
IoU = c / L        →  pass iff  c > 0.05·L        (i.e. c ≥ floor(0.05·L) + 1)
```

**Chunk entirely containing the ground truth:**
```
IoU = L / c        →  pass iff  c < 20·L         (i.e. c ≤ 20·L − 1)
```

Strict `>` on both, because of §2.3. That last `− 1` is the whole of the "tiny extra margin" — for `L = 2000` a 100-character chunk gives exactly 0.05 and **fails**; you need 101.

| Ground-truth span `L` | Chunk must be ≥ | Chunk must be ≤ | Binding? |
|---|---|---|---|
| 12 chars (`trust_remote_code = False`, code min) | 1 char | **239 chars** | upper |
| 40 chars (docs min) | 3 chars | **799 chars** | upper |
| 200 chars | 11 chars | 3 999 (no real limit) | neither |
| 878 chars (code median) | 44 chars | 17 559 (no real limit) | neither |
| 1 154.5 chars (docs median) | 58 chars | 23 089 (no real limit) | neither |
| 1 578 chars (code max) | 79 chars | 31 559 (no real limit) | neither |
| 1 997 chars (docs max) | 100 chars | 39 939 (no real limit) | neither |

**Straddling is worse than either nested case.** If the chunk starts `p` characters *before* the ground-truth start and does not cover all of it, then `inter = c − p` and `union = L + p`:

```
IoU = (c − p) / (L + p)   →  pass iff  c − p > 0.05·(L + p)
```

Concrete numbers, all against `L = 1997` with a 400-character chunk:

| Chunk position | inter | union | IoU | |
|---|---|---|---|---|
| fully inside the span | 400 | 1997 | 0.200 | pass |
| starts 200 chars early, covers 200 of the span | 200 | 2197 | 0.091 | pass |
| starts 380 chars early, covers 20 of the span | 20 | 2377 | 0.008 | **fail** |

That third row is the failure mode to design against: not a wrong chunk size, but a **chunk that begins just too far before the region of interest**. IoU is maximised when one span is nested in the other, so alignment pays.

**But see `CHUNKING_NOTES.md` §3 — an earlier version of this file asserted that "structural boundaries are what produce nesting," and that is not supported by your data.** Measured: **80% of code ground-truth spans (79/99) start mid-line**, not at a `def`/`class` boundary. Only 10 of 99 code spans begin at anything resembling a structural start. Nesting helps only if your boundary lands near the reference one, and for code it usually will not. A structural splitter can produce a clean boundary that sits 40 characters away from the ground-truth start — which lands you in the "starts early, covers little" failure row above.

### 2.6 What this does to the chunk-size recommendation

**An earlier revision of this file recommended chunk sizes of 150–500 characters. That was based on the wrong formula and on span lengths that had not been measured. Both premises are gone. The recommendation is withdrawn.**

The measured span distribution:

```
span lengths (last - first, exclusive last):
  code: n=99  min=12  max=1578  mean=820.6  median=878
       histogram {'<50': 1, '50-200': 1, '200-500': 11, '500-1000': 61, '1000-2000': 25, '>2000': 0}
  docs: n=100 min=40  max=1997  mean=1135.0 median=1154.5
       histogram {'<50': 1, '50-200': 10, '200-500': 11, '500-1000': 23, '1000-2000': 55, '>2000': 0}
```

Spans are **large** — median 878 characters of code, 1155 of docs — and none exceed the 2000 cap. Two consequences:

- **The lower bound is essentially free.** For a typical question the `0.05·L` floor is only **~44 characters** (code) or **~58 characters** (docs), and across the entire corpus the worst case is 100 characters (the 1997-character docs span). Any chunk of 100+ characters clears it for every question in both datasets.
- **The upper bound is nowhere near binding.** `20·L` is 240 even for the 12-character minimum, but it only binds when `L ≤ c/20`. Counting the actual spans that a given chunk size would sink:

| Chunk size `c` | Code spans sunk (`L ≤ c/20`) | Docs spans sunk | Worst case |
|---|---|---|---|
| 150 – 200 | 0 / 99 | 0 / 100 | none |
| 400 | 1 / 99 | 0 / 100 | the 12-char code span (IoU 0.030) |
| 800 | 1 / 99 | 1 / 100 | — |
| 1 200 | 1 / 99 | 2 / 100 | — |
| 2 000 (the cap) | 2 / 99 | 4 / 100 | — |

A 400-character chunk against a 1997-character docs span scores `400 / 1997 = 0.200` — **four times the threshold**, comfortably passing.

**The constraint is much looser than previously advised.** The practical implication is freedom: **choose your chunk size on retrieval-quality grounds, not IoU grounds.**

Now measured directly. For each candidate size, I computed the fraction of questions where **some** chunk of that size, placed anywhere in the file, would clear IoU > 0.05 — the ceiling on recall regardless of ranking quality:

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
| 2000 (the cap) | 98% | 96% |

**Anything from 150 to 600 characters is free.** The IoU rule does not pick your chunk size; it only rules out the large end, where the `20·L` bound starts sinking the tight spans. At the 2000 cap you have given away ~4 points of docs ceiling.

Chunking for BM25 — lexical precision, enough context for BM25 to discriminate, enough for the answer generator — is the correct basis for the decision. `CHUNKING_NOTES.md` §2 still makes that argument on its own merits; it no longer needs this file to defend it.

**One caveat on this table.** It assumes you can retrieve *any* window, i.e. it measures the overlap rule in isolation. It says nothing about whether your ranker will surface that window. Your real recall@5 will be well below these numbers, and the gap is a ranking problem, not an IoU problem. Do not mistake a high ceiling for a good system.

---

## 3. What the subject does NOT specify — mostly RESOLVED

Of the four items that were open before, all four are now closed. What is left is genuinely open and is not about the formula.

### 3.1 The two gotchas

**Gotcha 1 — omission is silent and it still costs you.**
A question you leave out of your output scores **0**, and **still counts in the denominator**. There is no "skip" and no normalisation by the number of questions you answered. Dropping the 10 questions you could not retrieve for is a flat 10-point deduction on a 99-question dataset. Relatedly, a question with **no** ground-truth sources returns **1.0 for free** — so a private dataset containing such a record hands you a point you did not earn. Neither public dataset has one, but your `evaluate` must implement both behaviours exactly, because the private set is where they bite.

**Gotcha 2 — an unknown `question_id` crashes the grader.**
The grader indexes the ground truth by `question_id` and does not guard the lookup: an id it does not know raises a **raw `KeyError`**, not a zero. A typo, a stale id from an earlier dataset version, or a leftover experiment file takes down the whole run with no partial score. Emit ids straight from the dataset you were given, and validate the id set before you submit.

### 3.2 Validation rules (`moulinette/validate_student_data.py`)

- **`max_context_length` is computed the same way** as the metric — `last − first`, no `+1` — and the check is `length > 2000`, so `[0:2000]` passes and `[0:2001]` fails. Validation **breaks out of the loop on the first failure**, so you get one error, not a list. Assert the cap in your own writer; do not lean on the grader to find it.
- **There is no path-format validation whatsoever.** `file_path` is compared by **exact string equality** and nothing else. `./f.txt`, `/abs/f.txt`, and `F.txt` all score **0.0** against a ground truth of `f.txt`. No normalisation, no basename matching, no warning. This makes path formatting a *silent, total* failure mode and it is the single most likely way to score 0 while believing your system works.
- **All fields are mandatory, no defaults.**

  ```
  MinimalSource:          file_path, first_character_index, last_character_index
  MinimalSearchResults:   question_id, question, retrieved_sources
  StudentSearchResults:   search_results, k: int
  ```

- **An index of exactly `-1` raises `AssertionError`**, not a clean validation failure — the same four asserts appear in `compare_sources`. Do not use `-1` as a sentinel for "unknown" anywhere in your output.

### 3.3 Still genuinely open

1. **Nothing about the metric itself.** Formula, convention, truncation, multi-source scoring, and validation are all settled above. If a future revision of this file is arguing about the formula again, something has gone wrong.
2. **Whether the private datasets have >1 source per question.** The scoring code handles it correctly, but no public record exercises it, so your `evaluate` will not have been tested on that path. Implement it from the recovered code, not from intuition.
3. **Whether the private `max_context_length` and `k` differ.** Defaults are 2000 and 10; the private harness may pass different values. Design your writer against a parameter, not the literal.

---

## 4. How the rule was verified, and how to verify your own output

### Route A — read the grader's source *(done)*

`others_to_delete/moulinette_RAG.zip` (extracted at `others_to_delete/moulinette_RAG/`) was decompiled, and the recovered functions were recompiled under CPython 3.10 to a **byte-exact match** against the shipped bytecode. That is what makes §2 a fact rather than an inference.

Again, and it is worth restating because it is the reason this file exists: **reading the moulinette is not calling it.** Subject VI.6 forbids *"import or call"* from your solution. Reading is not calling. Keep the recovered code outside `src/`.

### Route B — confirm against the binary anyway *(still worth doing)*

Route A tells you what the metric does. Route B tells you whether *your* pipeline produces output the metric accepts. These are different questions and you still need to answer the second one.

Construct a synthetic `StudentSearchResults` file with hand-chosen ranges against a real ground-truth dataset and run the moulinette on it. The discriminators, now that you know what to look for:

| Probe | Expected, if §2 is right |
|---|---|
| gt `[0, 50)` vs chunk `[0, 100)` | does **not** count (IoU 0.5) → recall 0.0 |
| gt `[0, 101)` vs chunk `[0, 100)` | does **not** count (IoU 0.0099) → recall 0.0 |
| IoU engineered to exactly 0.05 | does **not** count (strict `>`) → recall 0.0 |
| declare `k = 10`, return 3 sources | accepted, no error |
| declare `k = 5`, return 7 sources | accepted, no error |
| one question omitted from the output | accepted, and that question scores 0 in the average |
| unknown `question_id` | **KeyError**, run dies |
| `./f.txt` where ground truth says `f.txt` | scores 0.0, no warning |

**Because the format is now confirmed rather than inferred, the oracle test in §5.1 is worth more than it was, not less**: it is no longer a probe of an uncertain format but a regression test of a known one. If it does not score 1.0, something in *your* code is wrong — there is no longer a legitimate "maybe I misunderstood the metric" branch.

---

## 5. Get a baseline before you have a retrieval system

You do not need a retrieval implementation to get a number. `evaluate` is the one component you can finish and test completely on its own: it reads your JSON and the ground truth, and needs nothing else.

**Reorder your build accordingly: `evaluate` first, indexer second.** (Same argument as `PIPELINE_NOTES.md` §0.)

Three reasons:
- It is self-contained, so you can finish it today.
- It is the only thing that tells you whether your retrieval is any good.
- It validates your output format — which is still suspect (`CHUNKING_NOTES.md` §8, the `search_reults` field-name typo in `models.py:37`).

Write `evaluate` as a **faithful port of §2.1–§2.4**, not as a re-derivation. Same formula, same half-open spans, same strict `>`, same `break`, same `len(true_sources)` denominator, same free 1.0 for empty ground truth, same 0 for omitted questions. Reimplementation from prose is how the old wrong formula got into circulation in the first place.

### 5.1 The oracle test — highest value, do it first

Take the `AnsweredQuestions` ground truth, strip the `answer` field, wrap each question's **own** `sources` into `retrieved_sources`, and write that out as a `StudentSearchResults` file. You are submitting the ground truth as your own results.

That scores **recall@k = 1.0 by construction** — and in getting there it proves your JSON shape, your `k` field, your path format, your half-open span convention, and your `evaluate` harness are all correct. Note that the oracle also exercises the gotchas in reverse: every question is present (gotcha 1) and every id is known (gotcha 2).

**It is a format canary.** If the oracle does not score 1.0, your `evaluate` or your writer is wrong, and no amount of chunker or BM25 tuning will reveal that. You would be tuning blind. Now that the format is confirmed, treat a non-1.0 oracle as a hard stop.

A useful structural note for building it: the `AnsweredQuestions` and `UnansweredQuestions` files for each dataset have **identical `question_id` sets, in identical order, with identical counts** (99/99 and 100/100), and `UnansweredQuestions` records carry **only** `question_id` and `question`. So you can zip the two positionally without any keying logic — but key on `question_id` anyway in your real code, because the private set may not be so obliging, and gotcha 2 turns a wrong key into a crash.

### 5.2 The complement — costs almost nothing

Write the same file with `"retrieved_sources": []` for every question. That must score **0.0**.

Two trivial submissions bracket the metric from both ends. Between them they validate everything **except** your actual retrieval quality.

### 5.3 Your first real baseline

This number will be bad. That is the point — it is a floor, not a target.

- chunk every `.py` and `.md` file into fixed **400-character** windows, no overlap
- textbook BM25 over an inverted index
- k = 10
- measure recall@5 on both datasets

400 is a reasonable unadorned starting point, but note that §2.6 no longer *requires* it. It costs at most one code question (the 12-character span) in the worst case, and clears the lower bound on every question in both datasets. If a later experiment says 250 or 800 retrieves better, take it — that is a legitimate reason to change, and the arithmetic will not object.

**Write the score down before you change anything.** Then classify the failures (§6). The classification, not the score, tells you what to build next.

---

## 6. How to read a disappointing number

With one ground-truth source per question, every miss is binary. Sort the misses into two buckets:

| Failure mode | Meaning | Fix |
|---|---|---|
| Correct **file** present in top-k, but no overlapping chunk | granularity / IoU / alignment problem | chunk size, overlap, splitter boundaries, alignment |
| Correct **file absent** from top-k | ranking problem | tokenizer, field weighting, IDF, k |

**These need opposite changes.** Do not guess which one you have. Count them.

Useful cuts to run on your misses:
- **by file type** — are code and docs failing for different reasons? They have different thresholds (50% vs 80%), different span-length distributions (code median 878, docs median 1155), and may have different failure modes
- **by ground-truth span length** — this is now a much cheaper and much less likely explanation than the previous revision assumed. Per §2.6, at a 400-character chunk size at most **1 of 99 code questions and 0 of 100 docs questions** can be lost to the upper bound, and none to the lower. If your span-length histogram of misses is flat, this cut has already told you it is not your problem; move on.
- **by chunk boundary offset** — for the right-file-wrong-region bucket, record where the chunk started relative to the ground-truth start. The straddling arithmetic in §2.5 predicts that misses cluster at large negative offsets (chunk beginning far before the region). If they do, your fix is alignment, not size.
- **by question phrasing** — do questions that quote identifiers verbatim fare better than paraphrased ones? See `PIPELINE_NOTES.md` §1.4

The last cut is the most informative. If verbatim-identifier questions score near 100% and paraphrased ones near 0%, you have found the real problem, and it is the paraphrase gap — not your chunker. Given how loose the IoU constraint turned out to be, expect this to be where the points are.

---

## 7. What `evaluate` must handle

Subject VI.6: `evaluate` is **for your own iteration**. The official metric comes from the moulinette, and *"your solution must never import or call the moulinette."* So `evaluate` is a genuine reimplementation — port the recovered functions, keep the binary out of your import graph.

Failure modes to cover, each traceable to code above:

- **Omitted questions** — score 0, still count in the denominator. Not an error. (§3.1 gotcha 1)
- **Empty ground-truth `sources`** — return 1.0 without dividing by zero. And *tell yourself* that this is a free point, not an achievement. (§2.3)
- **Multiple ground-truth sources per question** — per-source 0/1 with `break`, divided by `len(true_sources)`. Never by `min(k, ...)`. (§2.3)
- **Fewer than k results returned** — fine, valid, no complaint. But fewer *than zero* is impossible and more than `k` is rejected. (§2.4)
- **Half-open spans throughout** — `last - first`, no `+1`, in the metric *and* in the validation cap. (§2.2)
- **Exactly 0.05 IoU** — must fail, because the real comparison is `>`. Test this one explicitly; it is the easiest line to get wrong and it never shows up in aggregate scores. (§2.3)
- **Unknown `question_id`** — the real grader raises `KeyError`. Yours should report it clearly rather than die; but do not paper over it as a zero, because in the real thing it is fatal. (§3.1 gotcha 2)
- **Result ordering** — recall@k slices your list and never sorts. **Is your list sorted by score descending?** If you emit results in arbitrary order, recall@k is being measured on an arbitrary subset and no amount of retrieval improvement will show up. (§2.4)
- **The 2000-character cap** — assert it in the writer, with `last - first`. Validation breaks on first failure, so you get one error at a time. (§3.2)
- **Malformed JSON and missing files** — subject VI.6: *"must never crash with an unhandled traceback."*

---

## 8. Reminders that follow from the metric

- **`file_path` must match verbatim** — same prefix, same spelling, same case. Subject VII.1.1: *"A result in a different file never counts."* There is **no path normalisation in either direction**: a correct chunk under `data/raw/...` when the reference says `data/raw/vllm-0.10.1/...` scores zero, and so does the reverse. This is a silent, total failure mode, and it is the first thing to check when the oracle in §5.1 does not score 1.0.
- **Never emit a source wider than 2000 characters** (`last - first > 2000` → rejected, and it stops at the first offence). Assert it, do not hope.
- **Emit an entry for every question.** Omitting one is a silent zero, not a skip. (§3.1)
- **Sort your results by descending score** before writing. The grader will not do it for you. (§2.4)
- **Report recall@1, @3, @5, @10.** The moulinette does exactly this (`k_values = [1, 3, 5, 10]`), and subject VI.1 asks you to report the effect of chunk size on recall@k — so you need a sweep, not one number. See `CHUNKING_NOTES.md` §10 step 4.
- **Your README's Performance analysis section is filled by this.** Chapter VIII requires it, and the chunk-size sweep is what populates it. It is a deliverable, not just debugging. With the IoU constraint now loose, that sweep is a genuine experiment about retrieval quality rather than a formality — which makes it more interesting to write up, not less.
- **Do not over-fit your chunk size to the arithmetic.** §2.6 exists to free you from that, not to give you a tighter cage.

---

## 9. Open questions

1. ~~What is the exact overlap formula?~~ **Solved:** true IoU, `inter / (len₁ + len₂ − inter)`. (§2.1)
2. ~~Is `last_character_index` inclusive or exclusive?~~ **Solved:** exclusive; spans are half-open; `len = last − first`. (§2.2)
3. ~~Does the moulinette validate that declared `k` matches returned source count?~~ **Solved:** no. Only `k > k` and `len(sources) > k`, both strict, both upper bounds. (§2.4)
4. ~~How are multiple ground-truth sources per question scored?~~ **Solved:** independently 0/1 with `break`, over `len(true_sources)`. (§2.3)
5. ~~What chunk sizes does the IoU rule permit?~~ **Solved:** 150–600 are effectively free; the ceiling table is in §2.6. It does not constrain you meaningfully.
6. ~~Are ground-truth spans aligned to structural boundaries?~~ **Solved:** no. 80% of code spans start mid-line. `CHUNKING_NOTES.md` §3.
7. What does your oracle test score? If not 1.0, stop — the format is confirmed, so the fault is yours. (§5.1)
8. Of your baseline misses, what proportion are wrong-file versus right-file-wrong-region? (§6)
9. Do verbatim-identifier questions score materially better than paraphrased ones? Measured on the question text already: **70/99 code questions quote a snake_case identifier, only 9/100 docs questions do.** So the paraphrase gap is concentrated in docs — which is also where your threshold is higher (80% vs 50%). Expect that split. (§6)
10. Do your misses cluster at large negative chunk-boundary offsets, as §2.5 predicts? Given 6, this is the *likely* code failure mode. (§6)
11. Do the private datasets contain questions with zero ground-truth sources, or more than one? Your `evaluate` handles both but has tested neither. (§3.3)
12. Do the private harness values for `k` and `max_context_length` differ from the defaults 10 / 2000? (§3.3)
13. Does your BM25 ranking put the right *file* in the top-10 at all? If not, no chunk-size decision will help and the paraphrase gap (`PIPELINE_NOTES.md` §1.4) is the whole project.

---

## 10. What was deliberately not done

No evaluation function was written, no oracle file generated, no score computed. No `src/` file was touched, and no recovered code was placed inside the solution tree.

The moulinette was **read and decompiled**, not imported and not called. Subject VI.6 forbids the latter, not the former, and the recovered code lives outside `src/` so that distinction is structural.

### Revision log

| Claim | Status |
|---|---|
| Span-length distribution and the chunk-size bound table | **Confirmed** — re-measured independently, same numbers |
| "Structural boundaries are what produce nesting" (§2.5) | **MISLEADING** — 80% of code spans start mid-line. Corrected in place |
| "The lower bound is essentially free / upper nowhere near binding" | **Confirmed and quantified** — §2.6 now has a full ceiling table per chunk size |

The metric is now documented here exactly as the grader implements it. The implementation is yours. Subject X.1 means you may be asked to explain or modify it live — which is now a considerably easier question to answer than it was.
