from importlib.metadata import version

from flowbio.cli._main import build_parser


class TestVersionAndHelp:

    def test_version_prints_version_and_exits_zero(self, run_cli) -> None:
        result = run_cli("--version")

        assert result.exit_code == 0
        assert version("flowbio") in result.stdout

    def test_top_level_help_exits_zero(self, run_cli) -> None:
        result = run_cli("--help")

        assert result.exit_code == 0
        assert "usage" in result.stdout.lower()

    def test_resource_help_exits_zero(self, run_cli) -> None:
        result = run_cli("data", "--help")

        assert result.exit_code == 0
        assert "usage" in result.stdout.lower()

    def test_samples_resource_help_exits_zero(self, run_cli) -> None:
        result = run_cli("samples", "--help")

        assert result.exit_code == 0
        assert "usage" in result.stdout.lower()


class TestUsageErrors:

    def test_bare_invocation_shows_help_and_exits_usage(self, run_cli) -> None:
        result = run_cli()

        assert result.exit_code == 2
        assert "usage" in result.stderr.lower()

    def test_resource_without_verb_shows_help_and_exits_usage(self, run_cli) -> None:
        result = run_cli("data")

        assert result.exit_code == 2
        assert "usage" in result.stderr.lower()

    def test_unknown_resource_exits_usage(self, run_cli) -> None:
        result = run_cli("bogus")

        assert result.exit_code == 2

    def test_unknown_verb_exits_usage(self, run_cli) -> None:
        result = run_cli("data", "bogus")

        assert result.exit_code == 2


class TestGlobalOptionPlacement:
    """FR-004: global options behave identically before and after the resource.

    The verb-level parity (``flowbio --json samples upload …`` ≡
    ``… --json``) is exercised once a leaf command exists (see test_data.py and
    the polish regression test); here we verify the parent-on-subparser merge
    mechanism that makes it work.
    """

    def test_flag_accepted_before_and_after_resource(self) -> None:
        parser = build_parser()

        before = parser.parse_args(["--json", "data"])
        after = parser.parse_args(["data", "--json"])

        assert getattr(before, "json", False) is True
        assert getattr(after, "json", False) is True

    def test_value_option_accepted_before_and_after_resource(self) -> None:
        token = "tok.value"
        parser = build_parser()

        before = parser.parse_args(["--token", token, "data"])
        after = parser.parse_args(["data", "--token", token])

        assert getattr(before, "token", None) == token
        assert getattr(after, "token", None) == token
