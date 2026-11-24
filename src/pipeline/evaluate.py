from ..helpers.models import MinimalSource, RagDataset, AnsweredQuestion
import json
from pydantic import ValidationError
from ..helpers import ParseError


def iou(a: MinimalSource, b: MinimalSource) -> float:
    """
    Calculate the Intersection over Union (IoU) between two source
    character ranges.

    Args:
        a (MinimalSource): The first source range.
        b (MinimalSource): The second source range.

    Returns:
        float: The IoU ratio between 0.0 and 1.0.
    """
    inter = max(0, min(a.last_character_index, b.last_character_index)
                - max(a.first_character_index, b.first_character_index))
    len_a = a.last_character_index - a.first_character_index
    len_b = b.last_character_index - b.first_character_index
    union = len_a + len_b - inter

    return inter / union if union > 0 else 0.0


def question_recall(truth: list[MinimalSource],
                    retrieved: list[MinimalSource],
                    k: int) -> float:
    """
    Calculate the recall metric for a question based on retrieved
    sources matching ground truth.

    Args:
        truth (list[MinimalSource]): The ground truth sources.
        retrieved (list[MinimalSource]): The retrieved sources.
        k (int): The number of top retrieved sources to consider.

    Returns:
        float: The fraction of ground truth sources successfully recalled.
    """
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
    """
    Load and validate the reference ground truth dataset from a JSON file.

    Args:
        dataset_path (str): The path to the ground truth dataset JSON file.

    Returns:
        RagDataset: The validated ground truth dataset.

    Raises:
        ParseError: If the file cannot be read, contains invalid JSON, or
        fails validation, or has no ground-truth sources.
    """
    try:
        with open(dataset_path, encoding="utf-8") as f:
            dataset = json.load(f)

        ground_truth = RagDataset.model_validate(dataset)
    except OSError:
        raise ParseError(f"File '{dataset_path}' "
                         "could not be loaded.")
    except json.JSONDecodeError:
        raise ParseError(f"File '{dataset_path}' "
                         "could not be processed.")
    except ValidationError:
        raise ParseError(f"File '{dataset_path}' "
                         "is not a valid RAG dataset.")

    if not any(isinstance(q, AnsweredQuestion) and q.sources
               for q in ground_truth.rag_questions):
        raise ParseError(f"File '{dataset_path}' has no ground-truth "
                         "sources. Use a file from AnsweredQuestions/")

    return ground_truth
