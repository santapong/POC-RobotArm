.PHONY: help install install-rtb install-all test test-rtb smoke uat sim lint clean

PYTHON ?= python

help:
	@echo "Targets:"
	@echo "  install      - pip install -e .[sim,dev]"
	@echo "  install-rtb  - pip install -e .[sim,rtb,dev]"
	@echo "  install-all  - pip install -e .[all,dev]"
	@echo "  test         - run headless tests (no rtb required)"
	@echo "  test-rtb     - run all tests including rtb-gated ones"
	@echo "  smoke        - run GUI smoke test (opens a real PyBullet window)"
	@echo "  uat          - run scripts/uat_run.py (UAT acceptance harness)"
	@echo "  sim          - launch the interactive simulator with Panda"
	@echo "  lint         - ruff check"
	@echo "  clean        - remove build/test artifacts"

install:
	$(PYTHON) -m pip install -e .[sim,dev]

install-rtb:
	$(PYTHON) -m pip install -e .[sim,rtb,dev]

install-all:
	$(PYTHON) -m pip install -e .[all,dev]

test:
	$(PYTHON) -m pytest -q --ignore=tests/test_robots.py \
	         --ignore=tests/test_forward.py \
	         --ignore=tests/test_inverse.py

test-rtb:
	$(PYTHON) -m pytest -q

smoke:
	RUN_GUI_TESTS=1 $(PYTHON) -m pytest tests/test_gui_smoke.py -v

uat:
	$(PYTHON) scripts/uat_run.py

sim:
	$(PYTHON) -m src.simulation --robot panda

lint:
	$(PYTHON) -m ruff check src tests

clean:
	rm -rf build dist *.egg-info .pytest_cache __pycache__ artifacts/*.png artifacts/*.ppm
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
