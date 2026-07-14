from pathlib import Path
from .parser import parse
from core import sync_state
import shlex
import subprocess

SYNC_TIMEOUT = 10  # seconds - a hung network op shouldn't hang the request

VENDOR = Path(__file__).parent / "vendor"
ARK = VENDOR / "bin" / "ark"
COMMAND_DIR = VENDOR / "lib" / "ark" / "commands"

BUILTIN_COMMANDS = {
    "help", "init", "edit", "glance",
    "basic", "compact", "pipe", "pretty", "wrap",
}


def known_commands():
    commands = set(BUILTIN_COMMANDS)

    if COMMAND_DIR.is_dir():
        commands.update(
            p.name for p in COMMAND_DIR.iterdir()
            if p.is_file() and not p.name.endswith(".txt")
        )

    return commands


def install(workspace):

    workspace.mkdir(parents=True, exist_ok=True)

    subprocess.run(
        [str(ARK), "init"],
        cwd=workspace,
        check=True,
    )


def run(workspace, command):

    command = command.strip()
    tokens = shlex.split(command)

    if tokens and tokens[0].lower() in known_commands():
        # Dispatch is case-insensitive ("Help"/"HELP"/"help" all count),
        # but the actual subprocess call uses the canonical lowercase
        # spelling - the real ark binary's own command dispatch is
        # case-sensitive, so a token like "Help" would otherwise be
        # passed through unrecognized and misinterpreted.
        args = [tokens[0].lower()] + tokens[1:]
    else:
        args = [command]

    result = subprocess.run(
        [str(ARK), *args],
        cwd=workspace,
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
    )

    return parse(result.stdout), result.stdout.strip(), result.stderr.strip()


def add(workspace, text):

    text = text.strip()

    if not text.endswith(";;"):
        text += ";;"

    inbox = workspace / "inbox.txt"

    with inbox.open("a", encoding="utf-8") as f:
        f.write(text + "\n")


def is_git_linked(workspace):
    return (workspace / ".git").exists()


def _git(workspace, *args):
    try:
        return subprocess.run(
            ["git", *args],
            cwd=workspace,
            capture_output=True,
            text=True,
            stdin=subprocess.DEVNULL,
            timeout=SYNC_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(args, 1, "", "timed out")


def auto_sync(workspace, workspace_id):
    """Best-effort background sync - called on every workspace page load
    and after every mutation, so the user never has to think about
    syncing. Commits any local changes, fetches + merges the remote, then
    pushes.

    On a real conflict, aborts the merge (leaving the working tree at the
    local commit - safe to keep reading/using) and flags the workspace
    conflicted instead of leaving conflict markers baked into files on
    disk; further mutations to the workspace are refused (see
    core.sync_state) until it's resolved via the conflicts screen.

    Silently no-ops if the workspace isn't git-linked, is offline/the
    remote is unreachable, or is already flagged conflicted - in all
    these cases the caller just proceeds with whatever's on disk."""

    if not is_git_linked(workspace):
        return

    if sync_state.is_conflicted(workspace_id):
        return

    status = _git(workspace, "status", "--porcelain")

    if status.returncode != 0:
        return

    if status.stdout.strip():
        _git(workspace, "add", "-A")
        _git(workspace, "commit", "-m", "auto-sync: local changes")

    fetch = _git(workspace, "fetch")

    if fetch.returncode != 0:
        return  # offline / remote unreachable - try again next time

    merge = _git(workspace, "merge", "--no-edit", "FETCH_HEAD")

    if merge.returncode != 0:
        conflicted = _git(workspace, "diff", "--name-only", "--diff-filter=U").stdout.split()
        remote_sha = _git(workspace, "rev-parse", "FETCH_HEAD").stdout.strip()
        _git(workspace, "merge", "--abort")
        sync_state.mark_conflict(workspace_id, conflicted, remote_sha)
        return

    _git(workspace, "push")


def theirs_content(workspace, path, remote_sha):
    """The remote side's version of a conflicted file, as of the fetch
    that produced the conflict - None if the file didn't exist there."""

    result = _git(workspace, "show", f"{remote_sha}:{path}")
    return result.stdout if result.returncode == 0 else None


def resolve_conflict(workspace, choices, remote_sha):
    """choices: {path: "mine" | "theirs"}. "mine" needs no write - the
    working tree already holds the local version (the merge that
    conflicted was aborted). "theirs" overwrites with the remote's
    version. Either way the file is staged, then the merge is completed
    with a resolution commit and pushed."""

    for path, choice in choices.items():
        if choice == "theirs":
            content = theirs_content(workspace, path, remote_sha)

            if content is not None:
                target = workspace / path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content, encoding="utf-8")

        _git(workspace, "add", path)

    _git(workspace, "commit", "-m", "sync: resolve conflict")
    _git(workspace, "push")
