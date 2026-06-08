"""Named types shared across the CLI internals.

These tighten otherwise-anonymous ``str``/``object`` values so signatures
document intent and tooling can catch mix-ups. They are purely internal — the
user-facing surface is the command line — so they satisfy the constitution's
"NewType … when it does not confuse end users".
"""
from __future__ import annotations

from typing import Dict, List, NewType, Union

Token = NewType("Token", str)
"""A Flow API access token."""

BaseUrl = NewType("BaseUrl", str)
"""The base URL of a Flow API instance."""

JsonValue = Union[
    None, bool, int, float, str, List["JsonValue"], Dict[str, "JsonValue"],
]
"""Any JSON-serialisable value emitted as a result or error document."""
