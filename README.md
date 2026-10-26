# 42_RAG

sources:
- https://jillanisofttech.medium.com/optimizing-chunking-strategies-for-retrieval-augmented-generation-rag-applications-with-python-c3ab5060d3e4
- https://community.databricks.com/t5/technical-blog/the-ultimate-guide-to-chunking-strategies-for-rag-applications/ba-p/113089
- https://weaviate.io/blog/introduction-to-rag
- https://medium.com/data-science/llm-rag-based-question-answering-6a405c8ad38a
- https://en.wikipedia.org/wiki/Retrieval-augmented_generation
- https://theaidatabaseblog.com/learn/measure-recall-k/
- https://krishnapullak.medium.com/understanding-precision-recall-and-f-score-at-k-in-recommender-systems-7146a0dce68e
- https://www.youtube.com/watch?v=A0K3K4fOvY8
- https://www.youtube.com/watch?v=pvCabUerwss&t=38s
- https://www.youtube.com/watch?v=sVcwVQRHIc8
- https://www.youtube.com/watch?v=T-D1OfcDW1M&t=18s
- https://www.youtube.com/watch?v=_HQ2H_0Ayy0


- https://www.pinecone.io/learn/chunking-strategies/
- https://weaviate.io/blog/chunking-strategies-for-rag
- https://docs.langchain.com/oss/python/langchain/overview

- https://arxiv.org/pdf/2506.15655
- https://docs.python.org/3/library/ast.html
- https://www.twig.so/dev/rag-scenarios-and-solutions/chunking/code-splitting

- https://reference.langchain.com/python/langchain-text-splitters/markdown/MarkdownHeaderTextSplitter



BM25 is the reference



How to import the llm:

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

self.tokenizer = AutoTokenizer.from_pretrained(model_name)
self.model = AutoModelForCausalLM.from_pretrained(
    model_name,
    dtype=torch.float32,   # explicit; v5.17 otherwise uses "auto" (likely bf16)
).eval()

def generate(self, context: str, question: str) -> str:
    messages = [
        {"role": "system", "content": "Answer using only the provided context."},
        {"role": "user", "content": f"Context:\n{context}\n\nQuestion: {question}"},
    ]
    prompt = self.tokenizer.apply_chat_template(
        messages,
        tokenize=False,
        add_generation_prompt=True,
        enable_thinking=False,   # Qwen3: avoid long thinking on CPU
    )
    inputs = self.tokenizer(
        prompt,
        return_tensors="pt",
        truncation=True,
        max_length=8192,         # keep CPU context manageable
    )
    with torch.inference_mode():
        output_ids = self.model.generate(
            **inputs,
            max_new_tokens=128,
            do_sample=False,
            repetition_penalty=1.15,
            eos_token_id=self.tokenizer.eos_token_id,
            pad_token_id=self.tokenizer.eos_token_id,
        )
    generated = output_ids[0][inputs["input_ids"].shape[1]:]
    return self.tokenizer.decode(generated, skip_special_tokens=True).strip()