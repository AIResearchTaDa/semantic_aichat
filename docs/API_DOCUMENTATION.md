# 📡 API Документація — Семантичний Пошук TA-DA!

## Зміст
- [Огляд API](#огляд-api)
- [Аутентифікація](#аутентифікація)
- [Endpoints](#endpoints)
- [Моделі даних](#моделі-даних)
- [Коди помилок](#коди-помилок)
- [Приклади використання](#приклади-використання)

---

## Огляд API

**Base URL:** `http://localhost:8080`  
**Protocol:** HTTP/1.1  
**Content-Type:** `application/json`  
**Encoding:** UTF-8

### Версії API
- **Current:** v1 (включена в основний URL)
- **Stability:** Production Ready

---

## Аутентифікація

На даний момент API не вимагає аутентифікації для базових операцій.

Для інтеграції з TA-DA API використовується токен:
```http
Authorization: Bearer <TA_DA_API_TOKEN>
User-Language: ua
```

---

## Endpoints

### 1. Health Check

Перевірка стану сервісу.

**Endpoint:** `GET /health`

**Параметри:** Немає

**Відповідь 200 OK:**
```json
{
  "status": "healthy",
  "elasticsearch": "connected",
  "embedding_service": "available",
  "gpt_service": "available",
  "timestamp": "2025-10-13T10:00:00.000Z",
  "version": "1.0.0"
}
```

**Відповідь 503 Service Unavailable:**
```json
{
  "status": "unhealthy",
  "elasticsearch": "disconnected",
  "error": "Connection timeout"
}
```

**Приклад:**
```bash
curl http://localhost:8080/health
```

---

### 2. Конфігурація

Отримання конфігурації фіч.

**Endpoint:** `GET /config`

**Параметри:** Немає

**Відповідь 200 OK:**
```json
{
  "streaming_enabled": true,
  "gpt_enabled": true,
  "version": "1.0.0",
  "features": {
    "chat_search": true,
    "recommendations": true,
    "image_proxy": true
  }
}
```

**Приклад:**
```bash
curl http://localhost:8080/config
```

---

### 3. Простий пошук

Виконує пошук товарів з підтримкою різних типів пошуку.

**Endpoint:** `POST /search`

**Content-Type:** `application/json`

**Тіло запиту:**
```json
{
  "query": "олівці кольорові",
  "k": 20,
  "search_type": "hybrid"
}
```

**Параметри:**
| Параметр | Тип | Обов'язковий | За замовчуванням | Опис |
|----------|-----|--------------|------------------|------|
| `query` | string | Так | - | Пошуковий запит |
| `k` | integer | Ні | 20 | Кількість результатів (1-100) |
| `search_type` | string | Ні | "hybrid" | Тип пошуку: `hybrid`, `vector`, `bm25` |

**Відповідь 200 OK:**
```json
{
  "results": [
    {
      "uuid": "12345-67890",
      "title_ua": "Олівці кольорові 24 кольори",
      "title_ru": "Карандаши цветные 24 цвета",
      "description_ua": "Набір олівців для малювання та творчості",
      "description_ru": "Набор карандашей для рисования и творчества",
      "score": 0.9523,
      "price": 89.99,
      "image_url": "https://cdn.ta-da.net.ua/images/prod-123.jpg",
      "category": "stationery_art",
      "in_stock": true,
      "sku": "ART-024-COL"
    }
  ],
  "query": "олівці кольорові",
  "total": 42,
  "search_type": "hybrid",
  "search_time_ms": 234.5
}
```

**Помилки:**
- `400 Bad Request` — невалідний запит
- `422 Unprocessable Entity` — помилка валідації
- `500 Internal Server Error` — помилка сервера

**Приклад:**
```bash
curl -X POST http://localhost:8080/search \
  -H "Content-Type: application/json" \
  -d '{
    "query": "олівці кольорові", 
    "k": 10,
    "search_type": "hybrid"
  }'
```

---

### 4. AI Чат-пошук (POST)

Інтелектуальний пошук з AI аналізом запиту.

**Endpoint:** `POST /chat/search`

**Content-Type:** `application/json`

**Тіло запиту:**
```json
{
  "query": "що подарувати дитині на 5 років",
  "session_id": "user-session-123",
  "dialog_context": null,
  "k": 50
}
```

**Параметри:**
| Параметр | Тип | Обов'язковий | Опис |
|----------|-----|--------------|------|
| `query` | string | Так | Пошуковий запит або питання |
| `session_id` | string | Так | Унікальний ID сесії користувача |
| `dialog_context` | object | Ні | Контекст попереднього діалогу |
| `k` | integer | Ні | Максимальна кількість товарів (за замовчуванням 50) |

**Відповідь 200 OK:**
```json
{
  "intent": "product_search",
  "clarification": null,
  "subqueries": [
    "іграшки для дітей 5 років",
    "розвиваючі ігри для дошкільнят",
    "конструктори для малюків"
  ],
  "products": [
    {
      "uuid": "toy-001",
      "title_ua": "Конструктор LEGO Classic",
      "score": 0.8945,
      "recommended": true,
      "category": "toys_educational",
      "image_url": "...",
      "price": 599.00
    }
  ],
  "recommendations": [
    {
      "product_uuid": "toy-001",
      "title": "Конструктор LEGO Classic",
      "reasoning": "Чудовий вибір для розвитку моторики та творчості п'ятирічної дитини",
      "benefits": [
        "Розвиває просторове мислення",
        "Стимулює креативність",
        "Безпечні матеріали"
      ]
    }
  ],
  "dialog_context": {
    "last_intent": "product_search",
    "categories_mentioned": ["toys_educational"],
    "user_preferences": {}
  },
  "total_found": 27,
  "search_time_ms": 1234.5,
  "metadata": {
    "subquery_count": 3,
    "recommended_count": 3,
    "filtering_applied": true
  }
}
```

**Intent types:**
- `product_search` — пошук товарів
- `clarification` — потрібні уточнення від користувача
- `invalid` — запит не стосується товарів

**Коли `intent: "clarification"`:**
```json
{
  "intent": "clarification",
  "clarification": "Будь ласка, уточніть: ви шукаєте подарунок для хлопчика чи дівчинки? Які інтереси у дитини?",
  "suggested_questions": [
    "Іграшки для хлопчика 5 років",
    "Іграшки для дівчинки 5 років",
    "Розвиваючі ігри для 5 років"
  ],
  "products": [],
  "dialog_context": {...}
}
```

**Приклад:**
```bash
curl -X POST http://localhost:8080/chat/search \
  -H "Content-Type: application/json" \
  -d '{
    "query": "товари для школи першокласнику",
    "session_id": "session-abc123",
    "k": 50
  }'
```

---

### 5. AI Чат-пошук SSE (Server-Sent Events)

Потокова передача результатів пошуку в реальному часі.

**Endpoint:** `GET /chat/search/sse`

**Query параметри:**
| Параметр | Тип | Обов'язковий | Опис |
|----------|-----|--------------|------|
| `query` | string | Так | Пошуковий запит (URL encoded) |
| `session_id` | string | Так | ID сесії |
| `dialog_context` | string | Ні | JSON контексту (URL encoded) |
| `k` | integer | Ні | Кількість товарів |

**Відповідь:** `text/event-stream`

**Події (events):**

#### `intent` — визначений тип запиту
```
event: intent
data: {"intent": "product_search", "clarification": null}
```

#### `subquery` — згенерований підзапит
```
event: subquery
data: {"subquery": "зошити шкільні", "index": 0, "total": 3}
```

#### `product` — знайдений товар
```
event: product
data: {
  "product": {
    "uuid": "prod-123",
    "title_ua": "Зошит шкільний 12 аркушів",
    "score": 0.9234,
    "image_url": "...",
    ...
  },
  "score": 0.9234,
  "recommended": true,
  "subquery_index": 0
}
```

#### `recommendation` — AI рекомендація
```
event: recommendation
data: {
  "product_uuid": "prod-123",
  "title": "Зошит шкільний 12 аркушів",
  "reasoning": "Цей зошит ідеально підходить для першокласника...",
  "benefits": ["Якісний папір", "Міцна обкладинка"],
  "index": 0
}
```

#### `category` — виявлена категорія
```
event: category
data: {"category": "stationery_notebooks", "label": "Зошити та блокноти"}
```

#### `done` — завершення пошуку
```
event: done
data: {
  "total_products": 28,
  "total_recommended": 3,
  "search_time_ms": 1456.7,
  "dialog_context": {...}
}
```

#### `error` — помилка
```
event: error
data: {"error": "Timeout while generating embeddings", "code": "EMBEDDING_TIMEOUT"}
```

**Приклад:**
```javascript
const eventSource = new EventSource(
  `/chat/search/sse?query=${encodeURIComponent('товари для школи')}&session_id=abc123`
);

eventSource.addEventListener('intent', (e) => {
  const data = JSON.parse(e.data);
  console.log('Intent:', data.intent);
});

eventSource.addEventListener('product', (e) => {
  const data = JSON.parse(e.data);
  console.log('Product:', data.product.title_ua);
});

eventSource.addEventListener('done', (e) => {
  const data = JSON.parse(e.data);
  console.log('Done! Total products:', data.total_products);
  eventSource.close();
});

eventSource.addEventListener('error', (e) => {
  const data = JSON.parse(e.data);
  console.error('Error:', data.error);
  eventSource.close();
});
```

---

### 6. Завантаження додаткових товарів

Lazy loading для чат-пошуку.

**Endpoint:** `POST /chat/search/load-more`

**Тіло запиту:**
```json
{
  "session_id": "session-123",
  "offset": 20,
  "limit": 20
}
```

**Параметри:**
| Параметр | Тип | Обов'язковий | Опис |
|----------|-----|--------------|------|
| `session_id` | string | Так | ID сесії з попереднього пошуку |
| `offset` | integer | Так | Зсув (пропустити N товарів) |
| `limit` | integer | Ні | Кількість товарів (за замовчуванням 20) |

**Відповідь 200 OK:**
```json
{
  "products": [...],
  "offset": 20,
  "limit": 20,
  "has_more": true,
  "total_available": 78
}
```

**Відповідь 404 Not Found:**
```json
{
  "detail": "No cached results for session session-123"
}
```

**Приклад:**
```bash
curl -X POST http://localhost:8080/chat/search/load-more \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "session-123",
    "offset": 20,
    "limit": 20
  }'
```

---

### 7. Статистика

Отримання статистики роботи системи.

**Endpoint:** `GET /stats`

**Відповідь 200 OK:**
```json
{
  "total_searches": 1523,
  "cache_hits": 456,
  "cache_misses": 789,
  "cache_hit_rate": 0.366,
  "cache_size": 456,
  "avg_search_time_ms": 234.5,
  "total_products_indexed": 12456,
  "elasticsearch_status": "green",
  "uptime_seconds": 86400
}
```

**Приклад:**
```bash
curl http://localhost:8080/stats
```

---

### 8. Очищення кешу

Очищає кеш embeddings.

**Endpoint:** `POST /cache/clear`

**Відповідь 200 OK:**
```json
{
  "message": "Cache cleared successfully",
  "items_removed": 456
}
```

**Приклад:**
```bash
curl -X POST http://localhost:8080/cache/clear
```

---

### 9. Статистика кешу

Детальна інформація про кеш.

**Endpoint:** `GET /cache/stats`

**Відповідь 200 OK:**
```json
{
  "size": 456,
  "max_size": 2000,
  "hit_rate": 0.366,
  "total_hits": 1234,
  "total_misses": 2345,
  "oldest_entry_age_seconds": 3456,
  "memory_usage_mb": 12.5
}
```

**Приклад:**
```bash
curl http://localhost:8080/cache/stats
```

---

### 10. Проксі зображень

Проксує зображення товарів для обходу CORS.

**Endpoint:** `GET /api/image-proxy`

**Query параметри:**
| Параметр | Тип | Обов'язковий | Опис |
|----------|-----|--------------|------|
| `url` | string | Так | URL зображення (URL encoded) |

**Відповідь 200 OK:** Бінарні дані зображення

**Headers:**
```
Content-Type: image/jpeg
Cache-Control: public, max-age=3600
```

**Приклад:**
```html
<img src="/api/image-proxy?url=https%3A%2F%2Fexample.com%2Fimage.jpg" alt="Product">
```

---

### 11. Логи пошуку

#### 11.1. Отримати список сесій

**Endpoint:** `GET /search-logs/sessions`

**Відповідь 200 OK:**
```json
{
  "sessions": [
    "session-abc123",
    "session-def456",
    "session-ghi789"
  ],
  "total": 3
}
```

#### 11.2. Отримати логи сесії

**Endpoint:** `GET /search-logs/session/{session_id}`

**Відповідь 200 OK:**
```json
{
  "session_id": "session-abc123",
  "logs": [
    {
      "timestamp": "2025-10-13T10:00:00",
      "query": "товари для школи",
      "intent": "product_search",
      "total_found": 45,
      "search_time_ms": 890
    }
  ]
}
```

#### 11.3. Звіт по сесії

**Endpoint:** `GET /search-logs/report/{session_id}`

**Відповідь 200 OK:**
```json
{
  "session_id": "session-abc123",
  "total_queries": 5,
  "first_query_time": "2025-10-13T10:00:00",
  "last_query_time": "2025-10-13T10:15:30",
  "average_stats": {
    "search_time_ms": 856.3,
    "products_found": 38.2,
    "products_after_filtering": 24.8,
    "filtering_rate": 0.649,
    "max_score": 0.8923
  },
  "score_distribution": {
    "min": 0.3012,
    "max": 0.9876,
    "avg": 0.7234
  },
  "queries": [...]
}
```

#### 11.4. Експорт звітів

**Endpoint:** `GET /search-logs/export`

**Відповідь 200 OK:**
```json
{
  "generated_at": "2025-10-13T12:00:00",
  "total_sessions": 15,
  "sessions": [
    {
      "session_id": "...",
      "total_queries": 5,
      "average_stats": {...},
      ...
    }
  ]
}
```

#### 11.5. Статистика логів

**Endpoint:** `GET /search-logs/stats`

**Відповідь 200 OK:**
```json
{
  "total_sessions": 15,
  "total_queries": 87,
  "avg_queries_per_session": 5.8,
  "global_avg_search_time_ms": 923.4,
  "global_avg_products_found": 42.1,
  "most_active_session": "session-abc123",
  "date_range": {
    "first": "2025-10-01T00:00:00",
    "last": "2025-10-13T12:00:00"
  }
}
```

---

## Моделі даних

### Product
```typescript
interface Product {
  uuid: string;                  // Унікальний ID товару
  title_ua: string;              // Назва українською
  title_ru: string;              // Назва російською
  description_ua?: string;       // Опис українською
  description_ru?: string;       // Опис російською
  score: number;                 // Релевантність (0-1)
  price?: number;                // Ціна в грн
  image_url?: string;            // URL зображення
  category?: string;             // Код категорії
  in_stock?: boolean;            // Наявність
  sku?: string;                  // Артикул
  good_code?: string;            // Код товару
  brand?: string;                // Бренд
  recommended?: boolean;         // Чи рекомендований AI
}
```

### ChatSearchResponse
```typescript
interface ChatSearchResponse {
  intent: "product_search" | "clarification" | "invalid";
  clarification?: string;
  subqueries: string[];
  products: Product[];
  recommendations: Recommendation[];
  dialog_context: DialogContext;
  total_found: number;
  search_time_ms: number;
  metadata?: {
    subquery_count: number;
    recommended_count: number;
    filtering_applied: boolean;
  };
}
```

### Recommendation
```typescript
interface Recommendation {
  product_uuid: string;
  title: string;
  reasoning: string;
  benefits: string[];
  index?: number;
}
```

### DialogContext
```typescript
interface DialogContext {
  last_intent: string;
  categories_mentioned: string[];
  user_preferences: Record<string, any>;
  conversation_history?: Array<{
    query: string;
    intent: string;
    timestamp: string;
  }>;
}
```

---

## Коди помилок

### HTTP статус коди

| Код | Значення | Коли виникає |
|-----|----------|--------------|
| 200 | OK | Успішний запит |
| 400 | Bad Request | Невалідні параметри |
| 404 | Not Found | Ресурс не знайдено |
| 422 | Unprocessable Entity | Помилка валідації Pydantic |
| 500 | Internal Server Error | Внутрішня помилка сервера |
| 503 | Service Unavailable | Сервіс недоступний |

### Формат помилки
```json
{
  "detail": "Error message",
  "error_code": "SPECIFIC_ERROR_CODE",
  "timestamp": "2025-10-13T10:00:00"
}
```

### Коди специфічних помилок

| Код | Опис |
|-----|------|
| `ELASTICSEARCH_CONNECTION_ERROR` | Не вдалося підключитися до Elasticsearch |
| `EMBEDDING_TIMEOUT` | Таймаут при генерації embedding |
| `EMBEDDING_API_ERROR` | Помилка Embedding API |
| `GPT_TIMEOUT` | Таймаут GPT запиту |
| `GPT_API_ERROR` | Помилка OpenAI API |
| `INVALID_SESSION` | Невалідний session_id |
| `CACHE_MISS` | Дані не знайдені в кеші |
| `VALIDATION_ERROR` | Помилка валідації даних |

---

## Приклади використання

### Python
```python
import requests

# Простий пошук
response = requests.post(
    "http://localhost:8080/search",
    json={
        "query": "олівці кольорові",
        "k": 10,
        "search_type": "hybrid"
    }
)
results = response.json()
print(f"Знайдено {len(results['results'])} товарів")

# AI чат-пошук
response = requests.post(
    "http://localhost:8080/chat/search",
    json={
        "query": "що подарувати дитині на 5 років",
        "session_id": "user-123",
        "k": 50
    }
)
data = response.json()
if data['intent'] == 'product_search':
    print(f"Знайдено {len(data['products'])} товарів")
    for rec in data['recommendations'][:3]:
        print(f"- {rec['title']}: {rec['reasoning']}")
```

### JavaScript (SSE)
```javascript
const query = "товари для школи";
const sessionId = "session-" + Date.now();

const eventSource = new EventSource(
  `/chat/search/sse?query=${encodeURIComponent(query)}&session_id=${sessionId}`
);

const products = [];
const recommendations = [];

eventSource.addEventListener('product', (e) => {
  const data = JSON.parse(e.data);
  products.push(data.product);
  updateUI(products);
});

eventSource.addEventListener('recommendation', (e) => {
  const data = JSON.parse(e.data);
  recommendations.push(data);
  displayRecommendation(data);
});

eventSource.addEventListener('done', (e) => {
  const data = JSON.parse(e.data);
  console.log(`Пошук завершено: ${data.total_products} товарів за ${data.search_time_ms}ms`);
  eventSource.close();
});
```

### cURL
```bash
# Health check
curl http://localhost:8080/health

# Простий пошук
curl -X POST http://localhost:8080/search \
  -H "Content-Type: application/json" \
  -d '{"query": "зошити", "k": 5}'

# AI чат-пошук
curl -X POST http://localhost:8080/chat/search \
  -H "Content-Type: application/json" \
  -d '{
    "query": "товари для першокласника",
    "session_id": "test-session",
    "k": 30
  }'

# SSE чат-пошук
curl -N "http://localhost:8080/chat/search/sse?query=іграшки&session_id=test"

# Статистика
curl http://localhost:8080/stats

# Очистити кеш
curl -X POST http://localhost:8080/cache/clear
```

---

## Rate Limits

На даний момент rate limits не встановлені. Рекомендується додати в production:

- `/search`: 60 запитів/хвилину на IP
- `/chat/search`: 30 запитів/хвилину на session
- `/chat/search/sse`: 10 одночасних з'єднань на IP

---

## Changelog

### v1.0.0 (2025-10-13)
- ✅ Початковий реліз API
- ✅ Простий пошук (hybrid, vector, BM25)
- ✅ AI чат-пошук з GPT-4
- ✅ SSE потокова передача
- ✅ Система логування
- ✅ Кешування embeddings
- ✅ Lazy loading результатів

---

**Версія документації:** 1.0.0  
**Дата оновлення:** 13 жовтня 2025

