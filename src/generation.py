from .ingesting import read_file
from .models import MinimalSource, StudentSearchResults
from .helpers import SYSTEM_PROMPT, MAX_CONTEXT, MAX_NEW_TOKENS
from pathlib import Path
from transformers import AutoModelForCausalLM, AutoTokenizer
import torch
from typing import Any


def read_sources(sources: list[MinimalSource]) -> list[str]:

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

def load_model(student_search_results_path: str) -> StudentSearchResults:
    with student_search_results_path open as f:
        


class LLM:
    def __init__(self, model_name: str = "Qwen/Qwen3-0.6B"):
        self.tokenizer = AutoTokenizer.from_pretrained(model_name)
        self.model: Any = AutoModelForCausalLM.from_pretrained(
            model_name, dtype=torch.float32)

    def _build_user_input(self, question: str,
                          sources: list[MinimalSource],
                          texts: list[str]) -> str:
        context = "\n\n".join(f"[{i}] {s.file_path}\n{t}"
                              for i, (s, t) in enumerate(zip(sources, texts),
                                                         start=1) if t)

        user_input = f"Context:\n{context}\n\nQuestion: {question}"

        return user_input

    def _build_prompt(self, user_input: str) -> str:
        messages = [{"role": "system", "content": SYSTEM_PROMPT},
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
        budget = MAX_CONTEXT - MAX_NEW_TOKENS

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

        text = self._check_tokens(question, sources, texts)

        inputs = self.tokenizer(text, return_tensors="pt")
        output = self.model.generate(**inputs,
                                     max_new_tokens=MAX_NEW_TOKENS,
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
