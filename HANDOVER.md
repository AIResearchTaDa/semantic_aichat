# 🛍️ Семантичний пошук TA-DA — Документація для передачі проекту

## 📖 Про проект

**Інтелігентна система пошуку товарів** для магазинів TA-DA з AI-асистентом.

### Що вміє система:

1. **Простий пошук** — звичайний пошук за назвою товару ("олівці кольорові")
2. **AI чат-пошук** — розумний помічник, який розуміє питання ("Що подарувати дитині на 5 років?")
3. **Персональні рекомендації** — пропонує додаткові товари на основі кошика
4. **Аналітика** — зберігає та аналізує всі пошукові запити

### Технології:

- **Frontend:** HTML/CSS/JavaScript (без фреймворків)
- **Backend:** Python + FastAPI
- **База даних:** Elasticsearch 8.11 (з українською морфологією)
- **AI:**
  - Qwen3-Embedding-8B — для розуміння значення тексту (векторні ембединги)
  - GPT-4o-mini — для аналізу запитів та рекомендацій
- **Інфраструктура:** Docker Compose

---

## 📁 Структура проекту

```
EmbeddingsQwen3/
│
├── 📂 backend/                      # BACKEND (Python)
│   │
│   ├── main.py                      # Головний файл API (~3150 рядків)
│   │   ├── Endpoints (API методи)
│   │   ├── SearchEngine (логіка пошуку)
│   │   ├── GPTIntegration (робота з AI)
│   │   ├── EmbeddingManager (генерація векторів)
│   │   └── Cache (кешування для швидкості)
│   │
│   ├── search_logger.py             # Логування пошукових запитів
│   │   └── SearchLogger (зберігає всі запити користувачів)
│   │
│   ├── reindex_products.py          # Індексація товарів в Elasticsearch
│   │   └── Завантажує товари з JSON → Elasticsearch
│   │
│   ├── requirements.txt             # Список Python бібліотек
│   ├── Dockerfile                   # Як збудувати Docker образ
│   ├── .env                         # ВАЖЛИВО! Конфігурація (токени, налаштування)
│   │
│   ├── products.json                # База товарів (JSON)
│   │
│   └── 📂 search_logs/              # Логи пошукових запитів
│       ├── search_queries.json      # JSON формат (для програм)
│       └── search_queries_readable.txt  # Читабельний формат (для людей)
│
├── 📂 web/                          # FRONTEND (HTML/CSS/JS)
│   │
│   ├── index.html                   # Головна сторінка (структура)
│   │   ├── Привітальна сторінка
│   │   ├── Сторінка простого пошуку
│   │   ├── Сторінка AI чат-пошуку
│   │   └── Модальні вікна (кошик, зображення)
│   │
│   ├── scripts.js                   # Вся логіка frontend (~4400 рядків)
│   │   ├── Простий пошук
│   │   ├── AI чат-пошук (SSE stream)
│   │   ├── Відображення товарів
│   │   ├── Кошик
│   │   ├── Рекомендації
│   │   └── Lazy loading (догрузка товарів)
│   │
│   ├── styles.css                   # Всі стилі (~2700 рядків)
│   │   ├── Дизайн сторінок
│   │   ├── Анімації
│   │   ├── Адаптивність (mobile/tablet/desktop)
│   │   └── Теми та кольори
│   │
│   └── 📂 images/                   # Логотипи та іконки
│       ├── logo_aitada.png          # Головний логотип AI
│       ├── icon_ai2.png             # Іконка AI
│       └── icon_search.png          # Іконка пошуку
│
├── 📂 elasticsearch/                # ELASTICSEARCH
│   └── Dockerfile                   # ES з плагіном української мови
│
├── docker-compose.yml               # Конфігурація всіх сервісів
├── nginx.conf                       # Налаштування веб-сервера
│
└── 📂 docs/                         # Додаткова документація
    ├── API_DOCUMENTATION.md
    ├── ARCHITECTURE.md
    ├── DEPLOYMENT_GUIDE.md
    └── FAQ.md
```

### Що знаходиться в кожному файлі:

#### `backend/main.py` — мозок системи

