from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parents[3]

# Absolute, so the file is found no matter what the working directory is.
# A relative "env_file" only resolves when the process CWD happens to be the
# service root, which is never true inside a container with its own WORKDIR.
ENV_FILE = ROOT_DIR / ".env"


def ensure_directory(path: Path) -> Path:
    """Create ``path`` (with parents), tolerating a dangling symlink at ``path``.

    ``Path.mkdir(exist_ok=True)`` still raises ``FileExistsError`` when the path
    is a symlink whose target does not exist, which is how a checked-in symlink
    pointing at an ephemeral directory takes the whole service down.
    """
    if path.is_symlink() and not path.exists():
        path.unlink(missing_ok=True)
    try:
        path.mkdir(parents=True, exist_ok=True)
    except FileExistsError:
        if not path.is_dir():
            raise
    except OSError as exc:
        raise RuntimeError(
            f"Unable to create directory {path}. "
            "Set AGROTECH_ARTIFACTS_DIR / AGROTECH_UPLOADS_DIR to a writable location."
        ) from exc
    return path


class AppSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="AGROTECH_",
        env_file=ENV_FILE,
        extra="ignore",
        # Fields with an explicit validation_alias would otherwise be
        # unsettable by their Python name (AppSettings(database_url=...)).
        populate_by_name=True,
    )

    data_path: Path = ROOT_DIR / "data" / "Crop_dataset.csv"
    artifacts_dir: Path = Field(
        default=ROOT_DIR / "artifacts",
        validation_alias=AliasChoices("AGROTECH_ARTIFACTS_DIR", "ARTIFACTS_DIR"),
    )
    uploads_dir: Path = Field(
        default=ROOT_DIR / "uploads",
        validation_alias=AliasChoices("AGROTECH_UPLOADS_DIR", "UPLOADS_DIR"),
    )

    model_filename: str = "crop_model.joblib"
    metadata_filename: str = "model_metadata.json"
    disease_model_filename: str = "disease_model.joblib"
    fertilizer_model_filename: str = "fertilizer_model.joblib"
    irrigation_model_filename: str = "irrigation_model.joblib"
    database_filename: str = "agrotech.db"

    environment: str = "development"
    port: int = Field(
        default=8080,
        validation_alias=AliasChoices("PORT", "AGROTECH_PORT"),
    )
    public_base_url: str = "http://127.0.0.1:8000"
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000,http://localhost:3001,http://127.0.0.1:3001"
    max_upload_size_bytes: int = 10 * 1024 * 1024
    allowed_upload_types: str = "image/jpeg,image/png,image/webp,application/pdf"
    request_timeout_seconds: int = 20

    # Managed persistence. Every one of these is optional: when they are unset
    # the service runs entirely on the local filesystem + SQLite (development
    # mode). Model artifacts are always read from ``artifacts_dir``; they are
    # baked into the container image and never downloaded at startup.
    database_url: str | None = Field(
        default=None,
        validation_alias=AliasChoices("AGROTECH_DATABASE_URL", "DATABASE_URL"),
    )

    # Optional S3-compatible uploads (Cloudflare R2, Supabase Storage,
    # Backblaze B2, MinIO, AWS S3). Leave the four required ones unset to keep
    # storing uploads on local disk.
    s3_endpoint_url: str | None = Field(
        default=None,
        validation_alias=AliasChoices("AGROTECH_S3_ENDPOINT_URL", "S3_ENDPOINT_URL"),
    )
    s3_bucket: str | None = Field(
        default=None,
        validation_alias=AliasChoices("AGROTECH_S3_BUCKET", "S3_BUCKET"),
    )
    s3_access_key_id: str | None = Field(
        default=None,
        validation_alias=AliasChoices("AGROTECH_S3_ACCESS_KEY_ID", "S3_ACCESS_KEY_ID"),
    )
    s3_secret_access_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("AGROTECH_S3_SECRET_ACCESS_KEY", "S3_SECRET_ACCESS_KEY"),
    )
    # Only needed when the bucket is served through a public/CDN hostname; when
    # empty, downloads are handed out as short-lived presigned URLs instead.
    s3_public_base_url: str | None = Field(
        default=None,
        validation_alias=AliasChoices("AGROTECH_S3_PUBLIC_BASE_URL", "S3_PUBLIC_BASE_URL"),
    )
    # SigV4 needs *a* region. "auto" is what R2/B2/MinIO expect; set the real
    # region only when the endpoint is AWS S3 itself.
    s3_region: str = Field(
        default="auto",
        validation_alias=AliasChoices("AGROTECH_S3_REGION", "S3_REGION"),
    )
    s3_uploads_prefix: str = "uploads"
    s3_url_expiry_seconds: int = 3600

    sarvam_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("AGROTECH_SARVAM_API_KEY", "SARVAM_API_KEY"),
    )
    sarvam_api_url: str = "https://api.sarvam.ai/translate"
    sarvam_model: str = "mayura:v1"
    myscheme_api_url: str = "https://api.myscheme.gov.in"
    myscheme_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("AGROTECH_MYSCHEME_API_KEY", "MYSCHEME_API_KEY"),
    )
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
    def use_postgres(self) -> bool:
        return bool(self.database_url and self.database_url.strip())

    @property
    def uploads_to_s3(self) -> bool:
        """True only when every credential the S3 client needs is present.

        A partial configuration silently falls back to local disk rather than
        failing uploads, which keeps the zero-config path unbreakable.
        """
        required = (
            self.s3_endpoint_url,
            self.s3_bucket,
            self.s3_access_key_id,
            self.s3_secret_access_key,
        )
        return all(bool(value and value.strip()) for value in required)

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
    ensure_directory(settings.artifacts_dir)
    ensure_directory(settings.uploads_dir)

    # No model download happens here. Artifacts are baked into the image (or
    # trained locally) and read straight from AGROTECH_ARTIFACTS_DIR, so
    # startup never depends on a network round-trip to object storage.
    from agrotech_ml.db.storage import init_db

    init_db(settings)
    return settings
