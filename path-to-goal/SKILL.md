---
name: path-to-goal
description: Use to clarify decisions or provide status updates in a goal-focused culture of rapid, evidence-based technical and strategic decision-making. Alias unconfuse-me.
---

# Path to goal

With ELI10 clarity, summarize:

- goal, one sentence
- current status, 1-3 need to know sentences
- in a new section, numbered path to goal from the start with ✅ or ⬜, including each numbered decision in its step when it becomes blocking
- in a new section, all the numbered decisions you need from me to move forward, as well-articulated one-line questions in bold followed by a table of lettered options in order to enable shorthand responses like `1a 2c 3b`. Highlight your recommended options with `★`. 
- If there are no decisions to make, say so clearly.

If there are decisions to make, remind the user of shorthand options they can respond with:

- `lgtm` accepts ★
- `1a 2b 3b` to choose (exclude if single decision)
- `1?` request more detail and confidence on decision 1 before deciding
- `q` launch built-in tool for user input (exclude if no tool)

## Readability

The value of this skill is condensing a lot of complex information into a form that is fast and efficient for a human to understand and respond to, so following these rules is important to achieve this.

- Never write "ELI10" but write all text in ELI10
- One liner items are < 88 chars
- Exempt from the char budgets are the anchor words required to correctly ask the decision to the user in the most effective way "Will I..." or "What is the next step for..." or "You need to decide on...".
- Decisions are always numbered, preceded by a blank line, and followed by a <64 char ELI8 subtitle of why it's important (prefix " - Why: "), then an optional " - Link: " only when a canonical URL (a github.com PR) lets the user make the decision. 
- For the table of options use ( # | Option | Tradeoffs) and for each tradeoff, prefix bolded symbols `(+)` for beneficial, `(-)` for negative, `(+/-)` if both good and bad, and increase count `(++)` sparingly only for notable differences (e.g. >1-2 orders of magnitude). Order a cell's tradeoffs descending, most positive `(++)` first down to most negative `(--)`.
- Negligible tradeoffs are not listed. 
- Differences in difficulty or effort for agent or wall clock time are out of scope as tradeoffs.
- If an option includes "I" or "you" the decision question must make it clear that "you" refers to the user e.g. "I (agent) will..."
- Prefix your path-to-goal response with a separator block — so the user can instantly spot where the report starts — then continue with the normal summary. The token-efficient block is a centered 1-col table, first row a line of `·` (middot) repeated to span one visual row — best-effort viewport width, **default 80** if unknown. Second row title: `PATH · TO · GOAL`. Then a blank line, and the summary begins (`**Goal:** ...`).
- No other emojis or icons

## Shorthand responses

Expanded instructions for some shorthand responses:

- If user responds `q`, it means launch your built-in tool for collecting user input, like `AskUserQuestion` or `request_user_input` or similar to collect user responses to each of these decisions. Follow the same decision numbers and formatting as closely as your built-in tool allows.
- If user responds `1?` it means "I can't decide on Decision 1 with the provided level of info. Follow up with the next level of detail and 3x char budgets and revisit this decision singularly next. Do not consume chars on duplicative points, focus on providing the single best description of each point once."
