import json

from agrotech_ml.core.settings import get_settings
from agrotech_ml.services.training import train_models


def main() -> None:
    settings = get_settings()
    metadata = train_models(settings)

    summary = {
        "best_model": metadata.best_model,
        "dataset_rows": metadata.dataset_rows,
        "trained_at": metadata.trained_at.isoformat(),
        "auxiliary_models": metadata.auxiliary_models,
        "top_models": [
            {
                "model": score.model_name,
                "macro_f1": round(score.macro_f1, 4),
                "accuracy": round(score.accuracy, 4),
            }
            for score in metadata.model_scores[:3]
        ],
    }

    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
