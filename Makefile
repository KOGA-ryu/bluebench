PYTHON ?= python3

.PHONY: install test run-bluebench run-scanner

install:
	$(PYTHON) -m pip install -r requirements.txt

test:
	$(PYTHON) -m unittest discover -s tests

run-bluebench:
	$(PYTHON) scripts/run_bluebench.py ui

run-scanner:
	$(PYTHON) scripts/run_scanner.py run
