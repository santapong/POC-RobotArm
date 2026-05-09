.PHONY: help install install-rtb install-all install-kali test test-rtb smoke smoke-ui uat sim lint clean

PYTHON ?= python

help:
	@echo "Targets:"
	@echo "  install      - pip install -e .[sim,dev]"
	@echo "  install-rtb  - pip install -e .[sim,rtb,dev]"
	@echo "  install-all  - pip install -e .[all,dev]"
	@echo "  install-kali - apt-install Qt+OpenGL libs, then [sim,rtb,cam,ui,dev] (see docs/UAT_KALI.md)"
	@echo "  test         - run headless tests (no rtb required)"
	@echo "  test-rtb     - run all tests including rtb-gated ones"
	@echo "  smoke        - run PyBullet GUI smoke test (opens a real window)"
	@echo "  smoke-ui     - run PySide6 UI smoke test under offscreen Qt"
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

# One-shot Kali / Debian setup: apt the Qt+OpenGL system libs, then pip the
# extras needed to run every UAT story (incl. CAM and PySide6 demos).
# See docs/UAT_KALI.md for the full walkthrough and troubleshooting notes.
install-kali:
	sudo apt update
	sudo apt install -y python3 python3-venv python3-pip python3-dev \
	    git build-essential pkg-config \
	    libgl1 libglu1-mesa libegl1 \
	    libxkbcommon0 libxkbcommon-x11-0 \
	    libdbus-1-3 libfontconfig1 \
	    libxcb-cursor0 libxcb-icccm4 libxcb-image0 libxcb-keysyms1 \
	    libxcb-randr0 libxcb-render-util0 libxcb-shape0 libxcb-sync1 \
	    libxcb-xfixes0 libxcb-xkb1 \
	    xvfb
	$(PYTHON) -m pip install --upgrade pip
	$(PYTHON) -m pip install -e .[sim,rtb,cam,ui,dev]

test:
	$(PYTHON) -m pytest -q --ignore=tests/test_robots.py \
	         --ignore=tests/test_forward.py \
	         --ignore=tests/test_inverse.py

test-rtb:
	$(PYTHON) -m pytest -q

smoke:
	RUN_GUI_TESTS=1 $(PYTHON) -m pytest tests/test_gui_smoke.py -v

smoke-ui:
	RUN_GUI_TESTS=1 QT_QPA_PLATFORM=offscreen $(PYTHON) -m pytest tests/test_ui_smoke.py -v

uat:
	$(PYTHON) scripts/uat_run.py

sim:
	$(PYTHON) -m src.simulation --robot panda

lint:
	$(PYTHON) -m ruff check src tests

clean:
	rm -rf build dist *.egg-info .pytest_cache __pycache__ artifacts/*.png artifacts/*.ppm
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
