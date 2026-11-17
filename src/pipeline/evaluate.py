from ..helpers.models import MinimalSource, RagDataset
import json
from pydantic import ValidationError
from ..helpers import ParseError


def iou(a: MinimalSource, b: MinimalSource) -> float:
    inter = max(0, min(a.last_character_index, b.last_character_index)
                - max(a.first_character_index, b.first_character_index))
    len_a = a.last_character_index - a.first_character_index
    len_b = b.last_character_index - b.first_character_index
    union = len_a + len_b - inter

    return inter / union if union > 0 else 0.0


def question_recall(truth: list[MinimalSource],
                    retrieved: list[MinimalSource],
                    k: int) -> float:
    if not truth:
        return 1.0
    found = 0
    for t in truth:
        for r in retrieved[:k]:
            if r.file_path == t.file_path and iou(t, r) > 0.05:
                found += 1
                break

    return found / len(truth)


def load_ground_truth(dataset_path: str) -> RagDataset:
    try:
        with open(dataset_path, encoding="utf-8") as f:
            dataset = json.load(f)

        return RagDataset.model_validate(dataset)
    except OSError:
        raise ParseError(f"File '{dataset_path}' "
                         "could not be loaded.")
    except json.JSONDecodeError:
        raise ParseError(f"File '{dataset_path}' "
                         "could not be processed.")
    except ValidationError:
        raise ParseError(f"File '{dataset_path}' "
                         "is not a valid search results file.")
