.PHONY: install run debug clean fclean lint flake8 mypy lint-strict mypy-strict

SGOINFRE_CACHE = /sgoinfre/$(USER)/uv-cache
SGOINFRE_VENV  = /sgoinfre/$(USER)/venvs/rag
SGOINFRE_HF    = /sgoinfre/$(USER)/huggingface

MYPY_FLAGS = --warn-return-any --warn-unused-ignores \
             --ignore-missing-imports --disallow-untyped-defs \
             --check-untyped-defs

ARGS = index --max_chunk_size 2000

install:
	@if ! command -v uv >/dev/null 2>&1; then \
		echo "Installing uv..."; \
		curl -LsSf https://astral.sh/uv/install.sh | sh; \
	fi
	@if [ -d /sgoinfre ]; then \
		echo "Using /sgoinfre for storage..."; \
		mkdir -p $(SGOINFRE_CACHE) /sgoinfre/$(USER)/venvs $(SGOINFRE_HF); \
		UV_CACHE_DIR=$(SGOINFRE_CACHE) \
		UV_PROJECT_ENVIRONMENT=$(SGOINFRE_VENV) \
		UV_LINK_MODE=copy \
		uv sync; \
		ln -sfn $(SGOINFRE_VENV) .venv; \
	else \
		uv sync; \
	fi


run: install
	@if [ -d /sgoinfre ]; then \
		HF_HOME=$(SGOINFRE_HF) UV_CACHE_DIR=$(SGOINFRE_CACHE) uv run python -m src $(ARGS); \
	else \
		uv run python3 -m src $(ARGS); \
	fi || true
	

debug: install
	@if [ -d /sgoinfre ]; then \
		HF_HOME=$(SGOINFRE_HF) UV_CACHE_DIR=$(SGOINFRE_CACHE) uv run python -m pdb -m src; \
	else \
		uv run python -m pdb -m src; \
	fi

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	rm -rf .mypy_cache

flake8:
	uv run flake8 .

mypy:
	uv run mypy . $(MYPY_FLAGS)

lint: flake8 mypy
	

lint-strict: flake8
	uv run mypy . $(MYPY_FLAGS) --strict