# AgroTech Unified Farmer Service

Advanced FastAPI backend for a multilingual farmer platform.

## Included capabilities

- Crop recommendation (ensemble classification)
- Irrigation scheduler (regression model)
- Disease diagnosis from symptoms (text classifier)
- Fertilizer advisory model
- Weather forecast (Open-Meteo integration)
- Government scheme navigator
- Marketplace prices, equipment rental catalog, investor opportunities
- Profile and farm record endpoints

## Quick start

```bash
cd ml-service
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
python scripts/bootstrap_datasets.py
python -m agrotech_ml.train
python -m uvicorn agrotech_ml.api:app --reload --port 8000
```

## Key endpoints

- `GET /health`
- `GET /languages`
- `GET /dashboard/summary`
- `GET /metadata`
- `POST /predict`
- `POST /irrigation/schedule`
- `POST /disease/diagnose`
- `POST /fertilizer/recommend`
- `GET /weather/forecast`
- `POST /schemes/recommend`
- `GET /market/prices`
- `GET /rentals/tools`
- `GET /investor/opportunities`
- `GET /knowledge/library`
- `POST /profiles/user`
- `POST /profiles/farms`

