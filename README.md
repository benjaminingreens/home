# home

HOME PROJECT SUMMARY

OVERVIEW

HOME is a local-first personal operating system built entirely around plain text. The core idea is that every piece of information—notes, tasks, journals, events, contacts, schedules, laws, projects, etc.—exists as ordinary human-readable text files. The web interface and command line are simply different ways of interacting with those files; the text itself is always the canonical source.

The philosophy is heavily inspired by Unix:

- Plain text first
- Local first
- Human-readable data
- No mandatory databases
- Minimal dependencies
- Fast and lightweight
- Long-term ownership of data
- Extensible through many small applications rather than one giant monolith

Think somewhere between Org Mode, Obsidian, DevonThink, Apple Notes, Notion and a Unix shell, except that everything ultimately remains editable with a normal text editor.

------------------------------------------------------------
ARCHITECTURE
------------------------------------------------------------

Current structure is roughly:

home/
    home.py
    core/
        app.py
        ...
    apps/
        ark/
        ...
    static/
    templates/
    data/

The project runs as a Flask application.

Each application lives inside apps/.

Applications register their own routes which HOME mounts automatically.

There is intentionally very little framework magic.

------------------------------------------------------------
GENERAL DESIGN PRINCIPLES
------------------------------------------------------------

Throughout development we've repeatedly agreed that the project should favour:

- simplicity over cleverness
- explicit code over abstraction
- plain text over databases
- local files over cloud storage
- backwards compatibility
- inspectable code
- minimal hidden state
- one obvious way to do something

Whenever designing a feature we ask:

"Does this naturally extend the existing model?"

rather than

"Can we bolt on another system?"

------------------------------------------------------------
ARK
------------------------------------------------------------

Ark is currently the largest application.

It exists both as:

- a command-line application
- a web application

Ark manages structured records stored inside plain text files.

Examples include:

- notes
- todos
- events
- journals
- routines
- laws
- schedules
- projects
- people

Each record contains metadata embedded inline.

Typical example:

todo: Buy milk {
    #shopping
    !2
    ~20260706T113027
    &uniqueid
}

The metadata syntax is intentionally compact because it is typed constantly.

------------------------------------------------------------
QUERY LANGUAGE
------------------------------------------------------------

Ark has a deliberately compact query syntax.

Examples:

evnt, today, --^, >>

evnt, week, --^, >>

These queries are intentionally terse because they are used dozens of times per day.

We discussed extending the existing time query parser to support arbitrary ranges (for example "next 44 days"), but concluded that any solution should fit naturally into the existing grammar rather than inventing an entirely new syntax.

------------------------------------------------------------
MULTI-RECORD EDITING
------------------------------------------------------------

One major recent piece of work was redesigning editing so multiple selected records can be modified simultaneously.

Originally there was an inconsistency between callers.

One call used:

apply_edit_to_records(\@matches, $op, @args);

while another used:

apply_edit_to_records(\@selected, \@operations);

The function itself expected an array reference of operations.

The intention is to standardise everything so all callers pass an operation array reference.

The editing routine itself groups selected records by source file so that:

selected records
    ↓
group by path
    ↓
load each file once
    ↓
apply every edit
    ↓
write file once

This avoids repeated file reads and writes.

------------------------------------------------------------
WEB APPLICATION
------------------------------------------------------------

Running

python3 home.py

starts the Flask development server.

Example:

Running on http://127.0.0.1:8000

Applications are mounted beneath the HOME interface.

------------------------------------------------------------
LONG-TERM APPLICATIONS
------------------------------------------------------------

HOME is intended to become a complete personal operating system containing many small applications that all share the same storage philosophy.

Examples include:

- Ark
- Notes
- Journal
- Calendar
- Contacts
- Finance
- Reading
- Theology
- Family
- Recipes
- Tea
- Games

Each application should feel independent but share the same underlying architecture and file format.

------------------------------------------------------------
OUR DEVELOPMENT STYLE
------------------------------------------------------------

During development we've repeatedly preferred:

- incremental improvements
- avoiding unnecessary rewrites
- keeping functions small
- reducing complexity whenever possible
- preserving compatibility
- making every file understandable months later

The guiding principle has been that HOME should remain something one person can understand completely.

------------------------------------------------------------
CURRENT STATE
------------------------------------------------------------

The project is currently an MVP.

The Flask shell works.

Ark is already functional.

Current work is focused on refining:

- querying
- editing
- UI
- additional applications

while keeping the architecture as small and maintainable as possible.

The long-term aim is for HOME to become a durable, local-first, plain-text operating system for life where every piece of information remains under the user's control.
