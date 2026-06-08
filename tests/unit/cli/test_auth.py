from pathlib import Path

import pytest

from flowbio.cli import _auth
from flowbio.cli._auth import DEFAULT_BASE_URL, resolve_credentials
from flowbio.cli._exit_codes import CliUsageError
from flowbio.cli._types import BaseUrl, Token
from flowbio.v2.auth import TokenCredentials, UsernamePasswordCredentials

MISSING_DEFAULT_FILE = Path("/nonexistent/flow/api-token")


def _resolve(*, token=None, token_file=None, base_url=None, login=False, username=None, env={}):
    # Mirror the CLI boundary: raw strings become the named types before
    # reaching resolve_credentials. `login` maps to the force_login parameter.
    return resolve_credentials(
        token=Token(token) if token is not None else None,
        token_file=Path(token_file) if token_file is not None else None,
        base_url=BaseUrl(base_url) if base_url is not None else None,
        force_login=login,
        username=username,
        env=env,
    )


def _assert_token(credentials: object, expected: str) -> None:
    assert isinstance(credentials, TokenCredentials)
    assert credentials._token == expected


def _fail_if_called() -> str:
    raise AssertionError("prompt should not be called")


@pytest.fixture
def interactive(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_auth, "_stdin_is_interactive", lambda: True)


@pytest.fixture
def no_default_token_file(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_auth, "DEFAULT_TOKEN_FILE", MISSING_DEFAULT_FILE)


class TestTokenPrecedence:

    def test_token_flag_beats_env_token(self) -> None:
        flag_token = "flag.token"

        resolved = _resolve(token=flag_token, env={"FLOW_API_TOKEN": "env.token"})

        _assert_token(resolved.credentials, flag_token)

    def test_env_token_used_when_no_flag(self) -> None:
        env_token = "env.token"

        resolved = _resolve(env={"FLOW_API_TOKEN": env_token})

        _assert_token(resolved.credentials, env_token)

    def test_token_beats_token_file(self, tmp_path: Path) -> None:
        flag_token = "flag.token"
        token_file = tmp_path / "api-token"
        token_file.write_text("file.token")

        resolved = _resolve(token=flag_token, token_file=str(token_file))

        _assert_token(resolved.credentials, flag_token)

    def test_token_file_flag_read_and_stripped(self, tmp_path: Path) -> None:
        token_file = tmp_path / "api-token"
        token_file.write_text("  file.token\n")

        resolved = _resolve(token_file=str(token_file))

        _assert_token(resolved.credentials, "file.token")

    def test_token_file_flag_beats_env_token_file(self, tmp_path: Path) -> None:
        flag_file = tmp_path / "flag-token"
        flag_file.write_text("flag.file.token")
        env_file = tmp_path / "env-token"
        env_file.write_text("env.file.token")

        resolved = _resolve(
            token_file=str(flag_file),
            env={"FLOW_TOKEN_FILE": str(env_file)},
        )

        _assert_token(resolved.credentials, "flag.file.token")

    def test_default_token_file_used_as_last_resort(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        default_file = tmp_path / "api-token"
        default_file.write_text("default.token")
        monkeypatch.setattr(_auth, "DEFAULT_TOKEN_FILE", default_file)

        resolved = _resolve()

        _assert_token(resolved.credentials, "default.token")


class TestLoginPrecedence:

    def test_login_forces_username_password_over_env_token(
        self, interactive: None, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(_auth, "_prompt_username", lambda: "alice")
        monkeypatch.setattr(_auth, "_prompt_password", lambda: "s3cret")

        resolved = _resolve(login=True, env={"FLOW_API_TOKEN": "env.token"})

        assert isinstance(resolved.credentials, UsernamePasswordCredentials)
        assert resolved.credentials.username == "alice"
        assert resolved.credentials.password == "s3cret"

    def test_username_flag_skips_username_prompt(
        self, interactive: None, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        username = "bob"
        monkeypatch.setattr(_auth, "_prompt_username", _fail_if_called)
        monkeypatch.setattr(_auth, "_prompt_password", lambda: "pw")

        resolved = _resolve(login=True, username=username)

        assert isinstance(resolved.credentials, UsernamePasswordCredentials)
        assert resolved.credentials.username == username

    def test_password_only_comes_from_getpass_prompt(
        self, interactive: None, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        prompted = []
        monkeypatch.setattr(_auth, "_prompt_username", lambda: "alice")
        monkeypatch.setattr(
            _auth, "_prompt_password", lambda: (prompted.append(True), "pw")[1],
        )

        _resolve(login=True)

        assert prompted == [True]


class TestBaseUrl:

    def test_flag_beats_env_and_default(self) -> None:
        flag_url = "https://flag.example/api"

        resolved = _resolve(
            token="t",
            base_url=flag_url,
            env={"FLOW_API_URL": "https://env.example/api"},
        )

        assert resolved.base_url == flag_url

    def test_env_used_when_no_flag(self) -> None:
        env_url = "https://env.example/api"

        resolved = _resolve(token="t", env={"FLOW_API_URL": env_url})

        assert resolved.base_url == env_url

    def test_default_when_neither_flag_nor_env(self) -> None:
        resolved = _resolve(token="t")

        assert resolved.base_url == DEFAULT_BASE_URL


class TestUsageErrors:

    def test_token_with_login_is_usage_error(self) -> None:
        with pytest.raises(CliUsageError):
            _resolve(token="t", login=True)

    def test_named_token_file_missing_is_usage_error(self, tmp_path: Path) -> None:
        missing = tmp_path / "does-not-exist"

        with pytest.raises(CliUsageError):
            _resolve(token_file=str(missing))

    def test_named_token_file_empty_is_usage_error(self, tmp_path: Path) -> None:
        empty = tmp_path / "api-token"
        empty.write_text("   \n")

        with pytest.raises(CliUsageError):
            _resolve(token_file=str(empty))

    def test_prompt_needed_but_non_interactive_is_usage_error(
        self, no_default_token_file: None, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(_auth, "_stdin_is_interactive", lambda: False)

        with pytest.raises(CliUsageError):
            _resolve()

    def test_login_non_interactive_is_usage_error(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(_auth, "_stdin_is_interactive", lambda: False)

        with pytest.raises(CliUsageError):
            _resolve(login=True)
