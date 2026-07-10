import re

from .db import connect


def _slugify(name):
    slug = re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")
    return slug or "group"


def get_group(group_id):
    with connect() as con:
        return con.execute("SELECT * FROM groups WHERE id=?", (group_id,)).fetchone()


def get_personal_group(user_id):
    with connect() as con:
        return con.execute(
            """
            SELECT g.* FROM groups g
            JOIN group_members m ON m.group_id = g.id
            WHERE m.user_id=? AND g.is_personal=1
            """,
            (user_id,),
        ).fetchone()


def create_personal_group(user_id, username):
    slug = username.strip().lower()

    with connect() as con:
        con.execute(
            "INSERT INTO groups (slug, name, is_personal, created_by) VALUES (?, ?, 1, ?)",
            (slug, username, user_id),
        )
        group_id = con.execute(
            "SELECT id FROM groups WHERE slug=?", (slug,)
        ).fetchone()["id"]

        con.execute(
            "INSERT INTO group_members (group_id, user_id, status) VALUES (?, ?, 'active')",
            (group_id, user_id),
        )

    return group_id


def create_group(name, creator_id):
    base_slug = _slugify(name)
    slug = base_slug

    with connect() as con:
        n = 2
        while con.execute("SELECT 1 FROM groups WHERE slug=?", (slug,)).fetchone():
            slug = f"{base_slug}-{n}"
            n += 1

        con.execute(
            "INSERT INTO groups (slug, name, is_personal, created_by) VALUES (?, ?, 0, ?)",
            (slug, name.strip(), creator_id),
        )
        group_id = con.execute(
            "SELECT id FROM groups WHERE slug=?", (slug,)
        ).fetchone()["id"]

        con.execute(
            "INSERT INTO group_members (group_id, user_id, status) VALUES (?, ?, 'active')",
            (group_id, creator_id),
        )

    return group_id


def list_user_groups(user_id):
    with connect() as con:
        return con.execute(
            """
            SELECT g.* FROM groups g
            JOIN group_members m ON m.group_id = g.id
            WHERE m.user_id=? AND m.status='active'
            ORDER BY g.is_personal DESC, g.name
            """,
            (user_id,),
        ).fetchall()


def list_pending_invites(user_id):
    with connect() as con:
        return con.execute(
            """
            SELECT g.* FROM groups g
            JOIN group_members m ON m.group_id = g.id
            WHERE m.user_id=? AND m.status='invited'
            ORDER BY g.name
            """,
            (user_id,),
        ).fetchall()


def require_active_member(user_id, group_id):
    with connect() as con:
        row = con.execute(
            "SELECT 1 FROM group_members WHERE group_id=? AND user_id=? AND status='active'",
            (group_id, user_id),
        ).fetchone()

    return row is not None


def list_group_members(group_id):
    with connect() as con:
        return con.execute(
            """
            SELECT u.id, u.username, m.status
            FROM group_members m
            JOIN users u ON u.id = m.user_id
            WHERE m.group_id=?
            ORDER BY m.status, u.username
            """,
            (group_id,),
        ).fetchall()


def list_invitable_users(group_id):
    with connect() as con:
        return con.execute(
            """
            SELECT id, username FROM users
            WHERE visibility != 'private'
            AND id NOT IN (SELECT user_id FROM group_members WHERE group_id=?)
            ORDER BY username
            """,
            (group_id,),
        ).fetchall()


def invite_member(group_id, inviter_id, invitee_id):
    if not require_active_member(inviter_id, group_id):
        raise PermissionError("not a member of this group")

    with connect() as con:
        existing = con.execute(
            "SELECT status FROM group_members WHERE group_id=? AND user_id=?",
            (group_id, invitee_id),
        ).fetchone()

        if existing:
            raise ValueError("already a member or already invited")

        con.execute(
            "INSERT INTO group_members (group_id, user_id, status) VALUES (?, ?, 'invited')",
            (group_id, invitee_id),
        )


