# Project Rules for AI Agents

## README Updates (Required Before Every Commit)

Before creating any git commit, you MUST update `README.md` to reflect the changes being committed. This is not optional.

### Project Structure
- If a new file or module was added, add it to the **Project Structure** section with a one-line description of its purpose.
- If a file was removed or renamed, update the structure to match.

### How It Works
- If an existing feature was changed or extended, update the relevant section in **How It Works** to reflect the new behavior.
- If a new feature was added (e.g. a new endpoint, CLI flag, visualization, data model), add a description under **How It Works**, creating a subsection if needed.

### Design Patterns & Infrastructure
- If a new design pattern is introduced (e.g. Strategy, Repository, Factory, Observer), add it to the **Design Patterns & Infrastructure** section with a one-line description and the files where it is applied.
- If an existing pattern is extended (e.g. a new extractor implementation, a new DB backend), update the relevant entry.
- If infrastructure changes (e.g. new cloud service, new env var, new dependency), update the **Infrastructure** subsection.

### Changelog
- Every commit must add a new entry to the **Changelog** section at the bottom of the README.
- Format: `- **YYYY-MM-DD** — <one-sentence description of what changed and why>`
- Entries are newest-first. Never delete old entries.
- The entry should describe the change from a user/operator perspective, not an implementation perspective (e.g. "Added support for parsing Snowflake 10-Q filings" not "Added SnowflakeExtractor class").

### Known Limitations
- If a known limitation was resolved, remove or update it from the **Known Limitations** section.
- If a change introduces a new limitation, add it.

The README should always be an accurate, up-to-date description of what the code currently does — not what it used to do.
