"""
Federation is not implemented. This module exists to hold the design notes
for it, so the shape of the eventual work is written down somewhere close
to the code rather than living only in a conversation.

The idea: two independently-run HOME servers agree to make some of their
users visible to each other, so a group on one server could invite a user
who only has an account on the other. `users.visibility` already has a
'federated' value users can opt into (see core/db.py, core/users.py) and
`federated_servers` (core/db.py) has a place to record peer servers - but
neither does anything yet. Nothing here signs a request, calls a peer, or
trusts an incoming one.

Sketch of what actually implementing this would need:

1. Server identity. Each server generates a keypair at install time
   (probably alongside the existing HOME_SECRET_KEY generation in the
   `install` script). The public half is this server's identity when
   talking to peers.

2. Connecting two servers. Manual, admin-to-admin, out-of-band exchange -
   the same pattern already used for the git remote URL flow in
   core/workspaces.py (one side generates something, the other side pastes
   it in). Concretely: each admin's Settings page shows their server's
   public identity token; pasting the other server's token into
   "connected servers" creates a `federated_servers` row with
   status='pending' until the other side reciprocates, then 'trusted'.

3. Discovery. A `GET /federation/whoami` endpoint (unauthenticated, but
   only ever meaningful between servers that have exchanged identity
   tokens) returning this server's `visibility='federated'` users, signed
   with the server's private key so a peer can verify the response wasn't
   tampered with in transit.

4. Federated group membership. `group_members` only has a local `user_id`
   today. A federated invite would need something like nullable
   `remote_host` / `remote_username` columns alongside it, since the
   invitee has no row in this server's `users` table at all.

5. Cross-server actions. Anything that needs to actually move data between
   servers (syncing a shared workspace with a federated member, for
   example) can't ride on a browser session the way everything else in
   this app does - it needs signed, server-to-server requests, verified
   against the keypair from (1).

None of this is wired up. `FEDERATION_ENABLED` stays False until it is.
"""

FEDERATION_ENABLED = False