def respond_to_invite(group_id, user_id, accept):
    with connect() as con:
        row = con.execute(
            "SELECT status FROM group_members WHERE group_id=? AND user_id=?",
            (group_id, user_id),
        ).fetchone()

        if not row or row["status"] != "invited":
            raise ValueError("no pending invite")

        if accept:
            con.execute(
                "UPDATE group_members SET status='active' WHERE group_id=? AND user_id=?",
                (group_id, user_id),
            )
        else:
            con.execute(
                "DELETE FROM group_members WHERE group_id=? AND user_id=?",
                (group_id, user_id),
            )


def get_workspace(workspace_id):
    with connect() as con:
        return con.execute(
            """
            SELECT w.*, g.slug AS group_slug, g.name AS group_name
            FROM workspaces w
            JOIN groups g ON g.id = w.group_id
            WHERE w.id=?
            """,
            (workspace_id,),
        ).fetchone()


def list_group_workspaces(group_id, app):
    with connect() as con:
        return con.execute(
            "SELECT * FROM workspaces WHERE group_id=? AND app=? ORDER BY name",
            (group_id, app),
        ).fetchall()


def create_workspace_record(group_id, app, name, creator_id):
    if not require_active_member(creator_id, group_id):
        raise PermissionError("not a member of this group")

    name = re.sub(r"\s+", "-", name.strip().lower()) or "default"

    with connect() as con:
        con.execute(
            "INSERT INTO workspaces (group_id, app, name, created_by) VALUES (?, ?, ?, ?)",
            (group_id, app, name, creator_id),
        )

    with connect() as con:
        return con.execute(
            """
            SELECT w.*, g.slug AS group_slug, g.name AS group_name
            FROM workspaces w
            JOIN groups g ON g.id = w.group_id
            WHERE w.group_id=? AND w.app=? AND w.name=?
            """,
            (group_id, app, name),
        ).fetchone()


def get_or_create_default_workspace(user_id, app):
    group = get_personal_group(user_id)

    with connect() as con:
        row = con.execute(
            """
            SELECT w.*, g.slug AS group_slug, g.name AS group_name
            FROM workspaces w
            JOIN groups g ON g.id = w.group_id
            WHERE w.group_id=? AND w.app=? AND w.name='default'
            """,
            (group["id"], app),
        ).fetchone()

    if row:
        return row

    return create_workspace_record(group["id"], app, "default", user_id)


def list_visible_workspaces(user_id, app):
    with connect() as con:
        return con.execute(
            """
            SELECT w.*, g.slug AS group_slug, g.name AS group_name
            FROM workspaces w
            JOIN groups g ON g.id = w.group_id
            JOIN group_members m ON m.group_id = g.id
            LEFT JOIN workspace_visibility v
                ON v.workspace_id = w.id AND v.user_id = ?
            WHERE m.user_id = ? AND m.status = 'active' AND w.app = ?
            AND (v.visible IS NULL OR v.visible = 1)
            ORDER BY g.is_personal DESC, g.name, w.name
            """,
            (user_id, user_id, app),
        ).fetchall()


def list_all_workspaces_with_visibility(user_id, app):
    with connect() as con:
        return con.execute(
            """
            SELECT w.*, g.slug AS group_slug, g.name AS group_name,
                   COALESCE(v.visible, 1) AS visible
            FROM workspaces w
            JOIN groups g ON g.id = w.group_id
            JOIN group_members m ON m.group_id = g.id
            LEFT JOIN workspace_visibility v
                ON v.workspace_id = w.id AND v.user_id = ?
            WHERE m.user_id = ? AND m.status = 'active' AND w.app = ?
            ORDER BY g.is_personal DESC, g.name, w.name
            """,
            (user_id, user_id, app),
        ).fetchall()


def set_workspace_visibility(user_id, workspace_id, visible):
    with connect() as con:
        con.execute(
            """
            INSERT INTO workspace_visibility (user_id, workspace_id, visible)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id, workspace_id) DO UPDATE SET visible=excluded.visible
            """,
            (user_id, workspace_id, int(visible)),
        )


def set_active_workspace(user_id, workspace_id):
    workspace = get_workspace(workspace_id)

    if not workspace:
        raise ValueError("no such workspace")

    if not require_active_member(user_id, workspace["group_id"]):
        raise PermissionError("not a member of this workspace's group")

    with connect() as con:
        con.execute(
            "UPDATE users SET active_workspace_id=? WHERE id=?",
            (workspace_id, user_id),
        )
