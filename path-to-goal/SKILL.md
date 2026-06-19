---
name: path-to-goal
description: A status update format for a goal-focused software-engineering culture of rapid, evidence-based technical decision-making. FKA unconfuse-me.
---

# Path to goal

With ELI10 clarity, summarize:

- goal, one sentence
- current status, 1-3 need to know sentences
- numbered path from start to goal with ✅ or ⬜
- in a new section, decisions you need from me to move forward, with well-articulated decision question in bold (<90 char), one line subtitle of why it's important (prefix "Why: "), followed by a table of lettered options to enable shorthand responses like `1a 2c 3b` or `yyn`. Highlight your recommended options with `★`. 

## Readability
  
- Separate decisions with a blank line
- Don't write "ELI10"
- No other emojis
- One liner items are < 88 chars
- For table of options use ( | Option | Tradeoffs) and for each tradeoff, prefix a bolded colored text symbols `(+)` for beneficial, `(-)` for negative, `(+/-)` if both, and double up for XXL e.g. `(++)`. Negligible tradeoffs are not tradeoffs.


## Shorthand responses

If user responds `2?` it means "I can't decide on Decision 2 with this level of info. Follow up with further detail on the situation and tradeoffs for this decision."

If user responds `3b?` it means "My gut sense is option B is best for Decision 3, but I don't have good enough information/data to be sure. Follow up with more detail on this decision and the tradeoffs with option B vs the other choices so I can confirm this choice."

If user responds `lgtm` it means "I accept all your recommendations"

If user responds `q`, it means launch your tool for collecting user input, like `AskUserQuestion` or `request_user_input` to collect  inputs to each of these decisions

End with a key of responses the user can provide:
- `1a 2b 3b` to choose
- `lgtm` accepts all ★
- `1?` more detail on 1
- `1b?` leaning 1B confirm after more info
- `q` use Question tool (exclude this line if none)
