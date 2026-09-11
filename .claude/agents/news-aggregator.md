---
name: news-aggregator
description: Fetch and analyze AI stock market theme headlines from the past 7 days. Returns structured JSON with headline text, news source, direct article URL, mentioned stocks, and a 5-level sentiment score (−2 to +2) based on confirmed or potential revenue/earnings impact. Includes a mandatory self-critic pass to verify scores, URLs, and tickers before output. Use this skill whenever the user types "run news-aggregator prompt" or asks for current AI stock market news, recent AI company funding announcements, or AI-related market movements.
---

# AI Stock Market News Aggregator

## What This Skill Does

Fetches the latest AI stock market theme headlines from the past 7 days and returns them in a structured JSON format with:
- **headline**: The news headline text
- **source**: News source/publisher
- **url**: Direct link to the article
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
      "url": "https://www.bloomberg.com/news/articles/...",
      "stocks_mentioned": ["MSFT", "AMZN"],
      "sentiment_score": 1,
      "sentiment_label": "Positive",
      "summary": "Large funding round signals continued investor confidence but does not directly confirm revenue impact"
    },
    {
      "headline": "Nvidia beats Q3 estimates; raises full-year guidance by 12%",
      "source": "CNBC",
      "url": "https://www.cnbc.com/2026/09/11/nvidia-earnings...",
      "stocks_mentioned": ["NVDA"],
      "sentiment_score": 2,
      "sentiment_label": "Very Positive",
      "summary": "Confirmed earnings beat and raised guidance represent direct upside to revenue and earnings"
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
For each headline found, produce a draft entry with all fields filled in.

### Step 3 — Critic Pass (mandatory before output)
Before returning results, review every draft entry by answering these questions explicitly in your internal reasoning:

**URL check**
- Is this URL the actual source for this specific headline?
- Was this URL reused from a different headline in the same batch?
- If yes to either → set `"url": null` rather than carry a wrong link.

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

### Step 4 — Output corrected final JSON

## Implementation Notes

- Extract stock tickers from news content (look for ticker symbols in parentheses or context)
- Always include the direct article URL from the search result — never reuse a URL from another headline in the same batch
- If a URL is unavailable or uncertain, set `"url": null`
- `weighted_sentiment` in summary_stats is the mean score across all headlines (round to 1 decimal)
- `net_sentiment_label` maps the weighted average: ≥1.5 → "Very Positive", ≥0.5 → "Positive", >-0.5 → "Neutral", >-1.5 → "Negative", else → "Very Negative"
