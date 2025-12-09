# Frontend Migration Guide: Semantic Citations

This document describes the changes to the citation system and how to update your frontend to support the new format.

## Summary

The citation format has changed from numeric markers (`[1]`, `[2]`) to semantic markers that directly reference article identifiers:

| Before | After |
|--------|-------|
| `establece la igualdad [1]` | `[cite:art_14_ce_abc123]Artículo 14[/cite] establece la igualdad` |

---

## API Response Changes

### `CitationResponse` Schema

**New fields:**
- `cite_key` (string): Unique citation identifier (e.g., `"art_14_ce_abc123"`)
- `display_text` (string): Text shown in the citation (e.g., `"Artículo 14"`)

**Removed fields:**
- `index` (was integer `1`, `2`, etc.)

```typescript
// Before
interface Citation {
  index: number;        // e.g., 1
  article_id: string;
  article_number: string;
  normativa_title: string;
  article_path: string;
  score: number;
}

// After
interface Citation {
  cite_key: string;     // e.g., "art_14_ce_abc123"
  display_text: string; // e.g., "Artículo 14"
  article_id: string;
  article_number: string;
  normativa_title: string;
  article_path: string;
  score: number;
}
```

---

## Response Text Format

### Old Format
```
El artículo 14 de la Constitución Española establece que los españoles 
son iguales ante la ley [1]. Este principio fundamental [1] prohíbe 
cualquier discriminación [2].
```

### New Format  
```
El [cite:art_14_ce_abc123]Artículo 14 de la Constitución Española[/cite] 
establece que los españoles son iguales ante la ley. Este principio 
fundamental [cite:art_14_ce_abc123]Artículo 14[/cite] prohíbe cualquier 
discriminación [cite:art_15_ce_def456]Artículo 15[/cite].
```

---

## Parsing Citations

Use this regex to extract citations from response text:

```typescript
const CITATION_REGEX = /\[cite:([^\]]+)\](.+?)\[\/cite\]/gs;

function parseCitations(text: string) {
  const citations: { citeKey: string; displayText: string }[] = [];
  let match;
  
  while ((match = CITATION_REGEX.exec(text)) !== null) {
    citations.push({
      citeKey: match[1],
      displayText: match[2]
    });
  }
  
  return citations;
}
```

---

## Rendering Citations

### Option 1: Clickable Links

Replace citations with interactive elements that link to article details:

```typescript
function renderCitationsAsLinks(text: string, citations: Citation[]) {
  const citationMap = new Map(citations.map(c => [c.cite_key, c]));
  
  return text.replace(
    /\[cite:([^\]]+)\](.+?)\[\/cite\]/g,
    (_, citeKey, displayText) => {
      const citation = citationMap.get(citeKey);
      if (citation) {
        return `<a href="/article/${citation.article_id}" 
                   class="citation-link" 
                   data-cite-key="${citeKey}"
                   title="${citation.normativa_title}">${displayText}</a>`;
      }
      return displayText;
    }
  );
}
```

### Option 2: Tooltips

Show article info on hover:

```typescript
function renderCitationsWithTooltips(text: string, citations: Citation[]) {
  const citationMap = new Map(citations.map(c => [c.cite_key, c]));
  
  return text.replace(
    /\[cite:([^\]]+)\](.+?)\[\/cite\]/g,
    (_, citeKey, displayText) => {
      const citation = citationMap.get(citeKey);
      if (citation) {
        return `<span class="citation" 
                      data-tooltip="${citation.normativa_title} - ${citation.article_path}">
                  ${displayText}
                </span>`;
      }
      return displayText;
    }
  );
}
```

---

## CSS Suggestions

```css
.citation-link {
  color: var(--primary-color);
  text-decoration: underline;
  text-decoration-style: dotted;
  cursor: pointer;
}

.citation-link:hover {
  text-decoration-style: solid;
  background-color: var(--highlight-bg);
}

.citation {
  color: var(--primary-color);
  font-weight: 500;
  border-bottom: 1px dotted currentColor;
  cursor: help;
}
```

---

## Migration Checklist

- [ ] Update TypeScript/interfaces for new `CitationResponse` schema
- [ ] Update citation parsing regex from `\[(\d+)\]` to `\[cite:([^\]]+)\](.+?)\[\/cite\]`
- [ ] Update citation rendering to use `cite_key` instead of `index`
- [ ] Add `display_text` to citation display
- [ ] Update any citation-related tests
- [ ] Remove any logic that references `citation.index`

---

## Example API Response

```json
{
  "response": "El [cite:art_14_ce_229_50]Artículo 14 de la Constitución Española[/cite] establece que los españoles son iguales ante la ley.",
  "conversation_id": "034819a4-f16d-432b-af03-e8b8e0e9fdae",
  "citations": [
    {
      "cite_key": "art_14_ce_229_50",
      "display_text": "Artículo 14 de la Constitución Española",
      "article_id": "BOE-A-1978-31229_50",
      "article_number": "14",
      "normativa_title": "Constitución Española.",
      "article_path": "Titulo I, Capitulo SEGUNDO",
      "score": 0.89
    }
  ],
  "execution_time_ms": 3900.63
}
```

---

## cite_key Format

The `cite_key` follows this pattern: `art_{article_number}_{normativa_abbrev}_{article_id_suffix}`

Examples:
- `art_14_ce_229_50` → Artículo 14, Constitución Española
- `art_18_ce_229_64` → Artículo 18, Constitución Española  
- `art_269_cc_444_123` → Artículo 269, Código Civil

---

## Questions?

Contact the backend team if you have questions about the new citation format.

