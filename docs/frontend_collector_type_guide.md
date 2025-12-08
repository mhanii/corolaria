# Chat API Update - Collector Type Selection

## Overview

A new optional field `collector_type` has been added to the Chat API to allow users to choose between different context retrieval strategies.

## API Changes

### POST `/v1/chat`

**New Request Field:**

```json
{
  "message": "¿Qué es un contrato de arrendamiento?",
  "conversation_id": null,
  "top_k": 5,
  "collector_type": "qrag"  // NEW - optional
}
```

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `collector_type` | `string` | No | `"rag"` | Context retrieval strategy |

**Allowed Values:**
- `"rag"` - Standard vector search (fast, default)
- `"qrag"` - Query-optimized search using AI (slower, potentially more accurate for complex questions)

## Frontend Integration

### 1. Add UI Toggle (Optional)

You may want to add a toggle or dropdown in the chat interface:

```
[ ] Use Advanced Search (QRAG)
```

Or a dropdown:
```
Search Mode: [Standard ▾]
             - Standard (RAG)
             - Advanced (QRAG)
```

### 2. Update Chat Request

```typescript
interface ChatRequest {
  message: string;
  conversation_id?: string;
  top_k?: number;
  collector_type?: 'rag' | 'qrag';  // ADD THIS
}
```

### 3. Send on First Message Only

> **Important:** `collector_type` only applies to the **first message** of a new conversation. It is ignored for follow-up messages.

```typescript
const sendMessage = async (message: string, conversationId?: string) => {
  const payload: ChatRequest = {
    message,
    conversation_id: conversationId,
    top_k: 5,
  };
  
  // Only include collector_type for new conversations
  if (!conversationId && userSelectedQRAG) {
    payload.collector_type = 'qrag';
  }
  
  return await api.post('/v1/chat', payload);
};
```

## Behavior Notes

1. **QRAG is slower** - It makes an additional LLM call to generate optimized queries
2. **Best for complex questions** - QRAG shines when users ask about multiple topics or vague questions
3. **Default is fine for most cases** - RAG works well for simple, direct questions

## Questions?

Contact the backend team for clarification.