```python
# Основні класи:

class Settings:           # Всі налаштування з .env

class EmbeddingManager:   # Генерує векторні представлення тексту
    └── generate_embedding(text)  # "олівці" → [0.23, -0.45, 0.67, ...]

class GPTIntegration:     # Робота з ChatGPT
    ├── analyze_query()   # Аналізує запит користувача
    └── generate_recommendations()  # Генерує рекомендації

class SearchEngine:       # Головна логіка пошуку
    ├── hybrid_search()   # Комбінований пошук (текст + вектори)
    ├── vector_search()   # Тільки векторний пошук
    └── bm25_search()     # Тільки текстовий пошук

class LRUCache:          # Кеш для швидкості
    └── Зберігає результати, щоб не перераховувати

# API endpoints (що можна викликати):
POST /search                  # Простий пошук
POST /chat-search             # AI чат-пошук
GET  /chat/search/sse         # AI пошук з потоковою передачею
POST /recommendations         # Рекомендації на основі кошика
GET  /health                  # Перевірка здоров'я системи
GET  /stats                   # Статистика
POST /cache/clear             # Очистити кеш
```

#### `web/scripts.js` — логіка інтерфейсу

```javascript
// Основні функції:

performSimpleSearch()        // Простий пошук
performChatSearch()          // AI чат-пошук
handleSSEStream()            // Обробка потоку даних від AI
renderProductCard()          // Малює картку товару
addToCart()                  // Додати в кошик
updateCartUI()               // Оновити відображення кошика
loadMoreProducts()           // Догрузити ще товари
```

---

## 🔧 Як працює система (архітектура)

### Схема взаємодії компонентів:

```
КОРИСТУВАЧ
    ↓ (відкриває браузер)
┌─────────────────────────────────┐
│    NGINX (порт 8080)            │  ← Веб-сервер
│  - Віддає HTML/CSS/JS           │
│  - Проксує запити до API        │
└────────┬────────────────────────┘
         │
         ├─── Статичні файли (web/) → Відображає сторінку
         │
         └─── API запити (/search, /chat-search) →
                ↓
         ┌──────────────────────────┐
         │  FastAPI (порт 8000)     │  ← Python Backend
         │  - Обробка запитів       │
         │  - Логіка пошуку         │
         └────┬──────────┬──────────┘
              │          │
              │          └─────→ ЗОВНІШНІ API:
              │                  ├─ OpenAI GPT-4 (рекомендації)
              │                  └─ Embedding API (вектори)
              ↓
         ┌──────────────────────────┐
         │  Elasticsearch (9200)    │  ← База даних
         │  - Зберігає товари       │
         │  - Векторний пошук (kNN) │
         │  - Текстовий пошук (BM25)│
         └──────────────────────────┘
```

### Приклад роботи AI чат-пошуку:

```
1. Користувач: "Що подарувати дитині на 5 років?"
   
2. Frontend (scripts.js):
   └─→ Відправляє запит на /chat/search/sse
   
3. Backend (main.py):
   ├─→ GPTIntegration: Аналізує запит
   │   └─→ Результат: "product_search" (шукати товари)
   │   └─→ Підзапити: ["іграшки для 5 років", "розвиваючі ігри", "конструктори"]
   │
   ├─→ EmbeddingManager: Генерує вектори для кожного підзапиту
   │   └─→ "іграшки для 5 років" → [0.12, -0.34, 0.56, ...]
   │
   ├─→ SearchEngine: Шукає в Elasticsearch
   │   ├─→ Векторний пошук (схожість за змістом)
   │   ├─→ Текстовий пошук (співпадіння слів)
   │   └─→ Об'єднує результати
   │
   ├─→ Фільтрація: Залишає тільки релевантні товари
   │
   └─→ GPTIntegration: Генерує рекомендації
       └─→ "Рекомендую конструктор LEGO Duplo — ідеально для цього віку..."
   
4. Frontend отримує:
   ├─→ Товари (по одному, в реальному часі)
   └─→ Рекомендації AI

5. Відображає результати користувачу
```

---

## 🚀 Як запустити проект

### Крок 1: Підготовка

