# Makefile for cloudmesh-ai-pi

# Project settings
PROJECT_NAME = cloudmesh-ai-pi
VERSION_FILE = VERSION
GIT = git
PIP = pip
PYTHON = python3

# Build and install
all: install

install:
	$(PIP) install -e .

# Testing
test:
	$(PYTHON) -m pytest tests

# Release
upload:
	$(PIP) install .
	$(PIP) upload dist/*

tag:
	@VERSION=$$(cat $(VERSION_FILE)); \
	echo "Tagging version v$$VERSION..."; \
	$(GIT) tag -a v$$VERSION -m "Release v$$VERSION"; \
	$(GIT) push origin v$$VERSION

release: upload tag
	@echo "Production release and tagging complete."

# --- CLEANUP & REINSTALL ---

uninstall-all:
	@echo "Searching for installed cloudmesh-ai packages..."
	@$(PIP) freeze | grep "cloudmesh-ai" | cut -d'=' -f1 | xargs $(PIP) uninstall -y || echo "No cloudmesh-ai packages found."

clean:
	@echo "Cleaning artifacts and temporary test plugins..."
	rm -rf build/ dist/ *.egg-info .pytest_cache .coverage .report.html
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	rm -rf tmp/cloudmesh-ai-*

reinstall: uninstall-all clean
	@echo "Performing fresh install..."
	$(PIP) install -e .