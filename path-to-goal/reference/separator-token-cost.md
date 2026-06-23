# Separator symbol — token cost analysis

Background for why the separator rule uses `·` (middot) and not `◇` (diamond).
Not linked from `SKILL.md`; kept here as the reasoning behind the choice.

## The measurements

Net tokens for an 80-char-wide rule, measured against Anthropic's
`/v1/messages/count_tokens` endpoint (`claude-sonnet-4-6` tokenizer), baseline
subtracted:

| Separator (80-char visual width) | Tokens | Note |
|---|---:|---|
| `◇`×80 (diamond, solid)          | 160 | the original choice |
| `◇ `×40 (diamond + space)        | 158 | spacing saves nothing |
| `◆`×80 (filled diamond)          | 160 | |
| `▸`×80 (triangle)                | 160 | |
| `─`×80 (box-drawing rule)        |  20 | clean continuous line |
| `·`×80 (middot)                  |   3 | **current choice** |
| `=`×80                           |   2 | "railroad" look |
| `-`×80                           |   1 | |

## Takeaways

- **The glyph is the cost, not the spacing.** `◇` tokenizes to ~2 tokens *each*
  (U+25C7, 3 UTF-8 bytes, no BPE merges), so an 80-wide diamond row costs ~160
  tokens on *every* path-to-goal response. Inserting spaces between diamonds
  (158 vs 160) is within noise — it buys nothing.
- **Any visible glyph solves the original problem.** Diamonds were adopted only
  because an all-*space* table row collapses to the title width; a visible
  filler char prevents that collapse. It doesn't need to be expensive.
- **`·` is ~50× cheaper than `◇`** (3 vs 160) for the same job, while still
  reading as an intentional dotted rule. `─` (20 tokens) is the cleanest-looking
  alternative if a solid line is preferred; `=` / `-` are near-free but look
  more like ASCII art.

## Reproduce

```bash
KEY=$(op read "op://Yolo Sam/<anthropic-key-item>/credential")
count() { # $1 = JSON-encoded string
  curl -s https://api.anthropic.com/v1/messages/count_tokens \
    -H "x-api-key: $KEY" -H "anthropic-version: 2023-06-01" \
    -H "content-type: application/json" \
    -d "{\"model\":\"claude-sonnet-4-6\",\"messages\":[{\"role\":\"user\",\"content\":$1}]}"
}
```

Subtract the count of a 1-char message (`8` tokens of envelope overhead) to get
the net figures above.
