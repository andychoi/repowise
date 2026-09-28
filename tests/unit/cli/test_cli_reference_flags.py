"""Every flag the CLI reference documents is one the command accepts (E6).

``docs/reference/CLI_REFERENCE.md`` told readers to pass ``--no-agents-md`` to
``repowise init``; the option was ``--agents/--no-agents``, so the documented
isolation invocation failed with "No such option". Nothing checked the
reference against the commands, so a renamed or never-shipped flag could sit in
the docs indefinitely.

This reads each ``### `repowise <command>` `` section, takes the flags from the
first column of its option table (the column that *defines* the command's
options, as opposed to prose that mentions other commands' flags) and asserts
the live Click command declares every one of them.
"""

from __future__ import annotations

import re
from pathlib import Path

import click
import pytest

from repowise.cli.main import cli

_REFERENCE = Path(__file__).resolve().parents[3] / "docs" / "reference" / "CLI_REFERENCE.md"
_SECTION_RE = re.compile(r"^### `repowise ([a-z][a-z -]*?)(?: [A-Z\[<].*)?`", re.M)
_ROW_FLAG_RE = re.compile(r"`(--?[A-Za-z][\w-]*)`")


def _sections() -> list[tuple[str, str]]:
    text = _REFERENCE.read_text(encoding="utf-8")
    heads = list(_SECTION_RE.finditer(text))
    out = []
    for i, m in enumerate(heads):
        end = heads[i + 1].start() if i + 1 < len(heads) else len(text)
        body = text[m.end() : end].split("\n## ", 1)[0]
        out.append((m.group(1).strip(), body))
    return out


def _documented_flags(body: str) -> set[str]:
    flags: set[str] = set()
    for line in body.splitlines():
        if not line.startswith("| `-"):
            continue
        first_cell = line.split("|")[1]
        flags.update(_ROW_FLAG_RE.findall(first_cell))
    return flags


def _command(path: str) -> click.Command | None:
    # The root group loads subcommands lazily, so resolve through get_command.
    cmd: click.Command = cli
    ctx = click.Context(cli)
    for part in path.split():
        if not isinstance(cmd, click.Group):
            return None
        nxt = cmd.get_command(ctx, part)
        if nxt is None:
            return None
        ctx = click.Context(nxt, parent=ctx)
        cmd = nxt
    return cmd


def _accepted(cmd: click.Command) -> set[str]:
    """Flags *cmd* declares; for a group, also every subcommand's.

    A group's reference section documents its subcommands' options in one table
    (``repowise security scan --history`` under ``### `repowise security` ``),
    so a flag is valid there if any subcommand declares it.
    """
    names: set[str] = {"--help"}
    for param in cmd.params:
        names.update(getattr(param, "opts", []))
        names.update(getattr(param, "secondary_opts", []))
    if isinstance(cmd, click.Group):
        ctx = click.Context(cmd)
        for sub_name in cmd.list_commands(ctx):
            sub = cmd.get_command(ctx, sub_name)
            if sub is not None:
                names |= _accepted(sub)
    return names


_CASES = [(name, body) for name, body in _sections() if _documented_flags(body)]


def test_the_reference_has_option_tables_to_check() -> None:
    assert len(_CASES) >= 10


@pytest.mark.parametrize(("command", "body"), _CASES, ids=[c for c, _ in _CASES])
def test_every_documented_flag_is_accepted(command: str, body: str) -> None:
    cmd = _command(command)
    assert cmd is not None, f"CLI_REFERENCE documents `repowise {command}`, which does not exist"

    missing = sorted(_documented_flags(body) - _accepted(cmd))

    assert not missing, f"`repowise {command}` does not accept documented flag(s): {missing}"


def test_the_documented_isolation_flags_parse_on_init() -> None:
    """The exact invocation the practice runbook depends on."""
    init = _command("init")
    assert init is not None
    accepted = _accepted(init)
    for flag in (
        "--no-prose",
        "--no-editor-setup",
        "--no-claude-md",
        "--no-agents",
        "--no-agents-md",
    ):
        assert flag in accepted, flag
