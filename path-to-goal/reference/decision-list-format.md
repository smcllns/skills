# Decision options — monospace aligned-list format

An alternative to the default `# | Option | Tradeoffs` markdown table (see `SKILL.md`).
Use it when each tradeoff should sit on its own line, vertically aligned for fast
scanning. The default table is usually better; reach for this only when per-line
tradeoffs genuinely aid review.

## Why it must be a fenced code block

Terminal markdown renderers collapse leading spaces in prose and ignore `<br>`
inside table cells — so neither can both break tradeoffs onto separate lines AND
align them into columns. A fenced code block is the only construct that preserves
exact whitespace and uses a fixed-width font.

The cost: **no bold or color inside a code block.** The `[a★]` tag and the `+`/`-`
symbols carry all the emphasis. To keep decisions scannable, the decision header and
its `Why:` line stay OUTSIDE the block as normal markdown (so they render bold).

## Rules

- Wrap each decision's option block in a single fenced code block.
- Decision header + `Why:` line stay outside the block (bold markdown).
- Each option: `[<letter>] Title`; tag the recommended one `[<letter>★]`.
- Option titles all start at the same column. `[a★]` is one char wider than `[b]`,
  so the `★` eats one of the two trailing spaces — `[a★] Title` and `[b]  Title`
  start the title at the same column.
- Tradeoffs below each option, one per line, ordered descending: most positive
  `(++)` first down to most negative `(--)`.
- The `+`/`-` symbol right-aligns to that option's closing `]`. Under the wider
  `[a★]` the symbols sit one column further right than under `[b]`/`[c]`. Net effect:
  recommended rows have a 1-space symbol→text gap, normal rows have 2.
- Blank line between options.

## Example

Header and `Why:` rendered as normal markdown (bold), then the aligned block:

**Decision 1 — How aggressive a cleanup?**
*Why: how much space comes back.*

```
[a★] Delete all 19 .dmg + clear dupes
  ++ frees ~3.1 GB
   + apps already installed, dmgs are dead weight

[b]  Only the duplicates
  +  safest
 --  frees only ~0.5 GB, real bloat stays

[c]  Everything except notes/PDFs
 ++  emptiest result
  -  removes screenshots/images too
```
