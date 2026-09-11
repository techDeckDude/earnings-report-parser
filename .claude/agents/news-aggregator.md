---
name: news-aggregator
description: Fetch and analyze AI stock market theme headlines from the past 7 days. Returns structured JSON with headline text, news source, direct article URL, mentioned stocks, and a 5-level sentiment score (−2 to +2) based on confirmed or potential revenue/earnings impact. Includes a mandatory self-critic pass to verify scores, URLs, and tickers before output. Use this skill whenever the user types "run news-aggregator prompt" or asks for current AI stock market news, recent AI company funding announcements, or AI-related market movements.
---

# AI Stock Market News Aggregator

## What This Skill Does

Fetches the latest AI stock market theme headlines from the past 7 days and returns them in a structured JSON format with:
- **headline**: The news headline text
- **source**: News source/publisher
- **url**: Direct link to the article (`null` if no verifiable source found)
- **url_verified**: `true` if URL came from a listed search result matching this headline; `false` if URL is a general page or could not be confirmed after a follow-up search
- **stocks_mentioned**: Array of stock tickers mentioned in the article
- **sentiment_score**: Integer from -2 to +2 (see scoring guidelines below)
- **sentiment_label**: Human-readable label for the score
- **summary**: Brief explanation of the revenue/earnings impact

## How to Use

When triggered by "run news-aggregator prompt", this skill will:

1. Search for AI stock market news from the past 7 days
2. Parse results to identify:
   - Specific stocks mentioned (with tickers)
   - The revenue or earnings impact on mentioned companies using the 5-level sentiment scale
3. Return all results as a JSON array for easy processing

## Sentiment Scoring Guidelines

Score each headline strictly on its **confirmed or potential impact to company revenue or earnings**:

| Score | Label | Criteria |
|-------|-------|----------|
| **+2** | Very Positive | Confirmed upside — beat earnings, raised guidance, closed a large contract, reported revenue growth |
| **+1** | Positive | Potential upside — funding round, new partnership, product launch, expansion into a new market |
| **0** | Neutral | No direct revenue or earnings impact — research papers, personnel changes, industry commentary |
| **-1** | Negative | Potential downside — regulatory investigation opened, competitive threat emerged, product delayed |
| **-2** | Very Negative | Confirmed downside — missed earnings, lowered guidance, lost a major contract, revenue decline reported |

**Key distinctions:**
- A funding announcement is **+1** (potential), not +2 — money raised is not revenue
- A closed enterprise deal with disclosed contract value is **+2** (confirmed)
- A regulatory fine with a known amount is **-2** (confirmed); an ongoing investigation is **-1** (potential)
- Macro market moves (index up/down) with no company-specific impact are **0**
- Do not default positive — assign the score the evidence actually supports

## Output Format

```json
{
  "timestamp": "2026-09-11T12:00:00Z",
  "period": "past 7 days",
  "headlines": [
    {
      "headline": "Mistral raises €3B in Europe's biggest tech round, led by Samsung",
      "source": "Bloomberg",
      "url": "https://www.bloomberg.com/news/articles/2026-09-08/mistral-raises-3b",
      "url_verified": true,
      "stocks_mentioned": ["MSFT", "AMZN"],
      "sentiment_score": 1,
      "sentiment_label": "Positive",
      "summary": "Large funding round signals continued investor confidence but does not directly confirm revenue impact"
    },
    {
      "headline": "Nvidia beats Q3 estimates; raises full-year guidance by 12%",
      "source": "CNBC",
      "url": null,
      "url_verified": false,
      "stocks_mentioned": ["NVDA"],
      "sentiment_score": 2,
      "sentiment_label": "Very Positive",
      "summary": "Confirmed earnings beat and raised guidance represent direct upside to revenue and earnings — source not verified, treat with caution"
    }
  ],
  "summary_stats": {
    "total_headlines": 2,
    "score_distribution": { "-2": 0, "-1": 0, "0": 0, "1": 1, "2": 1 },
    "weighted_sentiment": 1.5,
    "net_sentiment_label": "Positive"
  }
}
```

## Execution Steps

### Step 1 — Search
Run 2–3 web searches to gather headlines:
- "AI stock market news this week [current month year]"
- "AI companies earnings guidance [current month year]"
- "AI funding announcements deals [current month year]"

### Step 2 — Draft JSON
For each headline found, produce a draft entry with all fields filled in. Note whether the URL came directly from a listed search result link, or whether the fact came only from the search tool's synthesized summary text.

### Step 3 — URL Verification (mandatory)
For every headline whose URL is uncertain (fact came from synthesized summary, or URL seems like a general page rather than the specific article), run a targeted follow-up search:
- Query format: `"[key phrase from headline]" site:cnbc.com OR site:bloomberg.com OR site:reuters.com OR site:wsj.com`
- If the follow-up search returns a direct article link → update `url` with that link
- If no direct article link is found after one targeted search → set `"url": null` and set `"url_verified": false`
- If the URL came from a listed search result link that clearly matches this headline → set `"url_verified": true`

### Step 4 — Critic Pass (mandatory before output)
Review every draft entry:

**URL check**
- Was this URL reused from a different headline in the same batch? → set `url: null`, `url_verified: false`
- Does the URL point to a general page (live blog, weekly recap, aggregator) rather than the specific article? → note this in `source`, keep the URL but set `url_verified: false`

**Score check — ask in order, stop at the first "yes"**
1. Does the article report a confirmed outcome (beat/miss earnings, raised/lowered guidance, closed contract, reported revenue growth/decline)? → score ±2
2. Does the article describe a potential future impact (funding, partnership, investigation opened, product launch, competitive threat)? → score ±1
3. Is this macro commentary, personnel news, or research with no company-specific revenue impact? → score 0
- If your draft score is higher than what this chain supports → downgrade it.
- Never assign +1 just because the story is broadly positive for AI.

**Stock ticker check**
- Is each listed ticker actually named in the article?
- If a ticker was inferred but not explicitly mentioned → remove it.

**Summary check**
- Does the summary explicitly state whether the impact is *confirmed* or *potential*?
- If not → rewrite it to make this clear.

### Step 5 — Output corrected final JSON

## Implementation Notes

- Extract stock tickers from news content (look for ticker symbols in parentheses or context)
- Always attempt to verify URLs via a targeted follow-up search before accepting or rejecting them
- Never reuse a URL from one headline for a different headline in the same batch
- `url_verified: false` is the honest signal that a headline came from synthesized search summary text rather than a confirmed article link — the user can decide whether to trust it
- `weighted_sentiment` in summary_stats is the mean score across all headlines (round to 1 decimal)
- `net_sentiment_label` maps the weighted average: ≥1.5 → "Very Positive", ≥0.5 → "Positive", >-0.5 → "Neutral", >-1.5 → "Negative", else → "Very Negative"
