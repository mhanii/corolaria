# Streaming Chat API Integration Guide

This guide explains how to integrate the streaming chat endpoint for real-time AI responses.

## Endpoint

```
POST /api/v1/chat/stream
```

Uses **Server-Sent Events (SSE)** to stream responses in real-time.

## Request

Same as the non-streaming `/api/v1/chat` endpoint:

```json
{
  "message": "¿Qué dice el artículo 14 de la Constitución?",
  "conversation_id": null,
  "top_k": 5,
  "collector_type": "rag"
}
```

**Headers:**
```
Content-Type: application/json
Authorization: Bearer <token>
```

## Response Format

The response is a stream of SSE events. Each event follows the format:
```
data: {"type": "...", ...}\n\n
```

### Event Types

| Type | Description | Payload |
|------|-------------|---------|
| `chunk` | Partial response text | `{"type": "chunk", "content": "..."}` |
| `citations` | Citation data (after text completes) | `{"type": "citations", "citations": [...]}` |
| `done` | Stream completion marker | `{"type": "done", "conversation_id": "...", "execution_time_ms": ...}` |
| `error` | Error occurred | `{"type": "error", "message": "..."}` |

### Citation Object

```json
{
  "index": 1,
  "article_id": "abc123",
  "article_number": "Artículo 14",
  "normativa_title": "Constitución Española de 1978",
  "article_path": "Título I",
  "score": 0.92
}
```

## JavaScript Integration

### Using EventSource (GET only - not applicable)

> **Note:** EventSource API only supports GET requests. Use `fetch` with streaming instead.

### Using Fetch API

```javascript
async function streamChat(message, conversationId = null) {
  const response = await fetch('/api/v1/chat/stream', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${token}`
    },
    body: JSON.stringify({
      message,
      conversation_id: conversationId,
      top_k: 5
    })
  });

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  
  let citations = [];
  let conversationIdResult = null;
  let fullResponse = '';

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    
    const text = decoder.decode(value, { stream: true });
    
    // Parse SSE events (may contain multiple events per chunk)
    const lines = text.split('\n');
    for (const line of lines) {
      if (line.startsWith('data: ')) {
        const data = JSON.parse(line.slice(6));
        
        switch (data.type) {
          case 'chunk':
            fullResponse += data.content;
            // Update UI with partial response
            updateChatMessage(fullResponse);
            break;
            
          case 'citations':
            citations = data.citations;
            // Display citations in UI
            displayCitations(citations);
            break;
            
          case 'done':
            conversationIdResult = data.conversation_id;
            console.log(`Completed in ${data.execution_time_ms}ms`);
            break;
            
          case 'error':
            console.error('Stream error:', data.message);
            showError(data.message);
            break;
        }
      }
    }
  }
  
  return { response: fullResponse, citations, conversationId: conversationIdResult };
}
```

### TypeScript Types

```typescript
interface StreamChunkEvent {
  type: 'chunk';
  content: string;
}

interface StreamCitationsEvent {
  type: 'citations';
  citations: Citation[];
}

interface StreamDoneEvent {
  type: 'done';
  conversation_id: string;
  execution_time_ms: number;
  metadata?: Record<string, any>;
}

interface StreamErrorEvent {
  type: 'error';
  message: string;
  details?: Record<string, any>;
}

type StreamEvent = 
  | StreamChunkEvent 
  | StreamCitationsEvent 
  | StreamDoneEvent 
  | StreamErrorEvent;

interface Citation {
  index: number;
  article_id: string;
  article_number: string;
  normativa_title: string;
  article_path: string;
  score: number;
}
```

## Error Handling

1. **HTTP Errors** - Check `response.ok` before reading the stream
2. **Stream Errors** - Handle `error` events from the stream
3. **Network Errors** - Wrap in try/catch for fetch failures

```javascript
try {
  const response = await fetch('/api/v1/chat/stream', options);
  
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail?.message || 'Request failed');
  }
  
  // Process stream...
  
} catch (error) {
  if (error.name === 'AbortError') {
    console.log('Stream aborted by user');
  } else {
    console.error('Stream failed:', error);
  }
}
```

## Fallback to Non-Streaming

If streaming is not supported or fails, fall back to the regular endpoint:

```javascript
async function chat(message, conversationId = null, useStreaming = true) {
  if (useStreaming) {
    try {
      return await streamChat(message, conversationId);
    } catch (e) {
      console.warn('Streaming failed, falling back:', e);
    }
  }
  
  // Fallback to non-streaming
  const response = await fetch('/api/v1/chat', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${token}`
    },
    body: JSON.stringify({ message, conversation_id: conversationId })
  });
  
  return response.json();
}
```

## Testing with curl

```bash
curl -N -X POST "http://localhost:8000/api/v1/chat/stream" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{"message": "¿Qué es el artículo 14?"}'
```

The `-N` flag disables curl's output buffering to see events in real-time.
