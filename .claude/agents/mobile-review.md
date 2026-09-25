---
name: mobile-review
description: Review and fix the mobile experience of the earnings dashboard. Starts the dev server, opens each page at 375px viewport, screenshots every key view, checks for overflow, tiny touch targets, unreadable text, and layout breakage, then applies fixes. Use whenever the user asks to check mobile responsiveness, test on mobile, or verify the site scales correctly.
---

# Mobile Experience Review

## What This Skill Does

Audits every page of the earnings dashboard at a 375px mobile viewport (iPhone SE baseline), identifies layout and usability defects, and applies fixes to the source templates. Then re-checks to confirm each fix landed.

---

## Pages to Review

| Page | URL | Key things to check |
|------|-----|---------------------|
| Earnings | `http://localhost:5001/` | Ticker buttons wrap cleanly, chart scales to container, table scrolls horizontally inside its own wrapper |
| News | `http://localhost:5001/news` | Carousel nav buttons reachable, sentiment chart fits, headline cards don't overflow |

---

## Execution Steps

### Step 1 — Start the dev server

Use `preview_start` with `{name: "earnings-dashboard"}` to open the app. If the server is already running, skip this step.

### Step 2 — Set mobile viewport

Use `resize_window` with `{preset: "mobile"}` on the active tab. This sets 375×812px and enables touch emulation.

### Step 3 — Screenshot each page

Navigate to each page in the table above and take a `screenshot` immediately after load. Do not judge yet — collect all screenshots first.

### Step 4 — Audit each screenshot against this checklist

For every screenshot, check every item. Mark each ✅ (pass) or ❌ (fail with description):

**Layout**
- [ ] No horizontal scrollbar on `<body>` (page body never scrolls sideways)
- [ ] Content stays within 375px; no element clips off the right edge
- [ ] Side gutters ≥ 16px on both sides
- [ ] Sections stack vertically (no multi-column layout that breaks at narrow width)

**Typography**
- [ ] Body text ≥ 14px
- [ ] No text is truncated or clipped inside its container
- [ ] Headings use `text-wrap: balance` or wrap naturally

**Touch targets**
- [ ] All buttons and links have a tap area ≥ 44×44px (check with `javascript_tool`: `el.getBoundingClientRect()`)
- [ ] Carousel PREV/NEXT buttons are reachable without zooming

**Charts and SVGs**
- [ ] Charts measure their container at render time (not hardcoded pixel widths)
- [ ] SVG viewBox is set; chart does not overflow its wrapper
- [ ] Axis labels are legible (≥ 11px)

**Tables**
- [ ] Wide tables have `overflow-x: auto` on their wrapper — table scrolls, page body does not
- [ ] Table text is legible (≥ 12px)

**Images and media**
- [ ] `max-width: 100%` on all `<img>` tags

### Step 5 — Fix all failures

For each ❌ item, edit the relevant template (`templates/earnings.html` or `templates/news.html`) to fix the issue. Common fixes:

| Problem | Fix |
|---------|-----|
| Body scrolls horizontally | Add `overflow-x: hidden` to `body`, or find the element with a fixed `width` wider than 375px and replace with `max-width: 100%` |
| Side gutter missing | Add `padding-inline: 16px` to the outer wrapper |
| Multi-column layout breaks | Add `@media (max-width: 600px) { .row { flex-direction: column; } }` |
| Button too small | Add `min-height: 44px; min-width: 44px; padding: 10px 16px` |
| Chart hardcoded width | Replace `width={N}` or `style="width:Npx"` with a container measurement in JS: `const w = el.clientWidth` at render time |
| Table overflows | Wrap table in `<div style="overflow-x:auto">` |
| Text too small | Bump `font-size` to at least `14px` for body, `12px` for table cells |

### Step 6 — Re-screenshot after fixes

Reload the page (`navigate` to the same URL) and take a new screenshot for each page that had failures. Confirm every previously-failing item now passes.

### Step 7 — Check dark mode at mobile

Use `resize_window` with `{colorScheme: "dark"}` and take one screenshot of each page. Confirm:
- [ ] Text is readable (no dark-on-dark or light-on-light)
- [ ] Chart lines and sentiment pills are visible
- [ ] No color is hardcoded in a way that only works in one theme

### Step 8 — Reset viewport

Use `resize_window` with `{preset: "desktop"}` to return the tab to its normal size.

### Step 9 — Report

List every item that was fixed, with before/after descriptions. List any items that passed without changes. If anything could not be fixed automatically (e.g. requires a data or logic change), call it out explicitly.

---

## Common Patterns in This Codebase

- Charts in `earnings.html` and `news.html` use inline SVG built in JavaScript. Look for a `buildChart()` or `renderChart()` function that sets a hardcoded `width` — replace it with `container.clientWidth`.
- The chart resize handler should already exist (added in a prior session); verify it fires on `window.resize`.
- The nav bar is sticky — confirm it does not cover content on scroll at mobile widths.
- The carousel in `news.html` uses swipe events — verify the touch area spans the full card width.
