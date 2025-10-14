# 🏗️ Архітектура системи — Семантичний Пошук TA-DA!

## Зміст
- [Огляд архітектури](#огляд-архітектури)
- [Компоненти системи](#компоненти-системи)
- [Потоки даних](#потоки-даних)
- [Алгоритми пошуку](#алгоритми-пошуку)
- [Кешування та оптимізація](#кешування-та-оптимізація)
- [Масштабованість](#масштабованість)

---

## Огляд архітектури

Система побудована на мікросервісній архітектурі з використанням контейнеризації Docker.

### Високорівнева діаграма

```
┌─────────────────────────────────────────────────────────────────┐
│                        КОРИСТУВАЧ                                │
└───────────────────────────┬─────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                    NGINX (Port 8080)                             │
│  ┌──────────────┐  ┌─────────────┐  ┌──────────────────────┐   │
│  │ Static Files │  │ Reverse     │  │ SSE Support          │   │
│  │ (HTML/CSS/JS)│  │ Proxy       │  │ (Event Streaming)    │   │
│  └──────────────┘  └─────────────┘  └──────────────────────┘   │
└───────────────────────────┬─────────────────────────────────────┘
                            │
          ┌─────────────────┼─────────────────┐
          │                 │                 │
          ▼                 ▼                 ▼
┌──────────────┐  ┌──────────────────┐  ┌────────────────┐
│   Static     │  │   FastAPI API    │  │   TA-DA API    │
│   Content    │  │   (Port 8000)    │  │   (External)   │
└──────────────┘  └────────┬─────────┘  └────────────────┘
                           │
        ┌──────────────────┼──────────────────┐
        │                  │                  │
        ▼                  ▼                  ▼
┌───────────────┐  ┌──────────────┐  ┌──────────────┐
│ Elasticsearch │  │ Embedding    │  │  OpenAI      │
│ (Port 9200)   │  │ API (Ollama) │  │  GPT-4 API   │
│               │  │ (Port 9001)  │  │              │
│ ┌───────────┐ │  │              │  │              │
│ │ Products  │ │  │ Qwen3-8B     │  │ gpt-4o-mini  │
│ │ Index     │ │  │ Q8_0         │  │              │
│ │           │ │  │              │  │              │
│ │ Vectors   │ │  │ 4096 dims    │  │              │
│ └───────────┘ │  │              │  │              │
└───────────────┘  └──────────────┘  └──────────────┘
```

---

## Компоненти системи

### 1. Frontend (Web Client)

**Технології:**
- Vanilla JavaScript (ES6+)
- HTML5 с семантичною розміткою
- CSS3 з Grid/Flexbox
- Server-Sent Events (SSE)

**Основні модулі:**

#### 1.1. UI Manager
```javascript
// Управління сторінками та навігацією
- welcomePage: Привітальна сторінка
- simpleSearchPage: Класичний пошук
- chatSearchPage: AI чат-пошук
```

#### 1.2. Search Manager
```javascript
// Обробка пошукових запитів
- performSimpleSearch(): Класичний пошук
- performChatSearch(): AI пошук
- handleSSEStream(): Обробка SSE потоку
```

#### 1.3. Cart Manager
```javascript
// Управління кошиком
- addToCart(): Додати товар
- removeFromCart(): Видалити товар
- updateCartUI(): Оновити інтерфейс
```

#### 1.4. Product Renderer
```javascript
// Відображення товарів
- renderProductCard(): Картка товару
- renderProductCarousel(): Карусель товарів
- lazyLoadImages(): Ліниве завантаження зображень
```

**Особливості:**
- 📱 Адаптивний дизайн (mobile-first)
- ⚡ Оптимізація продуктивності
- 🎨 Сучасний UI/UX
- ♿ Accessibility (ARIA labels)

---

### 2. Backend API (FastAPI)

**Структура коду:**

```
backend/
├── main.py                 # Головний додаток FastAPI
├── search_logger.py        # Логування пошуку
├── reindex_products.py     # Реіндексація
└── requirements.txt        # Залежності
```

#### 2.1. Application Lifecycle

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Управління життєвим циклом додатку"""
    # Startup
    - Підключення до Elasticsearch
    - Перевірка індексу
    - Ініціалізація HTTP клієнтів
    - Підготовка кешів
    
    yield
    
    # Shutdown
    - Закриття з'єднань
    - Очищення ресурсів
```

#### 2.2. Dependency Injection

```python
async def get_es_client() -> AsyncElasticsearch:
    """Singleton Elasticsearch клієнт"""
    
async def get_http_client() -> httpx.AsyncClient:
    """Singleton HTTP клієнт для embeddings"""
```

#### 2.3. Кеш менеджер

```python
class TimedLRUCache:
    """LRU кеш з TTL для embeddings"""
    
    def __init__(self, maxsize: int, ttl_seconds: int):
        self._cache: OrderedDict = OrderedDict()
        self._timestamps: Dict[str, float] = {}
        self._maxsize = maxsize
        self._ttl_seconds = ttl_seconds
    
    def get(self, key: str) -> Optional[Any]:
        """Отримати з перевіркою TTL"""
        
    def put(self, key: str, value: Any):
        """Додати з LRU eviction"""
```

#### 2.4. Embedding Manager

```python
class EmbeddingManager:
    """Управління генерацією та кешуванням embeddings"""
    
    async def get_embedding(self, text: str) -> List[float]:
        """Отримати embedding з кешем"""
        # 1. Перевірка кешу
        # 2. Генерація нового embedding
        # 3. Кешування результату
        
    async def batch_embeddings(self, texts: List[str]) -> List[List[float]]:
        """Batch генерація з обмеженням конкурентності"""
```

#### 2.5. Search Engine

```python
class SearchEngine:
    """Ядро пошукової системи"""
    
    async def hybrid_search(
        self, 
        query: str, 
        k: int = 20
    ) -> List[Dict]:
        """Гібридний пошук (vector + BM25)"""
        
    async def vector_search(
        self, 
        embedding: List[float], 
        k: int = 20
    ) -> List[Dict]:
        """Векторний KNN пошук"""
        
    async def bm25_search(
        self, 
        query: str, 
        k: int = 20
    ) -> List[Dict]:
        """Повнотекстовий BM25 пошук"""
```

#### 2.6. GPT Analyzer

```python
class GPTAnalyzer:
    """AI аналіз запитів та генерація рекомендацій"""
    
    async def analyze_intent(
        self, 
        query: str,
        context: Optional[Dict] = None
    ) -> Dict:
        """Визначення наміру користувача"""
        
    async def generate_subqueries(
        self, 
        query: str,
        max_subqueries: int = 5
    ) -> List[str]:
        """Генерація підзапитів"""
        
    async def generate_recommendations(
        self, 
        query: str,
        products: List[Dict],
        top_k: int = 3
    ) -> List[Dict]:
        """Персоналізовані рекомендації"""
```

---

### 3. Elasticsearch

**Конфігурація індексу:**

```json
{
  "settings": {
    "number_of_shards": 1,
    "number_of_replicas": 0,
    "analysis": {
      "analyzer": {
        "ukrainian_analyzer": {
          "type": "ukrainian"
        }
      }
    }
  },
  "mappings": {
    "properties": {
      "uuid": { "type": "keyword" },
      "title_ua": { 
        "type": "text", 
        "analyzer": "ukrainian_analyzer",
        "fields": {
          "keyword": { "type": "keyword" }
        }
      },
      "title_ru": { 
        "type": "text",
        "fields": {
          "keyword": { "type": "keyword" }
        }
      },
      "description_ua": { 
        "type": "text",
        "analyzer": "ukrainian_analyzer"
      },
      "description_ru": { "type": "text" },
      "description_vector": {
        "type": "dense_vector",
        "dims": 4096,
        "index": true,
        "similarity": "cosine"
      },
      "category": { "type": "keyword" },
      "price": { "type": "float" },
      "in_stock": { "type": "boolean" },
      "sku": { "type": "keyword" },
      "good_code": { "type": "keyword" }
    }
  }
}
```

**Плагіни:**
- `analysis-ukrainian` — морфологічний аналіз української мови

**Оптимізації:**
- `refresh_interval`: 30s (зменшує навантаження)
- `number_of_replicas`: 0 (для dev/single node)
- Cosine similarity для векторів

---

### 4. Embedding Service (Ollama)

**Модель:** `dengcao/Qwen3-Embedding-8B:Q8_0`

**Характеристики:**
- **Розмірність:** 4096 вимірів
- **Квантизація:** Q8_0 (8-bit)
- **Підтримка мов:** Багатомовна (включаючи українську)
- **Швидкість:** ~200-300ms на запит

**API endpoint:**
```http
POST http://10.2.0.171:9001/api/embeddings
{
  "model": "dengcao/Qwen3-Embedding-8B:Q8_0",
  "prompt": "текст для embedding"
}
```

**Відповідь:**
```json
{
  "embedding": [0.123, -0.456, ...],  // 4096 чисел
  "model": "dengcao/Qwen3-Embedding-8B:Q8_0"
}
```

---

### 5. OpenAI GPT-4

**Модель:** `gpt-4o-mini`

**Використання:**
1. **Аналіз intent** — визначення типу запиту
2. **Генерація підзапитів** — розбиття складних запитів
3. **Рекомендації** — персоналізовані поради

**Промпти:**

#### Intent Analysis
```
Проаналізуй запит користувача інтернет-магазину TA-DA!

Запит: "{query}"

Визнач:
1. intent: "product_search" | "clarification" | "invalid"
2. Якщо потрібні уточнення, надай їх
3. Згенеруй 3-5 підзапитів для семантичного пошуку

Відповідь у JSON.
```

#### Recommendations
```
Створи персоналізовані рекомендації для знайдених товарів.

Запит користувача: "{query}"

Топ-3 товари:
{products}

Для кожного товару поясни:
- Чому він підходить
- Основні переваги
- Для кого рекомендується

Відповідь у JSON.
```

---

## Потоки даних

### 1. Класичний пошук (Simple Search)

```
User Input
    ↓
Frontend (scripts.js)
    ↓ POST /search
Backend API
    ↓
┌─────────────────────────┐
│ 1. Генерація embedding  │
│    - Перевірка кешу     │
│    - Ollama API         │
│    - Кешування          │
└───────────┬─────────────┘
            ↓
┌─────────────────────────┐
│ 2. Elasticsearch пошук  │
│    - KNN vector search  │
│    - BM25 text search   │
│    - Fusion results     │
└───────────┬─────────────┘
            ↓
┌─────────────────────────┐
│ 3. Обробка результатів  │
│    - Сортування         │
│    - Пагінація          │
│    - Форматування       │
└───────────┬─────────────┘
            ↓
Frontend Rendering
    ↓
Display Results
```

**Типовий час виконання:**
- Генерація embedding: 200-300ms
- Elasticsearch пошук: 50-150ms
- Обробка результатів: 10-50ms
- **Загалом:** 300-500ms

---

### 2. AI Чат-пошук (Chat Search)

```
User Query
    ↓
Frontend (scripts.js)
    ↓ GET /chat/search/sse
Backend API
    ↓
┌──────────────────────────┐
│ 1. GPT Intent Analysis   │
│    - Визначення intent   │
│    - Генерація підзапитів│
│    - SSE: event=intent   │
└────────────┬─────────────┘
             ↓
      ┌──────┴──────┐
      │  For each   │
      │  subquery   │
      └──────┬──────┘
             ↓
┌──────────────────────────┐
│ 2. Генерація embedding   │
│    - Cache lookup        │
│    - Ollama API          │
│    - SSE: event=subquery │
└────────────┬─────────────┘
             ↓
┌──────────────────────────┐
│ 3. Vector search         │
│    - KNN пошук           │
│    - Score weighting     │
│    - Dedupe products     │
└────────────┬─────────────┘
             ↓
      ┌──────┴──────┐
      │  For each   │
      │  product    │
      └──────┬──────┘
             ↓
┌──────────────────────────┐
│ 4. Stream products       │
│    - SSE: event=product  │
│    - Real-time rendering │
└────────────┬─────────────┘
             ↓
┌──────────────────────────┐
│ 5. Адаптивна фільтрація  │
│    - Dynamic threshold   │
│    - Quality control     │
└────────────┬─────────────┘
             ↓
┌──────────────────────────┐
│ 6. GPT Recommendations   │
│    - Top-K products      │
│    - Reasoning           │
│    - SSE: event=reco     │
└────────────┬─────────────┘
             ↓
┌──────────────────────────┐
│ 7. Логування             │
│    - SearchLogger        │
│    - Session tracking    │
│    - Analytics           │
└────────────┬─────────────┘
             ↓
SSE: event=done
    ↓
Frontend Display
```

**Типовий час виконання:**
- GPT аналіз: 500-1000ms
- Embeddings (3 підзапити): 600-900ms
- Elasticsearch (3 запити): 150-450ms
- Фільтрація: 50-100ms
- GPT рекомендації: 1000-1500ms
- **Загалом:** 2500-4000ms

**SSE Timeline:**
```
0ms       → event: intent
500ms     → event: subquery (1/3)
700ms     → event: subquery (2/3)
900ms     → event: subquery (3/3)
1000ms    → event: product (перший)
1050ms    → event: product
...
1800ms    → event: product (останній)
2000ms    → event: recommendation (1/3)
2500ms    → event: recommendation (2/3)
3000ms    → event: recommendation (3/3)
3100ms    → event: done
```

---

### 3. Lazy Loading

```
User scrolls
    ↓
Frontend detects scroll
    ↓ POST /chat/search/load-more
Backend API
    ↓
┌──────────────────────────┐
│ 1. Lookup cached results │
│    - Session ID          │
│    - TTL check           │
└────────────┬─────────────┘
             ↓
┌──────────────────────────┐
│ 2. Slice products        │
│    - offset: 20          │
│    - limit: 20           │
└────────────┬─────────────┘
             ↓
┌──────────────────────────┐
│ 3. Return batch          │
│    - has_more flag       │
│    - total_available     │
└────────────┬─────────────┘
             ↓
Frontend appends
```

---

## Алгоритми пошуку

### 1. Гібридний пошук (Hybrid Search)

**Алгоритм:**

```python
def hybrid_search(query: str, k: int = 20, alpha: float = 0.7):
    """
    Гібридний пошук з комбінуванням векторного та текстового пошуку
    
    Args:
        query: Пошуковий запит
        k: Кількість результатів
        alpha: Вага векторного пошуку (0-1)
    """
    
    # 1. Генерація embedding
    embedding = generate_embedding(query)
    
    # 2. Паралельний пошук
    vector_results = knn_search(embedding, k=k*2)
    bm25_results = text_search(query, k=k*2)
    
    # 3. Нормалізація scores
    vector_scores = normalize_scores(vector_results)
    bm25_scores = normalize_scores(bm25_results)
    
    # 4. Weighted fusion
    combined = {}
    for product_id, vec_score in vector_scores.items():
        bm25_score = bm25_scores.get(product_id, 0)
        final_score = alpha * vec_score + (1 - alpha) * bm25_score
        combined[product_id] = final_score
    
    # 5. Сортування та топ-K
    results = sorted(combined.items(), key=lambda x: x[1], reverse=True)[:k]
    
    return results
```

**Переваги:**
- ✅ Точність векторного пошуку
- ✅ Швидкість BM25
- ✅ Робастність до typos (BM25)
- ✅ Семантична схожість (vectors)

---

### 2. Адаптивна фільтрація

**Проблема:** 
При різних запитах розподіл scores може сильно відрізнятися. Фіксований поріг може:
- Відфільтрувати занадто багато (втрата результатів)
- Залишити занадто мало (погана якість)

**Рішення:**

```python
def adaptive_filtering(products: List[Dict], config: Dict) -> List[Dict]:
    """
    Адаптивна фільтрація на основі статистики scores
    """
    if not products:
        return []
    
    # Параметри
    threshold_ratio = config['threshold_ratio']  # 0.4
    min_absolute = config['min_absolute']        # 0.3
    
    # Статистика
    scores = [p['score'] for p in products]
    max_score = max(scores)
    mean_score = statistics.mean(scores)
    std_dev = statistics.stdev(scores) if len(scores) > 1 else 0
    
    # Динамічний поріг
    dynamic_threshold = max_score * threshold_ratio
    
    # Адаптивний мінімум (для малої кількості результатів)
    if len(products) < 10:
        adaptive_min = min_absolute
    else:
        adaptive_min = max(mean_score - std_dev, min_absolute)
    
    # Фінальний поріг
    final_threshold = max(
        min(dynamic_threshold, adaptive_min),
        min_absolute
    )
    
    # Фільтрація
    filtered = [p for p in products if p['score'] >= final_threshold]
    
    # Гарантований мінімум (якщо занадто агресивна фільтрація)
    if len(filtered) < 3 and len(products) >= 3:
        filtered = sorted(products, key=lambda x: x['score'], reverse=True)[:10]
    
    return filtered
```

**Приклади:**

| Сценарій | Max Score | Threshold | Результат |
|----------|-----------|-----------|-----------|
| Точний запит | 0.95 | 0.38 | Топ 15 товарів |
| Розмитий запит | 0.65 | 0.30 | Топ 25 товарів |
| Мало результатів | 0.85 | 0.30 | Всі 5 товарів |

---

### 3. Дедуплікація товарів

При пошуку за підзапитами один товар може з'явитися кілька разів.

**Алгоритм:**

```python
def deduplicate_products(
    products_by_subquery: List[List[Dict]]
) -> List[Dict]:
    """
    Дедуплікація з агрегацією scores
    """
    product_map = {}
    
    for subquery_idx, products in enumerate(products_by_subquery):
        # Вага підзапиту (перший важливіший)
        weight = config['weight_decay'] ** subquery_idx
        
        for product in products:
            uuid = product['uuid']
            
            if uuid not in product_map:
                product_map[uuid] = {
                    **product,
                    'aggregated_score': 0,
                    'appearance_count': 0,
                    'subquery_indices': []
                }
            
            # Агрегація score
            product_map[uuid]['aggregated_score'] += product['score'] * weight
            product_map[uuid]['appearance_count'] += 1
            product_map[uuid]['subquery_indices'].append(subquery_idx)
    
    # Нормалізація
    for product in product_map.values():
        count = product['appearance_count']
        product['final_score'] = (
            product['aggregated_score'] / count * 
            (1 + 0.1 * (count - 1))  # Бонус за кількість появ
        )
    
    # Сортування
    results = sorted(
        product_map.values(),
        key=lambda x: x['final_score'],
        reverse=True
    )
    
    return results
```

**Переваги:**
- Товари, що підходять під кілька критеріїв, отримують вищий score
- Зменшення weight для наступних підзапитів
- Бонус за появу в кількох підзапитах

---

## Кешування та оптимізація

### 1. Embedding Cache

**Реалізація:**

```python
class TimedLRUCache:
    def __init__(self, maxsize: int = 2000, ttl_seconds: int = 3600):
        self._cache = OrderedDict()
        self._timestamps = {}
        self._maxsize = maxsize
        self._ttl_seconds = ttl_seconds
        self._lock = asyncio.Lock()
    
    async def get(self, key: str) -> Optional[Any]:
        async with self._lock:
            if key not in self._cache:
                return None
            
            # TTL check
            if time.time() - self._timestamps[key] > self._ttl_seconds:
                del self._cache[key]
                del self._timestamps[key]
                return None
            
            # LRU update
            self._cache.move_to_end(key)
            return self._cache[key]
    
    async def put(self, key: str, value: Any):
        async with self._lock:
            # Eviction
            if len(self._cache) >= self._maxsize:
                oldest_key = next(iter(self._cache))
                del self._cache[oldest_key]
                del self._timestamps[oldest_key]
            
            self._cache[key] = value
            self._timestamps[key] = time.time()
            self._cache.move_to_end(key)
```

**Метрики:**
- Hit rate: ~36%
- Середнє економія часу: 200-300ms на hit
- Розмір: 2000 entries (~50MB RAM)

---

### 2. Search Results Cache

Кешування результатів чат-пошуку для lazy loading.

```python
class SearchResultsCache:
    def __init__(self, ttl_seconds: int = 3600):
        self._cache: Dict[str, Dict] = {}
        self._timestamps: Dict[str, float] = {}
        self._ttl_seconds = ttl_seconds
    
    def store(self, session_id: str, results: List[Dict]):
        self._cache[session_id] = {
            'products': results,
            'total': len(results)
        }
        self._timestamps[session_id] = time.time()
    
    def get_batch(
        self, 
        session_id: str, 
        offset: int, 
        limit: int
    ) -> Optional[Dict]:
        if session_id not in self._cache:
            return None
        
        # TTL check
        if time.time() - self._timestamps[session_id] > self._ttl_seconds:
            del self._cache[session_id]
            del self._timestamps[session_id]
            return None
        
        products = self._cache[session_id]['products']
        batch = products[offset:offset + limit]
        
        return {
            'products': batch,
            'has_more': offset + limit < len(products),
            'total_available': len(products)
        }
```

---

### 3. Connection Pooling

```python
# HTTP клієнт з connection pooling
http_client = httpx.AsyncClient(
    timeout=httpx.Timeout(30.0),
    limits=httpx.Limits(
        max_connections=100,
        max_keepalive_connections=20
    )
)

# Elasticsearch з connection pooling
es_client = AsyncElasticsearch(
    [settings.elastic_url],
    max_retries=3,
    retry_on_timeout=True,
    request_timeout=30
)
```

---

### 4. Batch Processing

```python
async def batch_generate_embeddings(
    texts: List[str],
    max_concurrent: int = 2
) -> List[List[float]]:
    """
    Паралельна генерація embeddings з обмеженням конкурентності
    """
    semaphore = asyncio.Semaphore(max_concurrent)
    
    async def _generate_with_semaphore(text: str):
        async with semaphore:
            return await generate_embedding(text)
    
    tasks = [_generate_with_semaphore(text) for text in texts]
    embeddings = await asyncio.gather(*tasks)
    
    return embeddings
```

---

## Масштабованість

### Поточна конфігурація (Single Node)

```
┌─────────────────────┐
│   nginx:8080        │
│   ├─ Static files   │
│   └─ Reverse proxy  │
└──────────┬──────────┘
           │
┌──────────┴──────────┐
│   api:8000          │
│   Single instance   │
└──────────┬──────────┘
           │
┌──────────┴──────────┐
│   elasticsearch     │
│   Single node       │
│   No replicas       │
└─────────────────────┘
```

**Обмеження:**
- Один API інстанс
- Один ES node
- Немає HA (High Availability)

---

### Масштабована конфігурація (Production)

```
                    ┌─────────────┐
                    │  Load       │
                    │  Balancer   │
                    │  (Nginx)    │
                    └──────┬──────┘
                           │
        ┌──────────────────┼──────────────────┐
        │                  │                  │
┌───────▼────────┐ ┌───────▼────────┐ ┌──────▼────────┐
│   API Pod 1    │ │   API Pod 2    │ │   API Pod 3   │
│   (FastAPI)    │ │   (FastAPI)    │ │   (FastAPI)   │
└───────┬────────┘ └───────┬────────┘ └──────┬────────┘
        │                  │                  │
        └──────────────────┼──────────────────┘
                           │
        ┌──────────────────┼──────────────────┐
        │                  │                  │
┌───────▼────────┐ ┌───────▼────────┐ ┌──────▼────────┐
│  ES Master 1   │ │  ES Master 2   │ │  ES Master 3  │
│                │ │                │ │               │
│  + Data Node   │ │  + Data Node   │ │  + Data Node  │
└────────────────┘ └────────────────┘ └───────────────┘
        │                  │                  │
        └──────────────────┴──────────────────┘
                    Cluster coordination
```

**Рекомендації:**

1. **API Layer:**
   - Мінімум 2-3 інстанси
   - Kubernetes HPA (Horizontal Pod Autoscaler)
   - Shared Redis для кешу
   - Sticky sessions для SSE

2. **Elasticsearch:**
   - 3 master nodes
   - 2+ data nodes
   - Replicas: 1-2
   - Cross-zone deployment

3. **Кешування:**
   - Redis Cluster для embedding cache
   - Shared між API інстансами
   - Persistence (AOF)

4. **Моніторинг:**
   - Prometheus + Grafana
   - ELK для логів
   - AlertManager

---

**Версія:** 1.0.0  
**Дата оновлення:** 13 жовтня 2025

