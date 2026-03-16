from app.config import Settings


class TestSettings:
    def test_default_values(self) -> None:
        settings = Settings(
            _env_file=None,  # type: ignore[call-arg]
        )
        assert settings.db_path == "data/factapi.db"
        assert settings.api_key == ""
        assert settings.admin_key == ""
        assert settings.default_limit == 100
        assert settings.max_limit == 1000
        assert settings.cors_origins == "*"
        assert settings.log_level == "info"

    def test_cors_origins_list_single(self) -> None:
        settings = Settings(cors_origins="*", _env_file=None)  # type: ignore[call-arg]
        assert settings.cors_origins_list == ["*"]

    def test_cors_origins_list_multiple(self) -> None:
        settings = Settings(
            cors_origins="http://localhost:3000, http://example.com",
            _env_file=None,  # type: ignore[call-arg]
        )
        assert settings.cors_origins_list == [
            "http://localhost:3000",
            "http://example.com",
        ]
