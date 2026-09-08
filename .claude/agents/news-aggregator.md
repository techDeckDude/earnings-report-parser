---
name: news-aggregator
description: Fetch and analyze AI stock market theme headlines from the past 24 hours. Returns structured JSON with headline text, news source, mentioned stocks, and bullish/bearish sentiment. Use this skill whenever the user types "run news-aggregator prompt" or asks for current AI stock market news, recent AI company funding announcements, or AI-related market movements.
---

# AI Stock Market News Aggregator

## What This Skill Does

Fetches the latest AI stock market theme headlines from the past 24 hours and returns them in a structured JSON format with:
- **headline**: The news headline text
- **source**: News source/publisher
- **stocks_mentioned**: Array of stock tickers mentioned in the article
- **sentiment**: Bullish or Bearish (assessment of financial impact on the AI theme)
- **summary**: Brief explanation of why it's bullish or bearish

## How to Use

When triggered by "run news-aggregator prompt", this skill will:

1. Search for AI stock market news from the past 24 hours
2. Parse results to identify:
   - Specific stocks mentioned (with tickers)
   - Whether the news is positive (Bullish) or negative (Bearish) for AI investments
3. Return all results as a JSON array for easy processing

## Sentiment Scoring Guidelines

**Bullish indicators:**
- Funding announcements or capital raises
- Positive earnings reports or guidance raises
- New partnerships or technology breakthroughs
- M&A activity, IPOs, or positive regulatory news
- Stock price rallies

**Bearish indicators:**
- Layoffs or downsizing announcements
- Regulatory concerns or restrictions
- Failed products or missed targets
- Downward guidance revisions
- Stock price declines or market sell-offs

## Output Format

```json
{
  "timestamp": "2026-09-08T12:00:00Z",
  "headlines": [
    {
      "headline": "Mistral raises €3B in Europe's biggest tech round, led by Samsung",
      "source": "Bloomberg",
      "stocks_mentioned": ["MSFT", "AMZN", "ASML"],
      "sentiment": "Bullish",
      "summary": "Major funding round demonstrates continued investor confidence in European AI development"
    },
    {
      "headline": "Forus lands $150M at $3B for AI prescription-fulfillment platform",
      "source": "Bloomberg",
      "stocks_mentioned": [],
      "sentiment": "Bullish",
      "summary": "Successful Series C financing for healthcare AI startup indicates strong demand for AI applications"
    }
  ],
  "summary_stats": {
    "total_headlines": 2,
    "bullish_count": 2,
    "bearish_count": 0,
    "net_sentiment": "Strongly Bullish"
  }
}
```

## Implementation Notes

- Use `web_search` tool with query like: "AI stock market news today" or "AI companies funding announcements September 2026"
- Extract stock tickers from news content (look for ticker symbols in parentheses or context)
- For stocks mentioned but not directly in headline, include them if they're central to the story
- If stocks are mentioned but not explicitly listed, use context to infer relevant tickers
- Assess sentiment based on the guidelines above; default to Bullish for neutral/informational stories about AI growth
