import subprocess

from .config import WORKSPACES, GIT_ROOT, GIT_HOST, GIT_SSH_USER


def root(group_slug, app, workspace_name):

    return WORKSPACES / group_slug / app / workspace_name


def path(group_slug, app, workspace_name):
    """Where an app's user-facing data actually lives on disk: not the
    workspace root itself, but a folder inside it named after the app -
    so if a workspace root is ever shared by more than one app's data,
    each app's files stay self-namespaced instead of getting dumped
    together in one generically-named bucket."""

    return root(group_slug, app, workspace_name) / app


def bare_repo_path(group_slug, app, workspace_name):

    return GIT_ROOT / group_slug / app / f"{workspace_name}.git"


def has_bare_repo(group_slug, app, workspace_name):

    return bare_repo_path(group_slug, app, workspace_name).exists()


def current_remote(group_slug, app, workspace_name):
    """The workspace's actual configured origin, if it has one. Prefer
    this over remote_url() for an already-linked workspace: it isn't
    necessarily one HOME provisioned itself (e.g. set up by hand), so it
    may not live at the conventional bare_repo_path()."""

    workspace = root(group_slug, app, workspace_name)

    result = subprocess.run(
        ["git", "-C", str(workspace), "remote", "get-url", "origin"],
        capture_output=True,
        text=True,
    )

    return result.stdout.strip() or None


def remote_url(group_slug, app, workspace_name):

    host = GIT_HOST or "<your-server-host>"
    ssh_user = GIT_SSH_USER or "<ssh-user>"

    return f"ssh://{ssh_user}@{host}{bare_repo_path(group_slug, app, workspace_name)}"


def _git(*args, cwd):

    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
    )


def start_link(group_slug, app, workspace_name):
    """Step 1 of linking an existing workspace: create an empty bare repo
    on the server for the user to push into from wherever their existing
    workspace already lives."""

    bare = bare_repo_path(group_slug, app, workspace_name)
    bare.parent.mkdir(parents=True, exist_ok=True)

    subprocess.run(["git", "init", "--bare", str(bare)], check=True)
    subprocess.run(
        ["git", "-C", str(bare), "symbolic-ref", "HEAD", "refs/heads/main"],
        check=True,
    )

    return remote_url(group_slug, app, workspace_name)


def finish_link(group_slug, app, workspace_name):
    """Step 2: once the user has pushed to the bare repo, clone it into
    the live workspace path. The pushed content is the app's raw external
    data (e.g. note/todo/evnt at the top level) - clone it into the app's
    own data folder first, same shape as always, then hoist .git up to the
    workspace root so this workspace's git scope matches every other
    workspace's (see hoist_git_to_root)."""

    bare = bare_repo_path(group_slug, app, workspace_name)
    data_dir = path(group_slug, app, workspace_name)

    result = subprocess.run(
        ["git", "-C", str(bare), "show-ref", "--heads"],
        capture_output=True,
        text=True,
    )

    if not result.stdout.strip():
        raise ValueError("nothing has been pushed to the server yet")

    data_dir.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "clone", str(bare), str(data_dir)], check=True)

    hoist_git_to_root(group_slug, app, workspace_name)


def enable_git(group_slug, app, workspace_name):
    """Wire up git backing for a workspace that already exists on the
    server but isn't linked to anywhere else yet, so a local copy can be
    cloned down elsewhere. Rooted at the workspace root (not just the
    app's own data folder), so anything else sitting there - other apps'
    data, legacy content - is in scope from the very first commit."""

    workspace = root(group_slug, app, workspace_name)

    if (workspace / ".git").exists():
        raise ValueError("already git-linked")

    bare = bare_repo_path(group_slug, app, workspace_name)
    bare.parent.mkdir(parents=True, exist_ok=True)

    subprocess.run(["git", "init", "--bare", str(bare)], check=True)
    subprocess.run(
        ["git", "-C", str(bare), "symbolic-ref", "HEAD", "refs/heads/main"],
        check=True,
    )

    _git("init", cwd=workspace)
    _git("checkout", "-b", "main", cwd=workspace)
    _git("remote", "add", "origin", str(bare), cwd=workspace)
    _git("add", "-A", cwd=workspace)
    _git("commit", "-m", "initial import", cwd=workspace)
    _git("push", "-u", "origin", "main", cwd=workspace)

    return remote_url(group_slug, app, workspace_name)


def hoist_git_to_root(group_slug, app, workspace_name):
    """Move a .git that lives at <root>/<app>/ up to <root>/ itself,
    widening git's scope from just the app's own data folder to the whole
    workspace root - so anything sitting beside <app>/ (other apps' data,
    legacy content that predates this convention) gets synced too,
    instead of being silently left out.

    The index still lists paths relative to the old root (e.g.
    "note/foo.md"), so one add-A/commit re-adds everything relative to the
    new root (e.g. "<app>/note/foo.md") - git represents this as a rename
    when the content matches, so no history is lost, just one extra
    "moved under <app>/" commit. Best-effort push: offline is fine, the
    next auto_sync picks it up.

    No-ops if there's nothing to hoist (already at the root, or never
    git-linked at all) - safe to call unconditionally, including on every
    boot for legacy workspaces (see core.storage's migration)."""

    workspace_root = root(group_slug, app, workspace_name)
    data_dir = workspace_root / app
    old_git = data_dir / ".git"
    new_git = workspace_root / ".git"

    if new_git.exists() or not old_git.exists():
        return

    old_git.rename(new_git)

    _git("add", "-A", cwd=workspace_root)
    _git("commit", "-m", "restructure: widen git scope to the workspace root", cwd=workspace_root)
    _git("push", cwd=workspace_root)
