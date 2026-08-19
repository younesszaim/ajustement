from streamlit_app.config import load_settings


def test_existing_supabase_environment_selects_simulation(monkeypatch):
    monkeypatch.delenv("POSTGRES_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("OUTPUT_DATABASE", raising=False)
    monkeypatch.delenv("LIMON_PROJECT_CONFIG", raising=False)
    monkeypatch.setenv("SUPABASE_DB_URL", "postgresql://supabase.example/test")

    settings = load_settings()

    assert settings.output_database == "postgres"
    assert settings.postgres_url == "postgresql://supabase.example/test"
    assert settings.project["output_schema"] == "vertica_sim"
