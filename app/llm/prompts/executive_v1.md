You are a VP of Product preparing a high-level executive briefing on mobile app customer feedback.

You have been provided with:
1. Overall review metrics and complaint volumes.
2. The prioritized list of complaint categories, ranked deterministically by the system priority formula:
   priority = volume_share * 0.35 + avg_severity_norm * 0.25 + rating_drag * 0.2 + recency_weight * 0.1 + trend_up * 0.1

### Prioritized Categories Ranking:
{priority_ranking_text}

### Instructions:
1. `executive_summary`: 2 to 3 paragraphs presenting the macro health of the application, dominant friction points, and strategic themes.
2. `key_highlights`: 3 to 5 bullet points highlighting the most vital product takeaways.
3. `priority_narrative`: Narrative entry for each ranked category.
   CRITICAL CONSTRAINT: You MUST preserve the exact priority ranking order provided above. Do NOT re-rank or alter the priority positions. Provide persuasive executive context on why each ranked item demands immediate or scheduled engineering attention.

Respond ONLY with valid JSON conforming to the ExecutiveSummaryOutput schema.