```bash
# Перейти в директорію проекту
cd /var/docker/AI/EmbeddingsQwen3

# Створити мережу Docker (щоб контейнери бачили один одного)
docker network create embeddingsqwen3_semantic-search-net

# Створити volume (для збереження даних Elasticsearch)
docker volume create embeddingsqwen3_elasticsearch-data
```

### Крок 2: Налаштувати .env файл

Створити файл `backend/.env` з такими параметрами:

```env
#========================================
# ОБОВ'ЯЗКОВІ НАЛАШТУВАННЯ
#========================================

# Elasticsearch (база даних для пошуку)
ELASTIC_URL=http://elasticsearch-qwen3:9200
INDEX_NAME=products_qwen3_8b

# Embedding API (генерація векторів) — ЗАМІНИТИ на свій IP!
EMBEDDING_API_URL=http://10.2.0.171:9001/api/embeddings
OLLAMA_MODEL_NAME=dengcao/Qwen3-Embedding-8B:Q8_0

# OpenAI (для AI асистента) — ВСТАВИТИ свій ключ!
OPENAI_API_KEY=sk-proj-your-actual-key-here
ENABLE_GPT_CHAT=true
GPT_MODEL=gpt-4o-mini

# TA-DA API (дані товарів) — ВСТАВИТИ токен!
TA_DA_API_TOKEN=your-ta-da-token-here
TA_DA_API_BASE_URL=https://api.ta-da.net.ua/v1.2/mobile
TA_DA_DEFAULT_SHOP_ID=8

#========================================
# ОПЦІОНАЛЬНІ (можна залишити як є)
#========================================

# Налаштування пошуку
HYBRID_ALPHA=0.7                    # Вага векторного пошуку (0.0 = тільки текст, 1.0 = тільки вектори)
KNN_NUM_CANDIDATES=500              # Скільки кандидатів брати для векторного пошуку
BM25_MIN_SCORE=5.0                  # Мінімальний score для текстового пошуку

# Продуктивність
EMBED_CACHE_SIZE=2000               # Скільки векторів зберігати в кеші
CACHE_TTL_SECONDS=3600              # Час життя кешу (1 година)
EMBEDDING_MAX_CONCURRENT=2          # Скільки векторів генерувати одночасно

# Інтерфейс
INITIAL_PRODUCTS_BATCH=20           # Скільки товарів показувати спочатку
LOAD_MORE_BATCH_SIZE=20             # Скільки товарів підвантажувати при прокрутці
```

### Крок 3: Запустити

```bash
# Запустити всі сервіси (Elasticsearch, API, Nginx)
docker-compose up -d

# Перевірити, що все запустилося
docker-compose ps

# Повинно бути:
# elasticsearch-qwen3   Up (healthy)
# api_qwen3             Up
# tada-nginx            Up
```

### Крок 4: Завантажити товари

```bash
# Індексувати товари (перший раз або повна переіндексація)
docker exec -it api_qwen3 python reindex_products.py

# Прогрес буде показано в консолі
# Після завершення товари будуть в Elasticsearch
```

### Крок 5: Перевірити

```bash
# Перевірити здоров'я API
curl http://localhost:8080/health

# Відповідь повинна бути:
# {"status": "healthy", "elasticsearch": "connected", ...}

# Відкрити в браузері
open http://localhost:8080
```

**Готово!** Система працює на `http://localhost:8080`

---

## 💡 Що можна робити з проектом

### 1. Переглядати логи пошуку

```bash
# Читабельні логи (для людей)
docker exec -it api_qwen3 cat search_logs/search_queries_readable.txt

# JSON логи (для програмної обробки)
docker exec -it api_qwen3 cat search_logs/search_queries.json

# Через API (отримати логи конкретної сесії)
curl http://localhost:8080/search-logs/session/YOUR-SESSION-ID

# Статистика всіх пошуків
curl http://localhost:8080/search-logs/stats
```

**Що логується:**
- Всі запити користувачів
- Знайдені товари та їх score
- Скільки часу зайняв пошук
- Які підзапити згенерував AI
- Рекомендації

### 2. Додавати/оновлювати товари

**Варіант А: Оновити існуючі товари**

