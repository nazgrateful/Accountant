import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SAMPLES = ROOT / "samples"


@pytest.fixture(scope="session")
def samples() -> Path:
    if not (SAMPLES / "bank_statement_march_2024.pdf").exists():
        subprocess.run([sys.executable, str(ROOT / "scripts" / "make_samples.py")], check=True)
    return SAMPLES


@pytest.fixture
def app(tmp_path):
    from ledgerlens import create_app

    app = create_app({"TESTING": True, "DATABASE": str(tmp_path / "test.db")})
    yield app


@pytest.fixture
def client(app):
    return app.test_client()
