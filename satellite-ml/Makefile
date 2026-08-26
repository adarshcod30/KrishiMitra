# KrishiMitra-RS — common tasks
PY ?= python3

.PHONY: help install run run-gee dataset dashboard test lint docker sync-config clean

help:
	@echo "make install    - install core deps (editable)"
	@echo "make run        - run the full pipeline on the simulated pilot"
	@echo "make run-gee    - run on real Sentinel-1/2 (needs Earth Engine auth)"
	@echo "make dataset    - build & cache the pilot ARD cube to data/processed/"
	@echo "make dashboard  - launch the Streamlit dashboard"
	@echo "make test       - run the pytest suite"
	@echo "make docker     - build the Cloud Run Job image"
	@echo "make sync-config- copy config/pilot_area.yaml over the packaged default"
	@echo "make clean      - remove generated outputs"

install:
	$(PY) -m pip install -e .

run:
	$(PY) -m krishimitra_rs.pipeline

run-gee:
	$(PY) -m krishimitra_rs.pipeline --source gee

dataset:
	$(PY) scripts/make_pilot_dataset.py

dashboard:
	streamlit run dashboard/app.py

test:
	$(PY) -m pytest tests/ -q

lint:
	ruff check src tests || true

docker:
	docker build -t krishimitra-satellite .

# The package ships a byte-identical default config so a non-editable install
# can find one; tests fail if the two drift.
sync-config:
	cp config/pilot_area.yaml src/krishimitra_rs/config/pilot_area.yaml

clean:
	rm -rf outputs/maps/* outputs/figures/* outputs/tables/* outputs/models/*
	find . -name '__pycache__' -type d -prune -exec rm -rf {} +
