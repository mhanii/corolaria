# Frontend API Integration Guide

## Overview

This document describes the updated API structure with authentication for the Coloraria chatbot. All chat endpoints now require JWT authentication.

---

## Breaking Changes ⚠️

1. **All chat endpoints now require authentication**
2. **New header required**: `Authorization: Bearer <token>`
3. **New endpoint**: `GET /api/v1/conversations` to list user's conversations
4. **Token consumption**: Each chat message consumes 1 token from user's balance

---

## Authentication Flow

```
┌─────────────────────────────────────────────────────────────┐
│  1. User enters credentials                                  │
│  2. Frontend calls POST /api/v1/auth/login                  │
│  3. Backend returns JWT token + user info                   │
│  4. Frontend stores token (localStorage/sessionStorage)     │
│  5. Frontend includes token in all subsequent requests      │
└─────────────────────────────────────────────────────────────┘
```

---

## API Endpoints

### 1. Login

**Endpoint**: `POST /api/v1/auth/login`

**Headers**:
```
Content-Type: application/json
```

**Request Body**:
```json
{
  "username": "string",    // Required, min 3 chars
  "password": "string"     // Required, min 6 chars
}
```

**Success Response** (200):
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "token_type": "bearer",
  "expires_in": 86400,           // Seconds (24 hours)
  "user_id": "uuid-string",
  "username": "john_doe",
  "available_tokens": 1000       // API call tokens remaining
}
```

**Error Response** (401):
```json
{
  "detail": {
    "error": "Unauthorized",
    "message": "Invalid username or password"
  }
}
```

---

### 2. Get Current User

**Endpoint**: `GET /api/v1/auth/me`

**Headers**:
```
Authorization: Bearer <access_token>
```

**Success Response** (200):
```json
{
  "id": "uuid-string",
  "username": "john_doe",
  "available_tokens": 950,
  "created_at": "2024-01-15T10:30:00"
}
```

---

### 3. Send Chat Message

**Endpoint**: `POST /api/v1/chat`

**Headers**:
```
Authorization: Bearer <access_token>
Content-Type: application/json
```

**Request Body**:
```json
{
  "message": "string",              // Required
  "conversation_id": "string|null", // Optional - null for new conversation
  "top_k": 5                        // Optional (1-20), default 5
}
```

**Success Response** (200):
```json
{
  "response": "AI response with [1] citations...",
  "conversation_id": "uuid-string",  // ← SAVE THIS for follow-ups
  "citations": [
    {
      "index": 1,
      "article_id": "string",
      "article_number": "Artículo 14",
      "normativa_title": "Constitución Española",
      "article_path": "Título I, Capítulo II",
      "score": 0.89
    }
  ],
  "execution_time_ms": 1250.5
}
```

**Error Responses**:
- `401`: Invalid/expired token
- `402`: Insufficient tokens (user has no API calls left)
- `500`: Server error

---

### 4. List Conversations

**Endpoint**: `GET /api/v1/conversations`

**Headers**:
```
Authorization: Bearer <access_token>
```

**Success Response** (200):
```json
{
  "conversations": [
    {
      "id": "uuid-string",
      "created_at": "2024-01-15T10:30:00",
      "updated_at": "2024-01-15T11:45:00",
      "message_count": 8,
      "preview": "¿Qué dice el artículo 14..."  // First message preview
    }
  ],
  "total": 5
}
```

---

### 5. Get Conversation History

**Endpoint**: `GET /api/v1/chat/{conversation_id}`

**Headers**:
```
Authorization: Bearer <access_token>
```

**Success Response** (200):
```json
{
  "id": "uuid-string",
  "messages": [
    {
      "role": "user",
      "content": "¿Qué dice el artículo 14?",
      "citations": [],
      "timestamp": "2024-01-15T10:30:00"
    },
    {
      "role": "assistant",
      "content": "El artículo 14 establece...",
      "citations": [
        {
          "index": 1,
          "article_id": "...",
          "article_number": "14",
          "normativa_title": "Constitución",
          "article_path": "Título I",
          "score": 0.92
        }
      ],
      "timestamp": "2024-01-15T10:30:05"
    }
  ],
  "created_at": "2024-01-15T10:30:00",
  "updated_at": "2024-01-15T10:30:05"
}
```

---

### 6. Delete Conversation

**Endpoint**: `DELETE /api/v1/chat/{conversation_id}`

**Headers**:
```
Authorization: Bearer <access_token>
```

**Success Response** (200):
```json
{
  "success": true,
  "message": "Conversation 'uuid' deleted successfully"
}
```

---

### 7. Clear Conversation

**Endpoint**: `POST /api/v1/chat/{conversation_id}/clear`

**Headers**:
```
Authorization: Bearer <access_token>
```

**Success Response** (200):
```json
{
  "success": true,
  "message": "Conversation 'uuid' cleared successfully"
}
```

---

## Frontend Implementation Guide

### 1. Token Storage

```typescript
// After successful login
const handleLogin = async (username: string, password: string) => {
  const response = await fetch('/api/v1/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password })
  });
  
  if (response.ok) {
    const data = await response.json();
    localStorage.setItem('access_token', data.access_token);
    localStorage.setItem('user', JSON.stringify({
      id: data.user_id,
      username: data.username,
      tokens: data.available_tokens
    }));
  }
};
```

### 2. API Client with Auth

```typescript
// Create an authenticated fetch wrapper
const authFetch = async (url: string, options: RequestInit = {}) => {
  const token = localStorage.getItem('access_token');
  
  const headers = {
    ...options.headers,
    'Authorization': `Bearer ${token}`,
    'Content-Type': 'application/json'
  };
  
  const response = await fetch(url, { ...options, headers });
  
  // Handle token expiration
  if (response.status === 401) {
    localStorage.removeItem('access_token');
    window.location.href = '/login';
    throw new Error('Session expired');
  }
  
  return response;
};
```

### 3. Chat Service

```typescript
interface ChatMessage {
  message: string;
  conversation_id?: string | null;
  top_k?: number;
}

