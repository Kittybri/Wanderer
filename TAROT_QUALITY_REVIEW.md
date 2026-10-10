# Wanderer tarot-quality repair (review-only)

Source branch: `fix/wanderer-tarot-reading-quality`, based on `3b998a71b3f3d75c14b7eeef00932e31c60569a5`.

Screenshot observations:
- Main 3-card interpretation and clarifier visibly ended mid-sentence.
- The reading gave lore without explaining why the cards answered the question.
- Default detail was Brief, which should still yield a complete response.

Code findings:
1. Tarot generation did not inspect provider `finish_reason` and accepted unfinished text.
2. Three-card and yes/no formatting clipped long text to one Discord message, potentially dropping conclusions.
3. The guidance did not explicitly require answering the question or translating lore for newcomers.
4. Clarifier/explanation/followup output could be truncated by a fixed 1950-character slice.

Repair:
- Reject truncated/incomplete results, retry at most once with a bounded higher token budget, and use an existing deterministic fallback when generation remains incomplete.
- Paginate entire three-card/yes-no and followup/clarifier text without silently discarding content.
- Improve question-focused prompts with plain-language explanations; treat past-life readings as symbolic storytelling, not verified reincarnation.
- Slightly increase tarot response budgets, preserving existing Brief/Detailed settings, positions, 78 card artworks, history, permissions and command surface.
- Add focused isolated regression tests.

Validation not yet run in a complete repository environment; no claims of Discord live testing. Review this draft and run full tarot/preservation suites before deployment. Voice and Scaramouche are untouched. No release or main merges.
