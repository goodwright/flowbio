from pathlib import Path

import pytest

from flowbio.cli._exit_codes import CliUsageError
from flowbio.cli._files import existing_file


def test_returns_path_for_an_existing_file(tmp_path: Path) -> None:
    file_path = tmp_path / "counts.tsv"
    file_path.write_bytes(b"data")

    assert existing_file(file_path) == file_path


def test_missing_file_raises_usage_error(tmp_path: Path) -> None:
    missing = tmp_path / "nope.tsv"

    with pytest.raises(CliUsageError):
        existing_file(missing)


def test_directory_raises_usage_error(tmp_path: Path) -> None:
    with pytest.raises(CliUsageError):
        existing_file(tmp_path)
