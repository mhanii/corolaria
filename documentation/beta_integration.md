# Beta Testing Frontend Integration Guide

Guide for integrating the Beta Testing features into the Coloraria frontend.

---

## Quick Start

### 1. Check Test Mode Status
On app load, check if user is in test mode:
```typescript
const response = await fetch('/api/v1/beta/status', {
  headers: { 'Authorization': `Bearer ${token}` }
});
const status = await response.json();

if (status.requires_refill) {
  // Show survey modal
}
```

---

## Token Refill Flow

### When Surveys Trigger

Surveys are triggered when:
1. **Token depletion** - User runs out of tokens (receives 402 error)
2. **requires_refill = true** - Check via `GET /api/v1/beta/status`

| Event | Trigger |
|-------|---------|
| 402 `InsufficientTokens` | Show survey modal immediately |
| Status check `requires_refill: true` | Prompt user to complete survey |

### Token Economy
- **Initial tokens**: 15 (for new test users created with `--test` flag)
- **Refill amount**: +10 tokens per survey completion
- **No daily limits** - Users can complete surveys as needed

### Question Types

Surveys contain 5 questions in two types:

| # | Type | Question | Response Format |
|---|------|----------|-----------------|
| 1 | Rating | ¿Qué tan útil fue la respuesta? | 1-5 scale |
| 2 | Rating | ¿Qué tan claras fueron las citas? | 1-5 scale |
| 3 | Rating | ¿Qué tan fácil fue entender? | 1-5 scale |
| 4 | Rating | ¿Recomendarías este asistente? | 1-5 scale |
| 5 | Open | ¿Cómo podemos mejorar? | Free text |

### When 402 Error Occurs
```typescript
try {
  await sendChatMessage(message);
} catch (error) {
  if (error.status === 402 && error.detail.requires_refill) {
    showSurveyModal();
  }
}
```

### Survey Submission
```typescript
// 1. Get questions from API
const questionsRes = await fetch('/api/v1/beta/survey/questions');
const { questions } = await questionsRes.json();

// 2. Display form - render each question based on position
questions.forEach((q, i) => {
  if (i < 4) {
    // Rating questions 1-5
    renderRatingInput(q);
  } else {
    // Open-ended text input
    renderTextarea(q);
  }
});

// 3. Submit responses (array of strings matching question order)
const surveyRes = await fetch('/api/v1/beta/survey', {
  method: 'POST',
  headers: { 
    'Authorization': `Bearer ${token}`,
    'Content-Type': 'application/json'
  },
  body: JSON.stringify({ 
    responses: ['5', '4', '5', '5', 'Me gustaría más ejemplos prácticos'] 
  })
});

const result = await surveyRes.json();
// result.tokens_granted = 10
// result.new_balance = updated token count
```

---

## Feedback System

### Add Like/Dislike Buttons
After each assistant message, add feedback buttons:
```tsx
<FeedbackButtons
  messageId={message.id}
  conversationId={conversationId}
  onFeedback={handleFeedback}
/>
```

### Submit Feedback
```typescript
const submitFeedback = async (
  messageId: number,
  conversationId: string,
  type: 'like' | 'dislike' | 'report',
  comment?: string
) => {
  await fetch('/api/v1/beta/feedback', {
    method: 'POST',
    headers: { 
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({
      message_id: messageId,
      conversation_id: conversationId,
      feedback_type: type,
      comment
    })
  });
};
```

---

## Config Matrix Display (Debug Mode)

In test mode, chat responses include `config_matrix`:
```typescript
if (response.config_matrix) {
  // Display debug info (dev tools or admin view)
  console.log('Config:', response.config_matrix);
}
```

---

## UI Components Needed

| Component | Purpose |
|-----------|---------|
| `SurveyModal` | Display 5 questions on token depletion |
| `FeedbackButtons` | Like/Dislike/Report on each message |
| `TokenCounter` | Display remaining tokens in header |

---

## Error Handling

| Status | Error | Action |
|--------|-------|--------|
| 402 | `InsufficientTokens` | Show survey modal |
| 404 | `ConversationNotFound` | Redirect to new chat |
| 403 | `Forbidden` | Show access denied |