```bash
# 1. Відредагувати backend/products.json
nano backend/products.json

# 2. Реіндексувати (без видалення старих)
docker exec -it api_qwen3 python reindex_products.py --update
```

**Варіант Б: Повна переіндексація**

```bash
# Видалить старий індекс та створить новий
docker exec -it api_qwen3 python reindex_products.py
```

**Варіант В: Завантажити з файлу**

```bash
# Якщо файл товарів в іншому місці
docker exec -it api_qwen3 python reindex_products.py --file /path/to/new_products.json
```

### 3. Налаштовувати алгоритм пошуку

**Зміна балансу між текстовим та векторним пошуком:**

```env
# У файлі backend/.env

# Більше ваги векторному пошуку (краще розуміє сенс)
HYBRID_ALPHA=0.8

# Більше ваги текстовому пошуку (краще шукає точні слова)
HYBRID_ALPHA=0.3

# Порівну
HYBRID_ALPHA=0.5
```

**Зміна фільтрації результатів:**

```env
# Показувати тільки дуже релевантні товари
CHAT_SEARCH_SCORE_THRESHOLD_RATIO=0.6

# Показувати більше товарів (менш строга фільтрація)
CHAT_SEARCH_SCORE_THRESHOLD_RATIO=0.3
```

### 4. Змінювати промпти для AI

Файл: `backend/main.py`

**Промпт для аналізу запитів:**

```python
# Знайти метод: _build_analyze_system_prompt()
# Приблизно рядок 1100

def _build_analyze_system_prompt(self) -> str:
    return """
    Ти — асистент для інтернет-магазину TA-DA.
    
    Твоє завдання: проаналізувати запит користувача...
    
    # МОЖНА ЗМІНИТИ ЦЕЙПРОМПТ
    """
```

**Промпт для рекомендацій:**

```python
# Знайти метод: _build_recommendation_system_prompt()
# Приблизно рядок 1300

def _build_recommendation_system_prompt(self) -> str:
    return """
    На основі знайдених товарів дай персоналізовані рекомендації...
    
    # МОЖНА ЗМІНИТИ ЦЕЙ ПРОМПТ
    """
```

Після змін:

```bash
docker-compose restart api
```

### 5. Змінювати дизайн

**Кольори та стилі:**

```css
/* Файл: web/styles.css */

:root {
    --primary-color: #4a90e2;      /* Головний колір */
    --secondary-color: #7b68ee;    /* Вторинний колір */
    --background: #f8f9fa;         /* Фон */
    /* Можна змінити будь-який колір */
}
```

**Текст на сторінках:**

```html
<!-- Файл: web/index.html -->

<!-- Знайти та змінити будь-який текст -->
<h1>Семантичний пошук TA-DA!</h1>
```

Зміни застосуються автоматично (перезавантажити сторінку в браузері).

### 6. Моніторити систему

```bash
# Статистика API
curl http://localhost:8080/stats

# Статистика кешу
curl http://localhost:8080/cache/stats

# Здоров'я Elasticsearch
curl http://localhost:9200/_cluster/health?pretty

# Скільки товарів в індексі
curl http://localhost:9200/products_qwen3_8b/_count

# Використання ресурсів Docker
docker stats
```

### 7. Робити бекапи

```bash
# Бекап логів
docker cp api_qwen3:/app/search_logs ./backup_logs_$(date +%Y%m%d)

# Бекап товарів
docker cp api_qwen3:/app/products.json ./backup_products.json

# Експорт індексу Elasticsearch
curl -X PUT "localhost:9200/_snapshot/backup_repo/snapshot_$(date +%Y%m%d)?wait_for_completion=true"
```

### 8. Тестувати API

```bash
# Простий пошук
curl -X POST http://localhost:8080/search \
  -H "Content-Type: application/json" \
  -d '{
    "query": "олівці кольорові",
    "k": 10,
    "search_type": "hybrid"
  }'

# AI чат-пошук
curl -N http://localhost:8080/chat/search/sse?query=подарунок+дитині&session_id=test123

# Рекомендації
curl -X POST http://localhost:8080/recommendations \
  -H "Content-Type: application/json" \
  -d '{
    "cart_items": [
      {"uuid": "123", "title_ua": "Олівці кольорові"}
    ],
    "session_id": "test"
  }'
```

