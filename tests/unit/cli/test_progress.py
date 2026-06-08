from flowbio.cli._progress import progress_config
from flowbio.v2.client import ClientConfig


def test_no_progress_disables_show_progress() -> None:
    assert progress_config(no_progress=True).show_progress is False


def test_default_keeps_show_progress_enabled() -> None:
    assert progress_config(no_progress=False).show_progress is True


def test_returns_a_client_config() -> None:
    assert isinstance(progress_config(no_progress=False), ClientConfig)
