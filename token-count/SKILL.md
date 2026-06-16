---
name: token-count
description: "Use when you need a free, accurate token count across Anthropic/Gemini/OpenAI for prompt budgeting, skill sizing, or annotating file references. Returns per-vendor counts and a range string."
---

# Token count

Call all three server-side count endpoints (no inference, free), then return a structured result.

- **Anthropic** — `POST https://api.anthropic.com/v1/messages/count_tokens` (`x-api-key`)
- **Gemini** — `POST https://generativelanguage.googleapis.com/v1beta/models/{model}:countTokens` (API key)
- **OpenAI** — `POST https://api.openai.com/v1/responses/input_tokens` (`Bearer`)

Tokenizer is vendor-fixed; model only selects family. Use any current model per vendor (e.g. `claude-sonnet-4-6`, `gemini-2.5-flash`, `gpt-5`).

## Output

Return a JSON object:

```json
{
  "counts": { "anthropic": 1234, "gemini": 1200, "openai": 1300 },
  "range": "1,200–1,300 tokens"
}
```

- `range` — smallest–largest, comma-formatted, suffixed ` tokens`
