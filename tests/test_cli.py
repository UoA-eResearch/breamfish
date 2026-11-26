import os
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

import breamfish
from breamfish import cli, refresh

REPO = Path(__file__).parent.parent


def test_data_dir_option_beats_environment_beats_default(monkeypatch):
    monkeypatch.delenv("BREAMFISH_DATA_DIR", raising=False)
    assert cli.data_dir_from(None) == Path("data")

    monkeypatch.setenv("BREAMFISH_DATA_DIR", "/var/lib/breamfish")
    assert cli.data_dir_from(None) == Path("/var/lib/breamfish")
    assert cli.data_dir_from(Path("/tmp/elsewhere")) == Path("/tmp/elsewhere")


def test_refresh_passes_the_data_dir_and_returns_the_exit_code(monkeypatch, tmp_path):
    seen = {}

    def fake_run(data_dir, get, now=None):
        seen["data_dir"] = data_dir
        return 1

    monkeypatch.setattr(refresh, "run", fake_run)

    assert cli.main(["refresh", "--data-dir", str(tmp_path)]) == 1
    assert seen["data_dir"] == tmp_path


def test_version_command(capsys):
    assert cli.main(["version"]) == 0
    assert capsys.readouterr().out.strip() == breamfish.__version__


def test_version_matches_pyproject():
    pyproject = tomllib.loads((REPO / "pyproject.toml").read_text())
    assert breamfish.__version__ == pyproject["project"]["version"]


def test_a_command_is_required():
    with pytest.raises(SystemExit):
        cli.main([])


def test_runs_as_a_module_the_way_the_server_calls_it():
    # PYTHONPATH=<checkout>/src python -m breamfish ...
    result = subprocess.run(
        [sys.executable, "-m", "breamfish", "version"],
        env=os.environ | {"PYTHONPATH": str(REPO / "src")},
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert result.stdout.strip() == breamfish.__version__
