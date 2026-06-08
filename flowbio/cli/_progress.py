"""Progress display wiring (FR-036).

The library already renders upload progress with ``tqdm`` to stderr, so the CLI
adds no progress mechanism of its own — it only translates ``--no-progress``
into the corresponding :class:`~flowbio.v2.client.ClientConfig` flag, keeping
stdout clean for results.
"""
from __future__ import annotations

from flowbio.v2.client import ClientConfig


def progress_config(no_progress: bool) -> ClientConfig:
    """Build a client config honouring ``--no-progress``.

    :param no_progress: Whether the user passed ``--no-progress``.
    :returns: A :class:`ClientConfig` with progress display enabled unless
        suppressed.
    """
    return ClientConfig(show_progress=not no_progress)
