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
- Every commit must add a new entry to the top of `CHANGELOG.md` (newest-first).
- Format: `- **YYYY-MM-DD** — <one-sentence description of what changed and why>`
- Never delete old entries.
- The entry should describe the change from a user/operator perspective, not an implementation perspective (e.g. "Added support for parsing Snowflake 10-Q filings" not "Added SnowflakeExtractor class").

### Known Limitations
- If a known limitation was resolved, remove or update it from the **Known Limitations** section.
- If a change introduces a new limitation, add it.

The README should always be an accurate, up-to-date description of what the code currently does — not what it used to do.

---

## Experimental Features

Not every idea belongs in the production surface of the app. Use the **Experimental Blueprint** (`experimental/`) to build and iterate on features that are not yet ready to be treated as first-class parts of the product.

### What belongs in `experimental/`

A feature goes in `experimental/` if any of the following are true:

- It uses hardcoded or mock data instead of a live backend
- Its design or scope is still being validated (layout, workflow, data model)
- It has no tests and is not yet referenced by any production code path
- It was built to explore an idea, not to ship it

### What does NOT belong in `experimental/`

A feature goes directly into the main app (a regular Flask route + template in `templates/`) if it:

- Reads from the live database or a verified data pipeline
- Is used by external or end users
- Has been reviewed, tested, and confirmed to be the right thing to build

### File structure

```
experimental/
  __init__.py       # Flask Blueprint definition (url_prefix="/experimental")
  routes.py         # All experimental route handlers

templates/
  experimental/
    themes.html     # Example: News page (mock data, prototype UI)
    <feature>.html  # Add new experimental templates here
```

### How to add a new experimental feature

1. Add a route function to `experimental/routes.py`:
   ```python
   @bp.route("/my-feature")
   def my_feature():
       return render_template("experimental/my_feature.html")
   ```
2. Create the template at `templates/experimental/my_feature.html`.
3. That's it — the Blueprint is already registered. Visit `/experimental/my-feature`.

Do NOT:
- Add the route to `app.py` directly
- Put the template in `templates/` (top level)
- Reference it from any production nav bar, link, or API without promoting it first

### Enabling and disabling

The Blueprint is mounted by default (`EXPERIMENTAL=1`). Set `EXPERIMENTAL=0` to disable all experimental routes — useful for production deployments or static builds where these pages should not be accessible.

```bash
EXPERIMENTAL=0 python app.py   # experimental routes disabled
python app.py                  # experimental routes enabled (default)
```

The `experimental` flag is also injected into every Jinja template via the context processor, so templates can conditionally show links:

```html
{% if experimental %}<a href="/experimental/themes">News</a>{% endif %}
```

### How to promote a feature from experimental to production

When a feature is ready to graduate:

1. Move its template from `templates/experimental/<name>.html` → `templates/<name>.html`
2. Move its route from `experimental/routes.py` → a new route in `app.py`
3. Update any nav bar links from `/experimental/<name>` → `/<name>` (remove the `{% if experimental %}` guard)
4. If it used mock/hardcoded data, wire it to the real backend first
5. Delete the old experimental route and template
6. Update `README.md` (Project Structure, How It Works), `CHANGELOG.md`, and this file if the pattern itself changed
