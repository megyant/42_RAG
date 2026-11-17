from ..chunking import read_file
from ..helpers.models import MinimalSource, StudentSearchResults
from ..helpers import Const, ParseError
from pathlib import Path
import json
from pydantic import ValidationError
from typing import Any


def read_sources(sources: list[MinimalSource]) -> list[str]:
    """
    Read and extract text snippets from sources, caching file contents to
    minimize I/O.

    Args:
        sources (list[MinimalSource]): A list of source objects containing
        file paths and character indices.

    Returns:
        list[str]: A list of extracted text strings corresponding to each
        source.
    """

    texts: list[str] = []
    file_texts: dict[Path, str | None] = {}

    for source in sources:
        file_path = Path(source.file_path)

        if file_path not in file_texts:
            file_texts[file_path] = read_file(file_path)

        text = file_texts[file_path]

        if text is None:
            texts.append("")
        else:
            texts.append(
                text[source.first_character_index:source.last_character_index])

    return texts


def load_student_search_results(
        student_search_results_path: str) -> StudentSearchResults:
    """
    Load and validate student search results from a JSON file.

    Args:
        student_search_results_path (str): The path to the JSON search
        results file.

    Returns:
        StudentSearchResults: The validated student search results model.

    Raises:
        ParseError: If the file cannot be loaded, contains invalid JSON, or
        fails validation.
    """
    try:
        with open(student_search_results_path,
                  encoding="utf-8", newline="")as f:
            searches = json.load(f)

        search_results = StudentSearchResults.model_validate(searches)

        return search_results
    except OSError:
        raise ParseError(f"File '{student_search_results_path}' "
                         "could not be loaded.")

    except json.JSONDecodeError:
        raise ParseError(f"File '{student_search_results_path}' "
                         "could not be processed.")
    except ValidationError:
        raise ParseError(f"File '{student_search_results_path}' "
                         "is not a valid search results file.")


class LLM:
    """
    A wrapper class for interacting with a Hugging Face
    Causal Language Model."""
    def __init__(self, model_name: str = "Qwen/Qwen3-0.6B"):
        """
        Initialize the LLM with a specified model, tokenizer,
        and system prompt.

        Args:
            model_name (str): The identifier of the pretrained model to
            load. Defaults to "Qwen/Qwen3-0.6B".
        """
        from transformers import AutoModelForCausalLM, AutoTokenizer
        import torch
        self.tokenizer = AutoTokenizer.from_pretrained(model_name)
        self.model: Any = AutoModelForCausalLM.from_pretrained(
            model_name, dtype=torch.float32)
        self.SYSTEM_PROMPT: str = ("You answer questions about the vLLM "
                                   "codebase. Use only the context below. "
                                   "If the context does not contain the "
                                   " answer, say you don't know. Be brief "
                                   "and name the source file you used")

    def _build_user_input(self, question: str,
                          sources: list[MinimalSource],
                          texts: list[str]) -> str:
        """
        Construct the formatted user input string including context and
        question.

        Args:
            question (str): The question to be answered by the model.
            sources (list[MinimalSource]): The list of sources providing
            context.
            texts (list[str]): The corresponding text content for each source.

        Returns:
            str: The formatted user input string.
        """
        context = "\n\n".join(f"[{i}] {s.file_path}\n{t}"
                              for i, (s, t) in enumerate(zip(sources, texts),
                                                         start=1) if t)

        user_input = f"Context:\n{context}\n\nQuestion: {question}"

        return user_input

    def _build_prompt(self, user_input: str) -> str:
        """
        Apply the chat template to build the final prompt string for
        the model.

        Args:
            user_input (str): The formatted user input string.

        Returns:
            str: The complete prompt string ready for tokenization.

        Raises:
            TypeError: If the generated prompt is not a string.
        """
        messages = [{"role": "system", "content": self.SYSTEM_PROMPT},
                    {"role": "user", "content": user_input}]

        text = self.tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True,
            enable_thinking=False,
        )

        if not isinstance(text, str):
            raise TypeError("expected a string prompt")

        return text

    def _check_tokens(self, question: str, sources: list[MinimalSource],
                      texts: list[str]) -> str:
        """
        Ensure the prompt token count fits within the token budget
        by pruning sources if necessary.

        Args:
            question (str): The question to be answered.
            sources (list[MinimalSource]): The list of sources.
            texts (list[str]): The corresponding text content for each
            source.

        Returns:
            str: The final prompt string that fits within the token budget.
        """
        budget = Const.MAX_CONTEXT - Const.MAX_NEW_TOKENS

        while True:
            prompt = self._build_prompt(
                self._build_user_input(question, sources, texts))

            n_tokens = len(self.tokenizer(prompt)["input_ids"])

            if n_tokens <= budget or len(sources) <= 1:
                return prompt

            sources = sources[:-1]
            texts = texts[:-1]

    def generate_response(self, question: str,
                          sources: list[MinimalSource],
                          texts: list[str]) -> str:
        """
        Generate a response from the LLM given a question and supporting
        sources.

        Args:
            question (str): The question to answer.
            sources (list[MinimalSource]): The supporting sources.
            texts (list[str]): The text content corresponding to each source.

        Returns:
            str: The generated response text.

        Raises:
            TypeError: If the decoded response is not a string.
        """

        text = self._check_tokens(question, sources, texts)

        inputs = self.tokenizer(text, return_tensors="pt")
        output = self.model.generate(**inputs,
                                     max_new_tokens=Const.MAX_NEW_TOKENS,
                                     do_sample=True,
                                     temperature=0.7,
                                     top_p=0.8,
                                     top_k=20,
                                     min_p=0.0)

        response_ids = output[0][len(inputs.input_ids[0]):].tolist()

        response = self.tokenizer.decode(response_ids,
                                         skip_special_tokens=True)

        if not isinstance(response, str):
            raise TypeError("expected a string response")

        return response
