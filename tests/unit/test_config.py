import pytest

from app.core.config import Settings

GOOD_KEY = "x" * 40


def test_development_may_use_weak_secrets():
    # no exception: convenience defaults are fine outside production
    assert Settings(ENV="development", SECRET_KEY="CHANGE_ME_dev", DEBUG=True).ENV == "development"


@pytest.mark.parametrize("key", ["CHANGE_ME_IN_PRODUCTION_super_secret_key", "short", ""])
def test_production_rejects_weak_or_placeholder_secret(key):
    with pytest.raises(ValueError, match="SECRET_KEY"):
        Settings(ENV="production", SECRET_KEY=key, DEBUG=False)


def test_production_rejects_debug_mode():
    with pytest.raises(ValueError, match="DEBUG"):
        Settings(ENV="production", SECRET_KEY=GOOD_KEY, DEBUG=True)


def test_production_accepts_a_proper_configuration():
    s = Settings(ENV="production", SECRET_KEY=GOOD_KEY, DEBUG=False)
    assert s.ENV == "production"


def test_seed_refuses_default_admin_password_in_production(monkeypatch, client, db):
    from scripts import seed
    monkeypatch.setattr(seed.settings, "ENV", "production")
    monkeypatch.delenv("ADMIN_PASSWORD", raising=False)
    with pytest.raises(SystemExit, match="ADMIN_PASSWORD"):
        seed.seed_admin(db)
