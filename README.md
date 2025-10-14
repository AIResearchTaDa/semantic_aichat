# 🛍️ Семантичний Пошук Товарів TA-DA!

## 📋 Зміст
- [Опис проекту](#опис-проекту)
- [Основні можливості](#основні-можливості)
- [Архітектура](#архітектура)
- [Технології](#технології)
- [Встановлення та запуск](#встановлення-та-запуск)
- [Конфігурація](#конфігурація)
- [API документація](#api-документація)
- [Структура проекту](#структура-проекту)
- [Розробка](#розробка)
- [Логування та аналітика](#логування-та-аналітика)

---

## 📖 Опис проекту

**Семантичний Пошук Товарів TA-DA!** — це інтелектуальна система пошуку товарів, яка поєднує традиційний пошук з AI-асистентом для надання персонабізованих рекомендацій покупцям.

### Особливості
- 🔍 **Класичний пошук** — швидкий пошук товарів за назвою або категорією
- 🤖 **AI Чат-пошук** — інтелектуальний помічник на базі GPT-4, який розуміє природну мову
- 🎯 **Семантичний аналіз** — використання векторних embeddings (Qwen3-Embedding-8B) для точного пошуку
- 📊 **Гібридний пошук** — комбінація BM25 (текстовий) та векторного пошуку
- 🎨 **Сучасний UI/UX** — адаптивний веб-інтерфейс з привабливим дизайном
- 📈 **Аналітика пошуку** — детальне логування та аналіз якості пошукових запитів

---

## 🌟 Основні можливості

### 1. Класичний пошук
- Швидкий пошук за назвою товару
- Фільтрація за категоріями
- Автодоповнення
- Пагінація результатів

### 2. AI Чат-пошук
- **Розуміння контексту** — GPT-4 аналізує запит та визначає намір користувача
- **Генерація підзапитів** — автоматичне розбиття складних запитів на простіші
- **Рекомендації** — персоналізовані поради на основі знайдених товарів
- **Потокова передача даних** — SSE (Server-Sent Events) для відображення результатів у реальному часі
- **Контекстний діалог** — збереження історії розмови для кращого розуміння

### 3. Семантичний пошук
- **Векторні embeddings** — використання Qwen3-Embedding-8B (4096 вимірів)
- **KNN пошук** — швидкий пошук схожих векторів в Elasticsearch
- **Адаптивна фільтрація** — динамічні пороги для балансу між точністю та повнотою
- **Кешування** — LRU-кеш для embeddings зі збереженням часових міток

### 4. Управління кошиком
- Додавання/видалення товарів
- Повноекранний кошик з детальною інформацією
- Міні-кошики для швидкого доступу
- Підрахунок загальної вартості

---

## 🏗️ Архітектура

```
┌─────────────────┐
│   Веб-клієнт    │
│  (Nginx:8080)   │
└────────┬────────┘
         │
         ├─────────────────────┐
         ▼                     ▼
┌─────────────────┐   ┌──────────────────┐
│  Статичні файли │   │   FastAPI API    │
│   (HTML/CSS/JS) │   │   (Python:8000)  │
└─────────────────┘   └────────┬─────────┘
                               │
         ┌─────────────────────┼─────────────────────┐
         ▼                     ▼                     ▼
┌─────────────────┐   ┌──────────────────┐ ┌──────────────────┐
│  Elasticsearch  │   │  Embedding API   │ │    OpenAI GPT-4  │
│   (векторний    │   │  (Qwen3-8B:9001) │ │  (Рекомендації)  │
│     індекс)     │   │                  │ │                  │
└─────────────────┘   └──────────────────┘ └──────────────────┘
```

### Компоненти

1. **Frontend (Web)**
   - `index.html` — головна сторінка
   - `scripts.js` — логіка додатку
   - `styles.css` — стилі та анімації
   - Використовує Fetch API для взаємодії з backend

2. **Backend (FastAPI)**
   - `main.py` — основний API сервер
   - `search_logger.py` — логування пошукових запитів
   - `reindex_products.py` — інструмент реіндексації

3. **Elasticsearch**
   - Зберігання векторів embeddings
   - KNN пошук
   - BM25 текстовий пошук
   - Плагін для української мови

4. **Nginx**
   - Reverse proxy для API
   - Роздача статичних файлів
   - SSE підтримка для потокової передачі

---

## 💻 Технології

### Backend
- **Python 3.10** — мова програмування
- **FastAPI 0.104.1** — веб-фреймворк
- **Elasticsearch 8.11.0** — пошуковий движок
- **httpx 0.25.2** — HTTP клієнт
- **Pydantic 2.5.0** — валідація даних
- **Tenacity 8.2.3** — retry логіка

### Frontend
- **Vanilla JavaScript** — без фреймворків для швидкості
- **HTML5/CSS3** — сучасний адаптивний дизайн
- **Server-Sent Events (SSE)** — для потокової передачі даних
- **Google Fonts** — шрифти Inter та Poppins

### AI/ML
- **Qwen3-Embedding-8B (Q8_0)** — генерація embeddings (4096 вимірів)
- **OpenAI GPT-4o-mini** — аналіз запитів та рекомендації
- **Ollama** — локальний inference сервер

### Infrastructure
- **Docker Compose** — оркестрація контейнерів
- **Nginx** — веб-сервер та reverse proxy
- **Elasticsearch 8.11.1** — з плагіном для української мови

---

## 🚀 Встановлення та запуск

### Передумови
- Docker та Docker Compose
- Мінімум 4GB RAM для Elasticsearch
- Доступ до Ollama API з моделлю Qwen3-Embedding-8B
- OpenAI API ключ (опціонально, для AI рекомендацій)

### Крок 1: Клонування репозиторію
```bash
git clone <repository-url>
cd EmbeddingsQwen3
```

### Крок 2: Налаштування змінних середовища
Створіть файл `backend/.env`:
```env
# Elasticsearch
ELASTIC_URL=http://elasticsearch-qwen3:9200
INDEX_NAME=products_qwen3_8b

# Embedding API
EMBEDDING_API_URL=http://10.2.0.171:9001/api/embeddings
OLLAMA_MODEL_NAME=dengcao/Qwen3-Embedding-8B:Q8_0
VECTOR_DIMENSION=4096

# OpenAI (опціонально)
OPENAI_API_KEY=your-api-key-here
GPT_MODEL=gpt-4o-mini
ENABLE_GPT_CHAT=true

# TA-DA API
TA_DA_API_TOKEN=your-ta-da-token
TA_DA_DEFAULT_SHOP_ID=8
```

### Крок 3: Створення мережі та volumes
```bash
docker network create embeddingsqwen3_semantic-search-net
docker volume create embeddingsqwen3_elasticsearch-data
```

### Крок 4: Запуск сервісів
```bash
docker-compose up -d
```

### Крок 5: Перевірка здоров'я сервісів
```bash
# Перевірка Elasticsearch
curl http://localhost:9200/_cluster/health

# Перевірка API
curl http://localhost:8080/health
```

### Крок 6: Індексація товарів
```bash
# Якщо потрібно реіндексувати товари
docker exec -it api_qwen3 python reindex_products.py
```

### Крок 7: Відкрийте додаток
Перейдіть на `http://localhost:8080`

---

## ⚙️ Конфігурація

### Backend налаштування (`.env`)

#### Elasticsearch
```env
ELASTIC_URL=http://elasticsearch-qwen3:9200  # URL Elasticsearch
INDEX_NAME=products_qwen3_8b                 # Назва індексу
VECTOR_DIMENSION=4096                         # Розмірність векторів
VECTOR_FIELD_NAME=description_vector          # Назва поля з векторами
```

#### Embeddings
```env
EMBEDDING_API_URL=http://10.2.0.171:9001/api/embeddings
OLLAMA_MODEL_NAME=dengcao/Qwen3-Embedding-8B:Q8_0
EMBED_CACHE_SIZE=2000                         # Розмір LRU кешу
CACHE_TTL_SECONDS=3600                        # Час життя кешу
EMBEDDING_MAX_CONCURRENT=2                    # Макс. паралельних запитів
```

#### Пошук
```env
KNN_NUM_CANDIDATES=500                        # Кандидатів для KNN
HYBRID_ALPHA=0.7                              # Вага векторного пошуку (0-1)
HYBRID_FUSION=weighted                        # Метод об'єднання (weighted/rrf)
BM25_MIN_SCORE=5.0                            # Мінімальний BM25 score
```

#### GPT
```env
OPENAI_API_KEY=sk-...                         # OpenAI API ключ
GPT_MODEL=gpt-4o-mini                         # Модель GPT
ENABLE_GPT_CHAT=true                          # Увімкнути AI чат
GPT_TEMPERATURE=0.3                           # Температура генерації
GPT_MAX_TOKENS_ANALYZE=250                    # Токенів для аналізу
GPT_MAX_TOKENS_RECO=500                       # Токенів для рекомендацій
GPT_ANALYZE_TIMEOUT_SECONDS=10.0              # Таймаут аналізу
GPT_RECO_TIMEOUT_SECONDS=15.0                 # Таймаут рекомендацій
```

#### Чат-пошук
```env
CHAT_SEARCH_SCORE_THRESHOLD_RATIO=0.4         # Відношення до max score
CHAT_SEARCH_MIN_SCORE_ABSOLUTE=0.3            # Абсолютний мінімум score
CHAT_SEARCH_SUBQUERY_WEIGHT_DECAY=0.85        # Зменшення ваги підзапитів
CHAT_SEARCH_MAX_K_PER_SUBQUERY=20             # Макс товарів на підзапит
```

#### Lazy Loading
```env
INITIAL_PRODUCTS_BATCH=20                     # Початкова кількість товарів
LOAD_MORE_BATCH_SIZE=20                       # Розмір batch при догрузці
SEARCH_RESULTS_TTL_SECONDS=3600               # Час зберігання результатів
```

#### Рекомендації
```env
RECO_DETAILED_COUNT=3                         # К-сть детальних рекомендацій
GROUNDED_RECOMMENDATIONS=true                 # Базувати на знайдених товарах
```

---

## 📡 API документація

### 1. Health Check
```http
GET /health
```
**Відповідь:**
```json
{
  "status": "healthy",
  "elasticsearch": "connected",
  "timestamp": "2025-10-13T10:00:00"
}
```

### 2. Конфігурація
```http
GET /config
```
**Відповідь:**
```json
{
  "streaming_enabled": true,
  "gpt_enabled": true
}
```

### 3. Простий пошук
```http
POST /search
Content-Type: application/json

{
  "query": "олівці кольорові",
  "k": 20,
  "search_type": "hybrid"
}
```

**Параметри:**
- `query` (string, обов'язковий) — пошуковий запит
- `k` (int, опціонально) — кількість результатів (за замовчуванням 20)
- `search_type` (string) — тип пошуку: `"hybrid"`, `"vector"`, `"bm25"`

**Відповідь:**
```json
{
  "results": [
    {
      "uuid": "prod-123",
      "title_ua": "Олівці кольорові 24 кольори",
      "description_ua": "Набір олівців для малювання",
      "score": 0.95,
      "image_url": "https://..."
    }
  ],
  "query": "олівці кольорові",
  "total": 42,
  "search_type": "hybrid"
}
```

### 4. AI Чат-пошук (SSE)
```http
GET /chat/search/sse?query=що+подарувати+дитині+5+років&session_id=abc123
```

**Параметри:**
- `query` (string) — пошуковий запит
- `session_id` (string) — ідентифікатор сесії
- `dialog_context` (string, опціонально) — JSON контексту діалогу

**Формат SSE події:**
```
event: intent
data: {"intent": "product_search", "clarification": null}

event: subquery
data: {"subquery": "іграшки для 5 років", "index": 0}

event: product
data: {"product": {...}, "score": 0.89, "recommended": true}

event: recommendation
data: {"recommendation": "Рекомендую конструктор LEGO..."}

event: done
data: {"total_products": 15, "search_time_ms": 1234}
```

### 5. Чат-пошук (POST)
```http
POST /chat/search
Content-Type: application/json

{
  "query": "товари для школи",
  "session_id": "session-123",
  "k": 50
}
```

**Відповідь:**
```json
{
  "intent": "product_search",
  "clarification": null,
  "subqueries": [
    "зошити шкільні",
    "ручки олівці",
    "пенали папки"
  ],
  "products": [...],
  "recommendations": [...],
  "dialog_context": {...},
  "total_found": 45,
  "search_time_ms": 890
}
```

### 6. Завантаження додаткових товарів
```http
POST /chat/search/load-more
Content-Type: application/json

{
  "session_id": "session-123",
  "offset": 20,
  "limit": 20
}
```

### 7. Статистика пошуку
```http
GET /stats
```

**Відповідь:**
```json
{
  "total_searches": 1523,
  "cache_hits": 456,
  "cache_misses": 789,
  "cache_hit_rate": 0.366,
  "avg_search_time_ms": 234.5,
  "total_products_indexed": 12456
}
```

### 8. Очищення кешу
```http
POST /cache/clear
```

### 9. Статистика кешу
```http
GET /cache/stats
```

### 10. Проксі зображень
```http
GET /api/image-proxy?url=https://example.com/image.jpg
```

### 11. Логи пошуку

#### Отримати всі сесії
```http
GET /search-logs/sessions
```

#### Отримати логи сесії
```http
GET /search-logs/session/{session_id}
```

#### Звіт по сесії
```http
GET /search-logs/report/{session_id}
```

#### Експорт звітів
```http
GET /search-logs/export
```

#### Статистика логів
```http
GET /search-logs/stats
```

---

## 📁 Структура проекту

```
EmbeddingsQwen3/
│
├── backend/                          # Backend додаток
│   ├── main.py                       # Головний FastAPI додаток
│   ├── search_logger.py              # Модуль логування пошуку
│   ├── reindex_products.py           # Скрипт реіндексації
│   ├── requirements.txt              # Python залежності
│   ├── Dockerfile                    # Docker образ для API
│   ├── .env                          # Змінні середовища
│   ├── products.json                 # Дані товарів
│   └── search_logs/                  # Логи пошукових запитів
│       ├── search_queries.json       # JSON логи
│       └── search_queries_readable.txt # Читабельні логи
│
├── web/                              # Frontend додаток
│   ├── index.html                    # Головна сторінка
│   ├── scripts.js                    # JavaScript логіка
│   ├── styles.css                    # CSS стилі
│   └── images/                       # Зображення та іконки
│       ├── logo_aitada.png
│       ├── logo_aitada4.png
│       ├── icon_ai2.png
│       ├── icon_search.png
│       └── tada_logo2.png
│
├── elasticsearch/                    # Elasticsearch конфігурація
│   └── Dockerfile                    # Dockerfile з українським плагіном
│
├── docker-compose.yml                # Docker Compose конфігурація
├── nginx.conf                        # Nginx конфігурація
└── README.md                         # Документація проекту
```

---

## 🔧 Розробка

### Локальний запуск backend
```bash
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### Перегляд логів
```bash
# Всі сервіси
docker-compose logs -f

# Конкретний сервіс
docker-compose logs -f api
docker-compose logs -f elasticsearch-qwen3
docker-compose logs -f nginx
```

### Відлагодження

#### Перевірка Elasticsearch індексу
```bash
# Інформація про індекс
curl http://localhost:9200/products_qwen3_8b

# Кількість документів
curl http://localhost:9200/products_qwen3_8b/_count

# Приклад документа
curl http://localhost:9200/products_qwen3_8b/_search?size=1
```

#### Перевірка embeddings API
```bash
curl -X POST http://10.2.0.171:9001/api/embeddings \
  -H "Content-Type: application/json" \
  -d '{
    "model": "dengcao/Qwen3-Embedding-8B:Q8_0",
    "prompt": "тестовий запит"
  }'
```

#### Тестування API endpoints
```bash
# Health check
curl http://localhost:8080/health

# Простий пошук
curl -X POST http://localhost:8080/search \
  -H "Content-Type: application/json" \
  -d '{"query": "олівці", "k": 5}'

# SSE чат-пошук
curl -N http://localhost:8080/chat/search/sse?query=іграшки&session_id=test
```

### Реіндексація товарів
```bash
# Запустити реіндексацію
docker exec -it api_qwen3 python reindex_products.py

# Подивитися логи реіндексації
docker exec -it api_qwen3 tail -f /app/indexing.log
```

---

## 📊 Логування та аналітика

### Модуль SearchLogger

Система автоматично логує всі чат-пошукові запити з детальною інформацією:

**Що логується:**
- Timestamp запиту
- ID сесії користувача
- Оригінальний запит
- Визначений intent (product_search, clarification, invalid)
- Згенеровані підзапити
- Статистика пошуку:
  - Загальна кількість знайдених товарів
  - Кількість після фільтрації
  - Відсоток фільтрації
  - Максимальний score
  - Використані пороги фільтрації
  - Час виконання пошуку
- Топ товари з їх scores
- Рекомендовані товари
- Категорії товарів
- Додаткова інформація

### Формати логів

#### JSON формат (`search_logs/search_queries.json`)
Структурований формат для програмної обробки:
```json
{
  "timestamp": "2025-10-13T10:15:30",
  "session_id": "abc-123",
  "query": "товари для школи",
  "intent": "product_search",
  "subqueries": ["зошити", "ручки"],
  "search_stats": {
    "total_found": 45,
    "after_filtering": 28,
    "filtering_rate": 0.622,
    "max_score": 0.956,
    "threshold_final": 0.382,
    "search_time_ms": 890.5
  },
  "top_products": [...],
  "additional_info": {...}
}
```

#### Читабельний формат (`search_logs/search_queries_readable.txt`)
Форматований текст для швидкого аналізу:
```
====================================================================================================
                                    ЛОГИ ПОШУКОВИХ ЗАПИТІВ                                        
                                  Згенеровано: 2025-10-13 10:15:30                                
====================================================================================================

📱 СЕСІЯ: abc-123
📊 Кількість запитів в сесії: 5
🕐 Перший запит: 2025-10-13T10:10:00
🕐 Останній запит: 2025-10-13T10:15:30

  ────────────────────────────────────────────────────────────────────────────────────────────────
  Запит #1
  ────────────────────────────────────────────────────────────────────────────────────────────────
  🕐 Час:        2025-10-13T10:10:00
  🔍 Запит:      товари для школи першокласнику
  🎯 Тип:        product_search
  
  📊 СТАТИСТИКА:
     • Знайдено товарів:    45
     • Після фільтрації:    28 (62.2%)
     • Max score:           0.9560
     • Поріг фільтрації:    0.3824
     • Час пошуку:          890 мс
  
  🔎 ПІДЗАПИТИ (3):
     1. зошити шкільні
     2. ручки олівці
     3. пенали папки
  
  🏆 ТОП-10 ТОВАРІВ:
     ⭐  1. [0.9560] Зошит шкільний 12 аркушів лінія
     ⭐  2. [0.9234] Ручка кулькова синя
        3. [0.8901] Олівці кольорові 24 кольори
     ...
```

### Аналітика сесій

Система генерує звіти по сесіях з аналітикою:

```bash
# Отримати звіт по сесії
curl http://localhost:8080/search-logs/report/session-123

# Експортувати всі сесії
curl http://localhost:8080/search-logs/export
```

**Метрики:**
- Середній час пошуку
- Середня кількість знайдених товарів
- Середній відсоток фільтрації
- Розподіл scores (мін/макс/середній)
- Історія всіх запитів у сесії

---

## 🎯 Алгоритми пошуку

### Гібридний пошук (Hybrid Search)

Комбінує векторний та текстовий пошук для найкращих результатів:

1. **Векторний пошук (KNN)**
   - Генерація embedding для запиту
   - Пошук k найближчих сусідів в векторному просторі
   - Cosine similarity для визначення схожості

2. **Текстовий пошук (BM25)**
   - Повнотекстовий пошук в Elasticsearch
   - Підтримка української морфології
   - Boosting за полями (title > description)

3. **Об'єднання результатів**
   - **Weighted fusion**: `final_score = α * vector_score + (1-α) * bm25_score`
   - **RRF** (Reciprocal Rank Fusion): комбінування за рангами
   - Параметр `HYBRID_ALPHA` контролює баланс

### Адаптивна фільтрація

Система автоматично визначає оптимальний поріг фільтрації:

```python
# Базові пороги
threshold_ratio = 0.4      # 40% від max_score
min_absolute = 0.3         # Абсолютний мінімум

# Динамічний поріг
dynamic_threshold = max_score * threshold_ratio

# Адаптивний мінімум
adaptive_min = min(dynamic_threshold, min_absolute)

# Фінальний поріг
final_threshold = max(adaptive_min, min_absolute)
```

Це забезпечує:
- Високу точність при великій кількості релевантних результатів
- Достатню повноту при малій кількості результатів
- Захист від повернення нерелевантних товарів

### AI Аналіз запитів

GPT-4 аналізує запити користувачів:

1. **Визначення intent**:
   - `product_search` — пошук товарів
   - `clarification` — потрібні уточнення
   - `invalid` — нерелевантний запит

2. **Генерація підзапитів**:
   - Розбиття складних запитів
   - Оптимізація для семантичного пошуку
   - Максимум 5 підзапитів

3. **Рекомендації**:
   - Аналіз знайдених товарів
   - Персоналізовані поради
   - Grounded в реальних товарах

---

## 🔐 Безпека

### CORS
```python
# Дозволені origins
origins = ["*"]  # В продакшені обмежити до конкретних доменів

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

### Rate Limiting
Рекомендується додати rate limiting для production:
```python
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

@app.post("/search")
@limiter.limit("60/minute")
async def search(...):
    ...
```

### Валідація вхідних даних
Pydantic моделі забезпечують валідацію:
```python
class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=500)
    k: int = Field(default=20, ge=1, le=100)
    search_type: str = Field(default="hybrid")
```

---

## 📈 Продуктивність

### Оптимізації

1. **Кешування embeddings**
   - LRU кеш на 2000 елементів
   - TTL: 1 година
   - Хеш MD5 для ключів

2. **Lazy loading**
   - Початкова партія: 20 товарів
   - Дозагрузка: 20 товарів
   - Кешування результатів на 1 годину

3. **Пагінація**
   - Elasticsearch search_after
   - Ефективна для великих результатів

4. **Асинхронність**
   - AsyncIO для I/O операцій
   - Семафор для контролю конкурентності
   - Batch обробка embeddings

### Моніторинг

```bash
# CPU та Memory
docker stats

# Elasticsearch health
curl http://localhost:9200/_cluster/health?pretty

# API метрики
curl http://localhost:8080/stats
```

---

## 🐛 Відлагодження проблем

### Проблема: Elasticsearch не запускається
```bash
# Перевірити логи
docker-compose logs elasticsearch-qwen3

# Збільшити vm.max_map_count
sudo sysctl -w vm.max_map_count=262144

# Перевірити простір на диску
df -h
```

### Проблема: Embeddings API недоступний
```bash
# Перевірити з'єднання
curl http://10.2.0.171:9001/api/embeddings

# Перевірити Ollama модель
docker exec ollama ollama list
```

### Проблема: Повільний пошук
```bash
# Перевірити кеш
curl http://localhost:8080/cache/stats

# Збільшити розмір кешу
EMBED_CACHE_SIZE=5000  # у .env

# Оптимізувати ES
curl -X PUT http://localhost:9200/products_qwen3_8b/_settings \
  -H "Content-Type: application/json" \
  -d '{"index": {"refresh_interval": "30s"}}'
```

---

## 📝 Ліцензія

Цей проект є власністю TA-DA! та призначений для внутрішнього використання.

---

## 👥 Автори та підтримка

Розроблено для **TA-DA!** — мережі магазинів товарів для дому та родини.

Для питань та підтримки:
- Email: support@ta-da.net.ua
- Website: https://ta-da.net.ua

---

## 🎉 Подяки

- **Qwen Team** — за чудову embedding модель
- **OpenAI** — за GPT-4 API
- **Elasticsearch** — за потужний пошуковий движок
- **FastAPI** — за швидкий та сучасний фреймворк

---

**Версія:** 1.0.0  
**Дата оновлення:** 13 жовтня 2025  
**Статус:** Production Ready ✅

