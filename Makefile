PYTHON ?= .venv/bin/python
PIP ?= .venv/bin/pip
UVICORN ?= .venv/bin/uvicorn
PYTEST ?= .venv/bin/pytest
BANK_UI := banks-ui

.PHONY: setup venv install-py install-ui dev dev-api dev-ui test lint clean

setup: venv install-py install-ui
	@echo ""
	@echo "Ready. Run: make dev"
	@echo "  UI:  http://127.0.0.1:5173"
	@echo "  API: http://127.0.0.1:8000/docs"

venv:
	python3 -m venv .venv

install-py:
	$(PIP) install -U pip
	$(PIP) install -e ".[dev]"

install-ui:
	cd $(BANK_UI) && npm install

dev:
	@bash scripts/dev.sh

dev-api:
	IAI_BANK_UI_BASE_URL=http://127.0.0.1:5173 $(UVICORN) interfaces_ai.api.app:app --reload --host 127.0.0.1 --port 8000

dev-ui:
	cd $(BANK_UI) && npm run dev

test:
	$(PYTEST) -q

lint:
	.venv/bin/ruff check src tests

clean:
	rm -rf .venv banks-ui/node_modules banks-ui/dist .pytest_cache .ruff_cache src/*.egg-info