---

## 🔍 Корисні команди

### Робота з Docker

```bash
# Подивитись логи
docker-compose logs -f                    # Всі сервіси
docker-compose logs -f api                # Тільки API
docker-compose logs -f elasticsearch      # Тільки Elasticsearch
docker-compose logs --tail=100 api        # Останні 100 рядків

# Перезапустити
docker-compose restart api                # Тільки API
docker-compose restart                    # Все

# Зупинити
docker-compose stop                       # Зупинити (дані зберігаються)
docker-compose down                       # Зупинити та видалити контейнери
docker-compose down -v                    # УВАГА! Видалить також дані Elasticsearch

# Перебудувати
docker-compose build --no-cache           # Перебудувати образи
docker-compose up -d --build              # Перебудувати та запустити
```

### Робота з API контейнером

```bash
# Увійти в контейнер
docker exec -it api_qwen3 bash

# Подивитись змінні середовища
docker exec -it api_qwen3 env

# Переглянути файли
docker exec -it api_qwen3 ls -la

# Подивитись логи Python
docker exec -it api_qwen3 cat /app/app.log

# Запустити Python команду
docker exec -it api_qwen3 python -c "print('Hello')"
```

### Робота з Elasticsearch

```bash
# Інформація про кластер
curl http://localhost:9200

# Список індексів
curl http://localhost:9200/_cat/indices?v

# Інформація про індекс товарів
curl http://localhost:9200/products_qwen3_8b

# Скільки документів
curl http://localhost:9200/products_qwen3_8b/_count

# Приклад документа
curl http://localhost:9200/products_qwen3_8b/_search?size=1&pretty

# Видалити індекс (УВАГА! Видалить всі товари)
curl -X DELETE http://localhost:9200/products_qwen3_8b

# Очистити кеш Elasticsearch
curl -X POST http://localhost:9200/products_qwen3_8b/_cache/clear
```

---

## ⚠️ Типові проблеми та рішення

### Проблема 1: Elasticsearch не запускається

**Симптоми:**

```bash
docker-compose logs elasticsearch
# Error: max virtual memory areas vm.max_map_count [65530] is too low
```

**Рішення:**

```bash
# Збільшити vm.max_map_count
sudo sysctl -w vm.max_map_count=262144

# Зробити постійним (щоб не скидалось після перезавантаження)
echo "vm.max_map_count=262144" | sudo tee -a /etc/sysctl.conf
```

### Проблема 2: API не може з'єднатися з Elasticsearch

**Симптоми:**

```bash
curl http://localhost:8080/health
# {"elasticsearch": "disconnected"}
```

**Рішення:**

```bash
# 1. Перевірити, що Elasticsearch запущений
docker-compose ps
curl http://localhost:9200

# 2. Перевірити мережу
docker network inspect embeddingsqwen3_semantic-search-net

# 3. Перезапустити API
docker-compose restart api
```

### Проблема 3: Embedding API недоступний

**Симптоми:**

```bash
docker-compose logs api
# Error connecting to embedding API: Connection refused
```

**Рішення:**

```bash
# 1. Перевірити доступність Embedding API
curl http://10.2.0.171:9001/api/embeddings

# 2. Якщо IP змінився — оновити .env
nano backend/.env
# EMBEDDING_API_URL=http://NEW-IP:9001/api/embeddings

# 3. Перезапустити
docker-compose restart api
```

### Проблема 4: Повільний пошук

**Рішення:**

```env
# У backend/.env збільшити кеш

EMBED_CACHE_SIZE=5000              # Більший кеш векторів
EMBEDDING_MAX_CONCURRENT=5         # Більше паралельних запитів
```

```bash
# Очистити старий кеш
curl -X POST http://localhost:8080/cache/clear

# Перезапустити
docker-compose restart api
```

### Проблема 5: GPT не працює

**Симптоми:**

```bash
docker-compose logs api | grep GPT
# OpenAI API error: Invalid API key
```

**Рішення:**

