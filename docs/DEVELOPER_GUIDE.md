# 👨‍💻 Developer Guide — Семантичний Пошук TA-DA!

## Зміст
- [Початок роботи](#початок-роботи)
- [Структура коду](#структура-коду)
- [Розробка нових фіч](#розробка-нових-фіч)
- [Тестування](#тестування)
- [Best Practices](#best-practices)
- [Code Style](#code-style)
- [Git Workflow](#git-workflow)

---

## Початок роботи

### 1. Налаштування локального середовища

```bash
# Клонувати репозиторій
git clone <repository-url>
cd EmbeddingsQwen3

# Створити віртуальне середовище для backend
cd backend
python3 -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Встановити залежності
pip install -r requirements.txt
pip install -r requirements-dev.txt  # dev залежності

# Повернутися в корінь проекту
cd ..

# Створити .env файл
cp backend/.env.example backend/.env
# Відредагувати .env з вашими налаштуваннями
```

### 2. Запуск локально (без Docker)

```bash
# Terminal 1: Запустити Elasticsearch
docker run -d --name elasticsearch-dev \
  -p 9200:9200 -p 9300:9300 \
  -e "discovery.type=single-node" \
  -e "xpack.security.enabled=false" \
  elasticsearch:8.11.1

# Terminal 2: Запустити backend API
cd backend
source venv/bin/activate
uvicorn main:app --reload --host 0.0.0.0 --port 8000

# Terminal 3: Запустити frontend (простий HTTP сервер)
cd web
python3 -m http.server 8080
# АБО
npx http-server -p 8080
```

Відкрийте http://localhost:8080

---

## Структура коду

### Backend (`backend/main.py`)

```python
# ============================================
# СЕКЦІЯ 1: Імпорти та налаштування (рядки 1-100)
# ============================================
- Імпорти бібліотек
- Logging конфігурація
- Settings class (Pydantic)

# ============================================
# СЕКЦІЯ 2: Data Models (рядки 100-250)
# ============================================
class SearchRequest(BaseModel):
    """Модель запиту пошуку"""
    
class ChatSearchRequest(BaseModel):
    """Модель чат-пошуку"""
    
class Product(BaseModel):
    """Модель товару"""

# ============================================
# СЕКЦІЯ 3: Кеш та утиліти (рядки 250-500)
# ============================================
class TimedLRUCache:
    """LRU кеш з TTL"""
    
def create_cache_key(text: str) -> str:
    """Генерація ключа кешу"""

# ============================================
# СЕКЦІЯ 4: Embedding Manager (рядки 500-800)
# ============================================
async def generate_embedding(text: str) -> List[float]:
    """Генерація embedding з кешуванням"""
    
async def batch_embeddings(texts: List[str]) -> List[List[float]]:
    """Batch генерація"""

# ============================================
# СЕКЦІЯ 5: GPT Integration (рядки 800-1200)
# ============================================
async def gpt_analyze_intent(query: str) -> Dict:
    """Аналіз наміру з GPT"""
    
async def gpt_generate_recommendations(products: List[Dict]) -> List[Dict]:
    """Генерація рекомендацій"""

# ============================================
# СЕКЦІЯ 6: Search Engine (рядки 1200-2000)
# ============================================
async def hybrid_search(query: str, k: int) -> List[Dict]:
    """Гібридний пошук"""
    
async def vector_search(embedding: List[float], k: int) -> List[Dict]:
    """Векторний пошук"""
    
async def bm25_search(query: str, k: int) -> List[Dict]:
    """Текстовий пошук"""

# ============================================
# СЕКЦІЯ 7: API Endpoints (рядки 2000-3000)
# ============================================
@app.get("/health")
async def health_check():
    """Health check endpoint"""

@app.post("/search")
async def search(request: SearchRequest):
    """Простий пошук"""

@app.post("/chat/search")
async def chat_search(request: ChatSearchRequest):
    """AI чат-пошук"""

@app.get("/chat/search/sse")
async def chat_search_sse():
    """SSE чат-пошук"""

# ============================================
# СЕКЦІЯ 8: Search Logging (рядки 3000-3150)
# ============================================
- Endpoints для логів
- Аналітика сесій
```

### Frontend (`web/scripts.js`)

```javascript
// ============================================
// СЕКЦІЯ 1: Конфігурація та константи (1-100)
// ============================================
const SEARCH_API_URL = '/search';
const CHAT_SEARCH_API_URL = '/chat/search';
const CATEGORY_SCHEMA = {...};

// ============================================
// СЕКЦІЯ 2: Глобальні змінні та стан (100-200)
// ============================================
let cartItems = [];
let chatStep = 0;
let searchBoxAnimationShown = false;

// ============================================
// СЕКЦІЯ 3: Утилітарні функції (200-400)
// ============================================
function debounce(func, wait) {...}
function throttle(func, limit) {...}
function formatPrice(price) {...}

// ============================================
// СЕКЦІЯ 4: UI Management (400-800)
// ============================================
function showPage(pageName) {...}
function toggleCatalog() {...}
function activateSearchBox() {...}

// ============================================
// СЕКЦІЯ 5: Простий пошук (800-1200)
// ============================================
async function performSimpleSearch(query) {...}
function renderSimpleSearchResults(results) {...}

// ============================================
// СЕКЦІЯ 6: AI Чат-пошук (1200-2500)
// ============================================
async function performChatSearch(query) {...}
function handleSSEStream(eventSource) {...}
function renderChatSection(data) {...}

// ============================================
// СЕКЦІЯ 7: Product Rendering (2500-3200)
// ============================================
function renderProductCard(product) {...}
function createProductCarousel(products) {...}
function renderRecommendations(recommendations) {...}

// ============================================
// СЕКЦІЯ 8: Cart Management (3200-3800)
// ============================================
function addToCart(product) {...}
function removeFromCart(uuid) {...}
function updateCartUI() {...}

// ============================================
// СЕКЦІЯ 9: Event Listeners (3800-4400)
// ============================================
document.addEventListener('DOMContentLoaded', () => {...});
headerSearchInput.addEventListener('input', debounce(...));
```

---

## Розробка нових фіч

### Приклад: Додати новий тип пошуку

#### 1. Backend: Додати новий алгоритм

```python
# backend/main.py

async def semantic_only_search(
    query: str,
    k: int = 20,
    es: AsyncElasticsearch = Depends(get_es_client)
) -> List[Dict]:
    """
    Чисто семантичний пошук без BM25
    """
    # Генерувати embedding
    embedding = await generate_embedding(query)
    if not embedding:
        raise HTTPException(status_code=500, detail="Failed to generate embedding")
    
    # KNN пошук
    knn_query = {
        "knn": {
            "field": settings.vector_field_name,
            "query_vector": embedding,
            "k": k,
            "num_candidates": settings.knn_num_candidates
        }
    }
    
    response = await es.search(
        index=settings.index_name,
        body=knn_query,
        size=k
    )
    
    # Обробити результати
    results = []
    for hit in response["hits"]["hits"]:
        product = hit["_source"]
        product["score"] = hit["_score"]
        results.append(product)
    
    return results
```

#### 2. Backend: Додати endpoint

```python
@app.post("/search/semantic")
async def semantic_search_endpoint(
    request: SearchRequest,
    es: AsyncElasticsearch = Depends(get_es_client)
):
    """Чисто семантичний пошук"""
    try:
        results = await semantic_only_search(
            query=request.query,
            k=request.k,
            es=es
        )
        
        return SearchResponse(
            results=results,
            query=request.query,
            total=len(results),
            search_type="semantic"
        )
    except Exception as e:
        logger.error(f"Semantic search error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
```

#### 3. Frontend: Додати UI

```javascript
// web/scripts.js

async function performSemanticSearch(query) {
    try {
        showLoadingIndicator();
        
        const response = await fetch('/search/semantic', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                query: query,
                k: 20
            })
        });
        
        if (!response.ok) {
            throw new Error('Search failed');
        }
        
        const data = await response.json();
        renderSearchResults(data.results);
        
    } catch (error) {
        console.error('Semantic search error:', error);
        showErrorMessage('Помилка пошуку');
    } finally {
        hideLoadingIndicator();
    }
}

// Додати кнопку в UI
function addSemanticSearchButton() {
    const button = document.createElement('button');
    button.className = 'search-mode-btn';
    button.textContent = 'Семантичний пошук';
    button.onclick = () => {
        const query = headerSearchInput.value;
        performSemanticSearch(query);
    };
    document.querySelector('.search-modes').appendChild(button);
}
```

#### 4. Тестування

```python
# tests/test_semantic_search.py

import pytest
from httpx import AsyncClient
from main import app

@pytest.mark.asyncio
async def test_semantic_search():
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post(
            "/search/semantic",
            json={"query": "олівці кольорові", "k": 10}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "results" in data
        assert len(data["results"]) <= 10
        assert data["search_type"] == "semantic"

@pytest.mark.asyncio
async def test_semantic_search_empty_query():
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post(
            "/search/semantic",
            json={"query": "", "k": 10}
        )
        
        assert response.status_code == 422  # Validation error
```

---

## Тестування

### Unit Tests

```python
# tests/test_cache.py

import pytest
import asyncio
from main import TimedLRUCache

@pytest.mark.asyncio
async def test_cache_basic():
    cache = TimedLRUCache(maxsize=3, ttl_seconds=60)
    
    # Test put and get
    await cache.put("key1", "value1")
    assert await cache.get("key1") == "value1"
    
    # Test miss
    assert await cache.get("nonexistent") is None

@pytest.mark.asyncio
async def test_cache_lru_eviction():
    cache = TimedLRUCache(maxsize=2, ttl_seconds=60)
    
    await cache.put("key1", "value1")
    await cache.put("key2", "value2")
    await cache.put("key3", "value3")  # Should evict key1
    
    assert await cache.get("key1") is None
    assert await cache.get("key2") == "value2"
    assert await cache.get("key3") == "value3"

@pytest.mark.asyncio
async def test_cache_ttl():
    cache = TimedLRUCache(maxsize=10, ttl_seconds=1)
    
    await cache.put("key1", "value1")
    assert await cache.get("key1") == "value1"
    
    # Wait for TTL to expire
    await asyncio.sleep(1.1)
    
    assert await cache.get("key1") is None
```

### Integration Tests

```python
# tests/test_integration.py

import pytest
from httpx import AsyncClient

@pytest.mark.asyncio
async def test_full_search_workflow():
    """Тест повного циклу пошуку"""
    async with AsyncClient(app=app, base_url="http://test") as client:
        # 1. Health check
        health = await client.get("/health")
        assert health.status_code == 200
        
        # 2. Простий пошук
        search = await client.post(
            "/search",
            json={"query": "олівці", "k": 5}
        )
        assert search.status_code == 200
        results = search.json()
        assert len(results["results"]) > 0
        
        # 3. Перевірити кеш
        cache_stats = await client.get("/cache/stats")
        assert cache_stats.status_code == 200
        stats = cache_stats.json()
        assert stats["size"] > 0
```

### Запуск тестів

```bash
# Встановити pytest
pip install pytest pytest-asyncio pytest-cov

# Запустити всі тести
pytest

# З coverage
pytest --cov=. --cov-report=html

# Тільки швидкі тести
pytest -m "not slow"

# Конкретний файл
pytest tests/test_cache.py

# З виводом
pytest -v -s
```

---

## Best Practices

### 1. Асинхронний код

**✅ DO:**
```python
async def fetch_data():
    async with httpx.AsyncClient() as client:
        response = await client.get(url)
        return response.json()
```

**❌ DON'T:**
```python
def fetch_data():
    # Блокуючий I/O в async функції
    response = requests.get(url)
    return response.json()
```

### 2. Обробка помилок

**✅ DO:**
```python
async def search_products(query: str):
    try:
        embedding = await generate_embedding(query)
        results = await vector_search(embedding)
        return results
    except EmbeddingAPIError as e:
        logger.error(f"Embedding API error: {e}")
        raise HTTPException(
            status_code=503,
            detail="Embedding service unavailable"
        )
    except Exception as e:
        logger.exception(f"Unexpected error: {e}")
        raise HTTPException(
            status_code=500,
            detail="Internal server error"
        )
```

**❌ DON'T:**
```python
async def search_products(query: str):
    # Проглочування помилок
    try:
        embedding = await generate_embedding(query)
        results = await vector_search(embedding)
        return results
    except:
        return []
```

### 3. Логування

**✅ DO:**
```python
logger.info(f"Search query: {query}, found {len(results)} products")
logger.warning(f"Low quality results for query: {query}, max_score: {max_score}")
logger.error(f"Search failed: {error}", exc_info=True)
```

**❌ DON'T:**
```python
print(f"Query: {query}")  # Не використовувати print
logger.debug(f"Sensitive data: {api_key}")  # Не логувати секрети
```

### 4. Валідація даних

**✅ DO:**
```python
class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=500)
    k: int = Field(default=20, ge=1, le=100)
    
    @field_validator("query")
    @classmethod
    def validate_query(cls, v: str) -> str:
        # Очистити від зайвих пробілів
        v = v.strip()
        if not v:
            raise ValueError("Query cannot be empty")
        return v
```

**❌ DON'T:**
```python
def search(query: str, k: int):
    # Немає валідації
    results = do_search(query, k)
    return results
```

### 5. Кешування

**✅ DO:**
```python
async def get_embedding_cached(text: str) -> List[float]:
    # Перевірити кеш
    cache_key = create_cache_key(text)
    cached = await embedding_cache.get(cache_key)
    
    if cached:
        cache_hits.inc()
        return cached
    
    # Генерувати новий
    cache_misses.inc()
    embedding = await generate_embedding(text)
    
    # Кешувати
    await embedding_cache.put(cache_key, embedding)
    
    return embedding
```

---

## Code Style

### Python (PEP 8)

```python
# Imports організовані
import os
import sys
from typing import List, Dict, Optional

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from .utils import helper_function

# Константи UPPERCASE
MAX_RESULTS = 100
DEFAULT_TIMEOUT = 30

# Класи PascalCase
class SearchEngine:
    """Пошуковий движок"""
    
    def __init__(self, config: Dict):
        self.config = config
    
    async def search(self, query: str) -> List[Dict]:
        """Виконати пошук"""
        pass

# Функції snake_case
async def generate_embedding(text: str) -> List[float]:
    """Генерувати embedding для тексту"""
    pass

# Docstrings для всіх публічних функцій
def process_results(
    results: List[Dict],
    threshold: float = 0.5
) -> List[Dict]:
    """
    Обробити результати пошуку
    
    Args:
        results: Список знайдених товарів
        threshold: Мінімальний score (0-1)
    
    Returns:
        Відфільтровані результати
    """
    return [r for r in results if r['score'] >= threshold]
```

### JavaScript (ES6+)

```javascript
// Константи UPPERCASE
const API_URL = '/api/search';
const MAX_PRODUCTS = 100;

// Класи PascalCase
class ProductCard {
    constructor(product) {
        this.product = product;
    }
    
    render() {
        // ...
    }
}

// Функції camelCase
async function fetchProducts(query) {
    const response = await fetch(API_URL, {
        method: 'POST',
        body: JSON.stringify({query})
    });
    return response.json();
}

// Arrow functions для callbacks
const products = data.map(item => ({
    id: item.uuid,
    name: item.title_ua
}));

// Destructuring
const {products, total, search_time_ms} = responseData;

// Template literals
const message = `Знайдено ${total} товарів за ${search_time_ms}ms`;

// Modern async/await
async function searchProducts(query) {
    try {
        const data = await fetchProducts(query);
        renderResults(data.products);
    } catch (error) {
        console.error('Search failed:', error);
        showError('Помилка пошуку');
    }
}
```

---

## Git Workflow

### Branch Naming

```bash
# Features
git checkout -b feature/add-semantic-search
git checkout -b feature/improve-cache

# Bugfixes
git checkout -b fix/cart-update-issue
git checkout -b fix/sse-connection-timeout

# Hotfixes
git checkout -b hotfix/production-crash
```

### Commit Messages

**Format:** `<type>(<scope>): <subject>`

**Types:**
- `feat`: Нова функція
- `fix`: Виправлення бага
- `docs`: Зміни в документації
- `style`: Форматування, відступи
- `refactor`: Рефакторинг коду
- `perf`: Покращення продуктивності
- `test`: Додавання тестів
- `chore`: Інші зміни

**Examples:**
```bash
git commit -m "feat(search): add semantic-only search mode"
git commit -m "fix(cart): fix total price calculation"
git commit -m "docs(api): update API documentation"
git commit -m "perf(cache): improve LRU cache performance"
git commit -m "refactor(ui): extract product card component"
```

### Pull Request Template

```markdown
## Опис
Короткий опис змін

## Тип змін
- [ ] Нова функція
- [ ] Виправлення бага
- [ ] Документація
- [ ] Рефакторинг

## Чеклист
- [ ] Код відповідає style guide
- [ ] Додані unit tests
- [ ] Оновлена документація
- [ ] Протестовано локально
- [ ] Немає breaking changes (або вони задокументовані)

## Скріншоти (якщо UI зміни)
Додайте скріншоти

## Пов'язані issues
Fixes #123
```

---

## Корисні команди

```bash
# Backend development
cd backend
source venv/bin/activate
uvicorn main:app --reload --log-level debug

# Тести
pytest -v
pytest --cov=. --cov-report=html
pytest -k "test_cache"  # Запустити конкретний тест

# Linting
flake8 main.py
pylint main.py
black main.py  # Auto-format

# Type checking
mypy main.py

# Docker
docker-compose up -d
docker-compose logs -f api
docker-compose exec api bash
docker-compose down -v  # З видаленням volumes

# Git
git status
git diff
git add .
git commit -m "feat: add new feature"
git push origin feature/my-feature
```

---

## Додаткові ресурси

- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [Elasticsearch Python Client](https://elasticsearch-py.readthedocs.io/)
- [Pydantic Documentation](https://docs.pydantic.dev/)
- [MDN Web Docs](https://developer.mozilla.org/)
- [Python asyncio](https://docs.python.org/3/library/asyncio.html)

---

**Версія:** 1.0.0  
**Дата оновлення:** 13 жовтня 2025

