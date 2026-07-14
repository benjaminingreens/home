from pathlib import Path
from .parser import parse
import shlex
import subprocess

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


def sync(workspace):

    if not is_git_linked(workspace):
        return False, "not a git-linked workspace"

    def git(*args):
        return subprocess.run(
            ["git", *args],
            cwd=workspace,
            capture_output=True,
            text=True,
            stdin=subprocess.DEVNULL,
        )

    status = git("status", "--porcelain")

    if status.returncode != 0:
        return False, "git status failed: " + status.stderr.strip()

    if status.stdout.strip():
        git("add", "-A")
        commit = git("commit", "-m", "sync: local changes")

        if commit.returncode != 0:
            return False, "commit failed: " + commit.stderr.strip()

    pull = git("pull", "--no-edit")

    if pull.returncode != 0:
        return False, "pull failed: " + pull.stderr.strip()

    push = git("push")

    if push.returncode != 0:
        return False, "push failed: " + push.stderr.strip()

    return True, "synced"
