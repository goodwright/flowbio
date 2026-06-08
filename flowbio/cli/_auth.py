"""Credential and base-URL resolution for the CLI (FR-006…FR-013).

A single :func:`resolve_credentials` builds a
:class:`~flowbio.v2.auth.Credentials` strategy from CLI inputs, environment
variables, and (as a last resort) an interactive prompt, applying a fixed
precedence so each rule stays testable in isolation. The CLI adds no
authentication protocol of its own — it constructs the same credential objects
the library already exposes.

Passwords are **only** ever read from an interactive ``getpass`` prompt, never
from a flag or environment variable (Principle VI). When a prompt would be
needed but stdin is not a TTY, resolution fails fast with a usage error rather
than hanging.
"""
from __future__ import annotations

import getpass
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from flowbio.cli._exit_codes import CliUsageError
from flowbio.v2.auth import Credentials, TokenCredentials, UsernamePasswordCredentials

DEFAULT_BASE_URL = "https://app.flow.bio/api"
DEFAULT_TOKEN_FILE = Path.home() / ".config" / "flow" / "api-token"


@dataclass(frozen=True)
class ResolvedCredentials:
    """The credential strategy plus the base URL to construct a client with."""

    credentials: Credentials
    base_url: str


def resolve_credentials(
    *,
    token: str | None,
    token_file: str | None,
    base_url: str | None,
    login: bool,
    username: str | None,
    env: Mapping[str, str] | None = None,
) -> ResolvedCredentials:
    """Resolve credentials and the base URL from CLI inputs and the environment.

    Credential precedence (highest first): ``--login`` → ``--token`` /
    ``FLOW_API_TOKEN`` → ``--token-file`` / ``FLOW_TOKEN_FILE`` → the default
    token file (``~/.config/flow/api-token``) → an interactive
    username/password prompt. Base URL: ``--base-url`` > ``FLOW_API_URL`` >
    the library default.

    :param token: A token supplied via ``--token``.
    :param token_file: A token-file path supplied via ``--token-file``.
    :param base_url: A base URL supplied via ``--base-url``.
    :param login: Whether ``--login`` forced interactive username/password auth.
    :param username: A username supplied via ``--username`` (password is always
        prompted).
    :param env: Environment mapping to read (defaults to ``os.environ``).
    :returns: The resolved credentials and base URL.
    :raises CliUsageError: On conflicting flags, a missing/empty named token
        file, or when a prompt is required but stdin is not interactive.
    """
    environment = _environ() if env is None else env
    resolved_base_url = (
        base_url or environment.get("FLOW_API_URL") or DEFAULT_BASE_URL
    )

    if login and token is not None:
        raise CliUsageError(
            "--token cannot be combined with --login; choose one.",
        )

    credentials = _resolve_strategy(token, token_file, login, username, environment)
    return ResolvedCredentials(credentials=credentials, base_url=resolved_base_url)


def _resolve_strategy(
    token: str | None,
    token_file: str | None,
    login: bool,
    username: str | None,
    environment: Mapping[str, str],
) -> Credentials:
    if login:
        return _prompt_for_credentials(username)
    if token is not None:
        return TokenCredentials(token)
    env_token = environment.get("FLOW_API_TOKEN")
    if env_token:
        return TokenCredentials(env_token)
    if token_file is not None:
        return TokenCredentials(_read_required_token_file(Path(token_file)))
    env_token_file = environment.get("FLOW_TOKEN_FILE")
    if env_token_file:
        return TokenCredentials(_read_required_token_file(Path(env_token_file)))
    default_token = _read_optional_token_file(DEFAULT_TOKEN_FILE)
    if default_token:
        return TokenCredentials(default_token)
    return _prompt_for_credentials(username)


def _read_required_token_file(path: Path) -> str:
    token = _read_optional_token_file(path)
    if not token:
        raise CliUsageError(
            f"Token file {path} is missing or empty.",
        )
    return token


def _read_optional_token_file(path: Path) -> str | None:
    if not path.is_file():
        return None
    return path.read_text().strip() or None


def _prompt_for_credentials(username: str | None) -> UsernamePasswordCredentials:
    if not _stdin_is_interactive():
        raise CliUsageError(
            "No credentials provided and stdin is not interactive. Supply a "
            "token via --token/FLOW_API_TOKEN, --token-file/FLOW_TOKEN_FILE, or "
            "~/.config/flow/api-token.",
        )
    resolved_username = username if username is not None else _prompt_username()
    password = _prompt_password()
    return UsernamePasswordCredentials(username=resolved_username, password=password)


def _environ() -> Mapping[str, str]:
    return os.environ


def _stdin_is_interactive() -> bool:
    return sys.stdin.isatty()


def _prompt_username() -> str:
    return input("Flow username: ")


def _prompt_password() -> str:
    return getpass.getpass("Flow password: ")
