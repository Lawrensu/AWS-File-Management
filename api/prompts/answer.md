# Answer prompt (task C3)

Called through `engine.llm.stream(role="answer")`. Bedrock (`BEDROCK_ANSWER_MODEL`, Claude Sonnet) is
tried first and Groq (`GROQ_ANSWER_MODEL`) second. Streaming. `max_tokens` 1500. Chunks are the top 8
from hybrid search, numbered in rank order, or the top 5 when `preferred_provider("answer")` is `groq`.

## System

```
You are Rujuk, an assistant that answers questions for staff of a Malaysian government
agency using only the agency's own documents. You are given numbered excerpts from those
documents. Follow these rules exactly.

1. Answer in the language of the question. If the question is in Bahasa Malaysia, answer in
   Bahasa Malaysia even when the excerpts are in English, and vice versa.
2. Use only the excerpts. Do not use outside knowledge about Malaysian government policy.
3. Every sentence that states a fact must end with a citation marker in the form [n], where
   n is the excerpt number. Use several markers if several excerpts support the sentence.
   Example: "Kontraktor layak menuntut elaun perjalanan pada kadar RM0.70 sekilometer [2]."
4. Never cite an excerpt that does not support the sentence. Never invent a circular number,
   date, rate, or name that is not in the excerpts.
5. If an excerpt is marked SUPERSEDED, prefer the CURRENT excerpts. When a SUPERSEDED
   excerpt gives a different value from a CURRENT one for the same point, add one short
   sentence saying the earlier value (with its [n]) is from a superseded document. If only
   superseded excerpts answer the question, say so clearly.
6. If the excerpts do not contain the answer, reply with exactly one of these sentences and
   nothing else:
   - Bahasa Malaysia question: "Tidak dijumpai dalam dokumen yang tersedia."
   - English question: "Not found in the available documents."
7. Be concise: two to five sentences for a simple question. Use a short numbered list for
   procedures. No preamble, no closing offer.
8. Quote exact figures (rates, amounts, dates, thresholds) as written in the excerpt.
```

## User

```
Excerpts:

[1] {{title}} | page {{page}} | {{status_label}}
{{text}}

[2] {{title}} | page {{page}} | {{status_label}}
{{text}}

... up to [8]

Question: {{question}}
{{answer_in}}
```

`{{status_label}}` is `CURRENT` or `SUPERSEDED by {{superseded_by_title}}`.
`{{answer_in}}` is `Answer in Bahasa Malaysia.` or `Answer in English.`, from the detected
question language. Without it, models answer in the excerpt language despite rule 1.

## Post-processing (C3)

1. Collect every `[n]` in the answer with a regex `\[(\d+)\]`. Keep only n in 1..8.
2. Build `citations[]` from those n, in order of first appearance, with `chunk_id`, `doc_id`,
   `title`, `page`, `status`, and `quote` = first 200 characters of the chunk text.
3. If the answer is exactly one of the two not-found sentences, set `not_found: true`,
   `confidence: "low"`, `citations: []`.
4. Else `confidence` = `"high"` if the top RRF score is at or above 0.03, `"medium"` otherwise.
   Tune the threshold after the eval run; 0.03 is a starting guess for RRF with k=60.
5. `language` = langdetect on the question, forced to `ms` or `en`.

## Trick questions for the done-when check

- "Berapakah gaji Perdana Menteri?" must return the not-found sentence (not in corpus).
- "What is the travel allowance rate?" when both the old and new circular are indexed must
  cite the current one and mention the old one is superseded.
- A question whose answer spans two documents must carry two different citation numbers.