```bash
# 1. Перевірити API key
docker exec -it api_qwen3 env | grep OPENAI_API_KEY

# 2. Оновити ключ у .env
nano backend/.env
# OPENAI_API_KEY=sk-proj-your-new-key

# 3. Перезапустити
docker-compose restart api
```

### Проблема 6: Нерелевантні результати

**Рішення 1: Підвищити поріг фільтрації**

```env
# backend/.env
CHAT_SEARCH_SCORE_THRESHOLD_RATIO=0.5   # Більш строга фільтрація
```

**Рішення 2: Змінити баланс пошуку**

```env
# Більше ваги текстовому пошуку (точні співпадіння)
HYBRID_ALPHA=0.4

# Або більше векторному (семантична схожість)
HYBRID_ALPHA=0.8
```

---

## 📊 Що контролювати в production

### Щодня:

```bash
# Перевірити статус
docker-compose ps

# Перевірити здоров'я
curl http://localhost:8080/health

# Подивитись логи помилок
docker-compose logs --tail=100 api | grep ERROR
```

### Щотижня:

```bash
# Статистика пошуку
curl http://localhost:8080/stats

# Статистика Elasticsearch
curl http://localhost:9200/_cluster/stats?pretty

# Розмір індексу
curl http://localhost:9200/_cat/indices?v

# Бекап логів
docker cp api_qwen3:/app/search_logs ./backup_logs_$(date +%Y%m%d)
```

### Щомісяця:

```bash
# Повний бекап
docker cp api_qwen3:/app/search_logs ./monthly_backup/
docker cp api_qwen3:/app/products.json ./monthly_backup/

# Очистити старі логи (якщо потрібно)
docker exec -it api_qwen3 rm search_logs/search_queries.json
docker exec -it api_qwen3 rm search_logs/search_queries_readable.txt
docker-compose restart api
```

### Метрики для відстеження:

- **Response time:** < 2 сек (простий пошук), < 10 сек (AI пошук)
- **Cache hit rate:** > 60%
- **Elasticsearch heap:** < 75%
- **Disk space:** > 20% вільного місця

---

## 📝 Чеклист передачі проекту

### Технічна підготовка:

- [ ] Скопійовано всю директорію `EmbeddingsQwen3/`
- [ ] Створено `backend/.env` з реальними токенами
- [ ] Перевірено доступність Embedding API
- [ ] Перевірено OpenAI API key
- [ ] Перевірено TA-DA API token
- [ ] Створено Docker network: `embeddingsqwen3_semantic-search-net`
- [ ] Створено Docker volume: `embeddingsqwen3_elasticsearch-data`

### Запуск:

- [ ] Виконано `docker-compose up -d`
- [ ] Всі контейнери працюють (`docker-compose ps`)
- [ ] API відповідає: `curl http://localhost:8080/health`
- [ ] Elasticsearch працює: `curl http://localhost:9200`
- [ ] Товари проіндексовані: `docker exec -it api_qwen3 python reindex_products.py`
- [ ] Інтерфейс відкривається: `http://localhost:8080`

### Тестування:

- [ ] Простий пошук працює
- [ ] AI чат-пошук працює
- [ ] Рекомендації генеруються
- [ ] Кошик працює
- [ ] Логи зберігаються

### Документація:

- [ ] Прочитано цей файл (HANDOVER.md)
- [ ] Зрозуміла структура проекту
- [ ] Знаємо, де логи
- [ ] Знаємо, як робити бекапи
- [ ] Знаємо, як додавати товари

### Доступи та контакти:

- [ ] OpenAI API key: `_________________`
- [ ] TA-DA API token: `_________________`
- [ ] Embedding API: `http://10.2.0.171:9001`
- [ ] Контакт для підтримки: `_________________`

---

## 📞 Контакти

**Проект:** Семантичний пошук TA-DA  
**Версія:** 1.0.0  
**Дата:** 13 жовтня 2025  

**Технології:**
- Python 3.11+
- Elasticsearch 8.11
- Docker 24+
- Qwen3-Embedding-8B (зовнішній API)
- OpenAI GPT-4o-mini

**Ліцензія:** Proprietary (власність TA-DA)