const sendMessage = async (chat: ChatMessage) => {
  const response = await authFetch('/api/v1/chat', {
    method: 'POST',
    body: JSON.stringify(chat)
  });
  
  if (response.status === 402) {
    throw new Error('No tokens remaining');
  }
  
  return response.json();
};

// Example usage
const startNewChat = async (message: string) => {
  const result = await sendMessage({ message, conversation_id: null });
  // Save conversation_id for follow-ups
  return result;
};

const continueChat = async (message: string, conversationId: string) => {
  return sendMessage({ message, conversation_id: conversationId });
};
```

### 4. Conversation Management

```typescript
const getConversations = async () => {
  const response = await authFetch('/api/v1/conversations');
  return response.json();
};

const getConversationHistory = async (id: string) => {
  const response = await authFetch(`/api/v1/chat/${id}`);
  return response.json();
};
```

---

## Error Handling

| Status | Meaning | Action |
|--------|---------|--------|
| 401 | Token invalid/expired | Redirect to login |
| 402 | No tokens remaining | Show "out of tokens" message |
| 404 | Conversation not found | Remove from UI, show error |
| 500 | Server error | Show generic error, retry |

---

## Token Balance

- Each chat message consumes **1 token**
- Check `available_tokens` in login response or `/auth/me`
- When tokens reach 0, chat returns `402 Payment Required`
- **No automatic token refresh** - contact admin for more tokens

---

## Security Notes

1. **Never log tokens** in console or error reports
2. **Clear tokens on logout**: `localStorage.removeItem('access_token')`
3. **Tokens expire in 24 hours** - handle gracefully
4. **User isolation**: Users can only see their own conversations

---

## Questions?

Contact the backend team for:
- Creating test accounts
- Token allocation
- API issues
