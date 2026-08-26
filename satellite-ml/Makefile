# KrishiMitra-RS — common tasks
PY ?= python3

.PHONY: help install run run-gee dataset dashboard test lint clean

help:
	@echo "make install    - install core deps (editable)"
	@echo "make run        - run the full pipeline on the simulated pilot"
	@echo "make run-gee    - run on real Sentinel-1/2 (needs Earth Engine auth)"
	@echo "make dataset    - build & cache the pilot ARD cube to data/processed/"
	@echo "make dashboard  - launch the Streamlit dashboard"
	@echo "make test       - run the pytest suite"
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

clean:
	rm -rf outputs/maps/* outputs/figures/* outputs/tables/* outputs/models/*
