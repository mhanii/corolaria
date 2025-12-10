# Beta Testing API Schema

API endpoints for the Coloraria Beta Testing program.

## Base URL
```
/api/v1/beta
```

---

## Authentication
All endpoints require JWT authentication via `Authorization: Bearer <token>` header.

---

## Endpoints

### GET `/status`
Get beta test mode status and user token information.

**Response**: `TestModeStatusResponse`
```json
{
  "test_mode_enabled": true,
  "available_tokens": 5,
  "requires_refill": false,
  "surveys_completed": 2
}
```

---

### GET `/survey/questions`
Get list of survey questions.

**Response**: `SurveyQuestionsResponse`
```json
{
  "questions": [
    "¿Qué tan útil fue la respuesta del asistente? (1-5)",
    "¿La respuesta citó fuentes legales de manera clara?",
    "¿Encontraste la información que buscabas?",
    "¿Qué tan fácil fue entender la respuesta?",
    "¿Recomendarías este asistente a un colega?"
  ],
  "total_questions": 5
}
```

---

### POST `/survey`
Submit survey responses to refill tokens.

**Request**: `SurveyRequest`
```json
{
  "responses": [
    "5 - Muy útil",
    "Sí, las citas fueron claras",
    "Sí, encontré lo que buscaba",
    "4 - Bastante fácil",
    "Sí, lo recomendaría"
  ]
}
```

**Response**: `SurveyResponse`
```json
{
  "success": true,
  "tokens_granted": 10,
  "new_balance": 15,
  "message": "¡Gracias! Se han añadido 10 tokens a tu cuenta."
}
```

---

### POST `/feedback`
Submit like/dislike/report feedback on a message.

**Request**: `FeedbackRequest`
```json
{
  "message_id": 42,
  "conversation_id": "abc123-def456",
  "feedback_type": "like",
  "comment": null
}
```

| `feedback_type` | Description |
|-----------------|-------------|
| `like` | User found response helpful |
| `dislike` | User found response unhelpful |
| `report` | User is reporting an issue |

**Response**: `FeedbackResponse`
```json
{
  "id": "feedback-uuid",
  "success": true,
  "message": "Feedback 'like' registrado. ¡Gracias!"
}
```

---

## Chat Endpoint Changes

### 402 Payment Required Response
When user has no tokens, error now includes:
```json
{
  "error": "InsufficientTokens",
  "message": "You have no remaining API tokens. Complete a survey to refill.",
  "requires_refill": true,
  "survey_endpoint": "/api/v1/beta/survey"
}
```

### Chat Response Fields (Test Mode)

#### `config_matrix`
Configuration used for response generation:
```json
{
  "config_matrix": {
    "model": "gemini-2.5-flash",
    "temperature": 0.3,
    "top_k": 3,
    "collector_type": "rag",
    "prompt_version": "1.0",
    "context_reused": false,
    "next_version_depth": -1,
    "previous_version_depth": 1,
    "max_refers_to": 3
  }
}
```

---

## Phoenix Observability

When Phoenix is enabled, spans are tagged with:
```
feedback.type: "like"
beta.test_mode: true
beta.user_id: "user-uuid"
```
