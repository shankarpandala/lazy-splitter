.PHONY: help install install-dev test lint format clean build publish

help:
	@echo "Available commands:"
	@echo "  make install      - Install package in production mode"
	@echo "  make install-dev  - Install package with development dependencies"
	@echo "  make test         - Run tests with pytest"
	@echo "  make lint         - Run linters (flake8, black check, mypy)"
	@echo "  make format       - Format code with black"
	@echo "  make clean        - Remove build artifacts"
	@echo "  make build        - Build distribution packages"
	@echo "  make publish      - Publish to PyPI (requires credentials)"

install:
	pip install .

install-dev:
	pip install -e ".[dev]"

test:
	pytest --cov=pdf_splitter --cov-report=html --cov-report=term

lint:
	flake8 src/
	black --check src/
	mypy src/

format:
	black src/

clean:
	rm -rf build/
	rm -rf dist/
	rm -rf *.egg-info
	rm -rf .pytest_cache/
	rm -rf .coverage
	rm -rf htmlcov/
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete

build: clean
	python -m build

publish: build
	twine upload dist/*
