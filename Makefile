.PHONY: setup run test lint fmt clean

setup:
	python -m venv .venv
	.venv/bin/pip install -r requirements-dev.txt
	.venv/bin/pip install -e .

run:
	python -m ics_append $(ARGS)

test:
	python -m pytest tests/ -v --cov=ics_append --cov-report=term-missing

lint:
	ruff check ics_append/ tests/

fmt:
	ruff format ics_append/ tests/

clean:
	rm -rf __pycache__ .pytest_cache .coverage htmlcov dist build *.egg-info .ruff_cache
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
