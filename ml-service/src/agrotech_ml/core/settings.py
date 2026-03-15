from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parents[3]


class AppSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="AGROTECH_", env_file=".env", extra="ignore"
    )

    data_path: Path = ROOT_DIR / "data" / "Crop_dataset.csv"
    artifacts_dir: Path = ROOT_DIR / "artifacts"
    uploads_dir: Path = ROOT_DIR / "uploads"

    model_filename: str = "crop_model.joblib"
    metadata_filename: str = "model_metadata.json"
    disease_model_filename: str = "disease_model.joblib"
    fertilizer_model_filename: str = "fertilizer_model.joblib"
    irrigation_model_filename: str = "irrigation_model.joblib"
    database_filename: str = "agrotech.db"

    environment: str = "development"
    public_base_url: str = "http://127.0.0.1:8000"
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000,http://localhost:3001,http://127.0.0.1:3001"
    max_upload_size_bytes: int = 10 * 1024 * 1024
    allowed_upload_types: str = "image/jpeg,image/png,image/webp,application/pdf"
    request_timeout_seconds: int = 20

    sarvam_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("AGROTECH_SARVAM_API_KEY", "SARVAM_API_KEY"),
    )
    sarvam_api_url: str = "https://api.sarvam.ai/translate"
    sarvam_model: str = "mayura:v1"
    myscheme_api_url: str = "https://api.myscheme.gov.in"
    myscheme_api_key: str = "tYTy5eEhlu9rFjyxuCr7ra7ACp4dv1RH8gWuHTDc"
    data_gov_market_catalog_url: str = "https://www.data.gov.in/resource/current-daily-price-various-commodities-various-markets-mandi"
    data_gov_market_source_name: str = "data.gov.in"
    enam_logistics_url: str = "https://enam.gov.in/web/eNAM-Logistics-Providers"
    brave_search_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "AGROTECH_BRAVE_SEARCH_API_KEY",
            "BRAVE_SEARCH_API_KEY",
        ),
    )
    admin_username: str | None = None
    admin_password_hash: str | None = None
    admin_password: str | None = None
    jwt_secret: str | None = None
    access_token_ttl_minutes: int = 120
    require_write_auth: bool = False
    enable_audit_logging: bool = True

    random_state: int = 42
    test_size: float = 0.2

    @property
    def model_path(self) -> Path:
        return self.artifacts_dir / self.model_filename

    @property
    def metadata_path(self) -> Path:
        return self.artifacts_dir / self.metadata_filename

    @property
    def disease_model_path(self) -> Path:
        return self.artifacts_dir / self.disease_model_filename

    @property
    def fertilizer_model_path(self) -> Path:
        return self.artifacts_dir / self.fertilizer_model_filename

    @property
    def irrigation_model_path(self) -> Path:
        return self.artifacts_dir / self.irrigation_model_filename

    @property
    def database_path(self) -> Path:
        return self.artifacts_dir / self.database_filename

    @property
    def cors_origins_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]

    @property
    def allowed_upload_types_list(self) -> set[str]:
        return {item.strip().lower() for item in self.allowed_upload_types.split(",") if item.strip()}


@lru_cache(maxsize=1)
def get_settings() -> AppSettings:
    settings = AppSettings()
    if settings.environment.lower() == "production" and not settings.jwt_secret:
        raise RuntimeError("Set AGROTECH_JWT_SECRET before running in production.")
    if settings.require_write_auth and (
        not settings.jwt_secret or not settings.admin_username or not (settings.admin_password_hash or settings.admin_password)
    ):
        raise RuntimeError(
            "Write auth is enabled, but AGROTECH_JWT_SECRET and admin credentials are missing."
        )
    settings.artifacts_dir.mkdir(parents=True, exist_ok=True)
    settings.uploads_dir.mkdir(parents=True, exist_ok=True)
    from agrotech_ml.db.storage import init_db

    init_db(settings)
    return settings
