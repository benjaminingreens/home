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

    if tokens and tokens[0] in known_commands():
        args = tokens
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
