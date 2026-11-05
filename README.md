# Caring Contact Resource Finder

A password-protected website where Caring Contact volunteers search New Jersey mental health and support resources during a call. Staff edit everything from a Manage panel.

Started 2026-09-25 as a demo for Caring Contact's executive director. The design follows NYC Mental Health Connect (https://mentalhealthconnect.nyc.gov/home).

## Passwords

There are two shared passwords, both stored as Disco environment variables and never in this repo:

| Variable | What it opens |
| --- | --- |
| `VOLUNTEER_PASSWORD` | Search and read everything |
| `ADMIN_PASSWORD` | The same, plus the Manage panel (add, edit, hide and delete resources, categories, notices and page text) |
| `SESSION_SECRET` | A long random string that signs the sign-in cookie |
| `ANTHROPIC_API_KEY` | Switches on the staff assistant (below). Without it the chat box says it isn't switched on. |
| `ASSISTANT_MODEL` | Optional. The Claude model the assistant uses; defaults to `claude-opus-5-5`. |

Every route except `/login` and `/healthz` needs one of the passwords. After 5 wrong tries, an address is locked out for 15 minutes. If neither password is set, nobody can sign in.

## Staff assistant

The Manage panel (staff password only) has an "Ask Claude to make a change" box. Staff type a change in plain words and Claude makes it through five tools in `chat.py` that can only search, read, save and delete this site's own records (resources, categories, notices, page text, the "Available to add" list). It has no web access and cannot touch the code, the layout, the passwords or anything outside the database.

- Every change it makes is logged with the earlier version (`changes` table), and each reply has an **Undo these changes** button.
- It must ask before deleting anything or changing more than 10 records, prefers hiding to deleting, never invents phone numbers or websites, and marks anything not supplied by staff as a suggestion.
- Conversations are stored in the `chats` table, so a page reload starts a fresh conversation but nothing is lost from the record.
- Each message costs a few cents of Anthropic API usage, billed to whoever owns the API key.

## Data

- The data is stored in SQLite at `$DATA_DIR/resources.db`. On Disco that's the `/data` volume, which is declared inside the `web` service in `disco.json`.
- `seed_data.json` holds the 134 starting resources from Caring Contact's documents (resource guide 5/19/2026, PES list 1/19/2026, EISS list 4/21/2025, the CCBHC list and the SNAP notice). It loads **only into an empty database**, so a redeploy never overwrites staff edits.
- Entries with `"suggestion": true` were added by Claude and are not from Caring Contact's documents. They show a "Suggestion: not yet verified" label until staff untick it.
- Caring Contact's rule is kept as a notice: volunteers never call PES, and PES always arrives with the police.

## Backups and moving the site

Staff can press **Download a backup of everything** on the Manage panel. The file has the same shape as `seed_data.json`. To start a new copy of the site with that content, set `SEED_FILE=/path/to/backup.json` before the site's first start with an empty data folder; it loads the backup instead of the starting data and skips the one-time updates the backup already has.

## Run and test

```
uv sync
uv run pytest -q
DATA_DIR=./data VOLUNTEER_PASSWORD=v ADMIN_PASSWORD=a COOKIE_INSECURE=1 uv run python app.py
```

`bash hooks/install.sh` installs the pre-commit hook, which runs the tests.

## Deploy

Deploys run on Disco. A push to `main` deploys automatically. The health check is `/healthz`.
