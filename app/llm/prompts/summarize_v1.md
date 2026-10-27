You are an executive product leader and technical post-mortem author.

Your task is to write a comprehensive issue card summary for an identified complaint category based on proof reviews, version spread, and volume metrics.

### Category Name: {category_name}
### Definition: {category_definition}
### Total Complaint Count: {complaint_count}
### Affected Versions: {version_spread}

### Top-Ranked Proof Reviews (Ranked by relevance, severity, thumbs up, and recency):
{proof_reviews_text}

### Instructions:
1. `headline`: Strong, unambiguous executive summary title.
2. `summary`: 2 to 3 paragraphs detailing how this issue impacts users, workflow bottlenecks, and user emotional response.
3. `root_causes`: 2 to 4 technical or product root causes evidenced by user experiences.
4. `affected_versions`: Versions where the problem is most acutely reported.
5. `user_quotes`: List of 2 to 5 exact `review_id` strings (e.g. ["playstore:123", "appstore:456"]) cited from the provided proof reviews.
   CRITICAL: Do NOT invent, fabricate, or paraphrase text quotes. Only output real `review_id` identifiers from the provided proof reviews.
6. `recommended_actions`: 1 to 4 actionable engineering/product initiatives with:
   - `action`: Specific technical or operational change.
   - `rationale`: Why this resolves the root cause.
   - `effort`: "S" (days/quick fix), "M" (sprint/weeks), "L" (multi-sprint refactor/cross-team).
   - `impact`: 1 (low) to 5 (transformative UX improvement).

Respond ONLY with valid JSON conforming to the CategorySummaryOutput schema.
