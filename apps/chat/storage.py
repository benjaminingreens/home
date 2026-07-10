from datetime import datetime, timezone

from core.config import DATA

CHAT_DIR = DATA / "chat"


def chat_file(group_id):
    CHAT_DIR.mkdir(parents=True, exist_ok=True)
    return CHAT_DIR / f"{group_id}.txt"


def append_message(group_id, username, text):
    text = text.replace("\n", " ").replace("\t", " ").strip()

    if not text:
        return

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    line = f"{timestamp}\t{username}\t{text}\n"

    with chat_file(group_id).open("a", encoding="utf-8") as f:
        f.write(line)


def load_messages(group_id, limit=200):
    path = chat_file(group_id)

    if not path.exists():
        return []

    lines = path.read_text(encoding="utf-8").splitlines()[-limit:]
    messages = []

    for line in lines:
        parts = line.split("\t", 2)

        if len(parts) == 3:
            timestamp, username, text = parts
            messages.append({"timestamp": timestamp, "username": username, "text": text})

    return messages
