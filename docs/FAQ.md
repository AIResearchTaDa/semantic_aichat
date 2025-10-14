# ❓ FAQ — Поширені питання

## Зміст
- [Загальні питання](#загальні-питання)
- [Технічні питання](#технічні-питання)
- [Пошук та AI](#пошук-та-ai)
- [Продуктивність](#продуктивність)
- [Deployment](#deployment)
- [Troubleshooting](#troubleshooting)

---

## Загальні питання

### Що таке семантичний пошук?

Семантичний пошук — це технологія, яка розуміє **значення** запиту, а не просто шукає співпадіння слів. 

**Приклад:**
- **Класичний пошук:** "червоні черевики" знайде тільки товари з цими словами
- **Семантичний пошук:** "взуття червоного кольору" знайде "червоні черевики", "червоні туфлі", "взуття червоне"

### Чому використовується AI?

AI (GPT-4) допомагає:
1. **Розуміти складні запити:** "Що подарувати дитині на 5 років?"
2. **Генерувати підзапити:** розбиває складний запит на простіші
3. **Давати рекомендації:** пояснює, чому товар підходить
4. **Вести діалог:** враховує контекст попередніх повідомлень

### Яка різниця між простим та AI пошуком?

| Характеристика | Простий пошук | AI чат-пошук |
|----------------|---------------|--------------|
| Швидкість | ⚡ Дуже швидко (300-500ms) | 🐢 Повільніше (2-4s) |
| Точність | ✅ Висока для точних запитів | ✅ Висока для складних запитів |
| Рекомендації | ❌ Немає | ✅ Є персоналізовані |
| Розуміння контексту | ❌ Обмежене | ✅ Повне |
| Витрати | 💰 Дешево | 💰💰 Дорожче (GPT API) |

### Чи зберігаються мої пошукові запити?

**Так**, але анонімно:
- Запити логуються для покращення якості
- Зберігається тільки session_id (без особистих даних)
- Логи використовуються для аналітики
- TTL: 7 днів за замовчуванням

**Ви можете відключити логування** в `.env`:
```env
ENABLE_SEARCH_LOGGING=false
```

---

## Технічні питання

### Які моделі AI використовуються?

1. **Qwen3-Embedding-8B (Q8_0)**
   - Призначення: Генерація векторних embeddings
   - Розмірність: 4096 вимірів
   - Швидкість: 200-300ms на запит
   - Підтримка: Багатомовна (включно з українською)

2. **GPT-4o-mini**
   - Призначення: Аналіз запитів та рекомендації
   - Токени: 250 (аналіз) + 500 (рекомендації)
   - Швидкість: 1-2 секунди

### Чому Elasticsearch?

**Переваги:**
- ✅ Швидкий повнотекстовий пошук (BM25)
- ✅ Вбудована підтримка векторного пошуку (KNN)
- ✅ Масштабованість (horizontal scaling)
- ✅ Плагін для української мови
- ✅ Powerful query DSL
- ✅ Real-time індексація

**Альтернативи:**
- PostgreSQL + pgvector (простіше, але повільніше)
- Pinecone (тільки вектори, без BM25)
- Milvus (тільки вектори)
- Qdrant (добрий, але менш зрілий)

### Як працює гібридний пошук?

```
Запит користувача: "зелені олівці"
         │
         ├─────────────────┬─────────────────┐
         ▼                 ▼                 ▼
    Генерація         BM25 пошук      KNN пошук
    embedding         (текст)          (вектори)
         │                 │                 │
         │                 ▼                 │
         │           Score BM25              │
         │           [0.8, 0.6, 0.5]         │
         │                 │                 │
         └─────────────────┼─────────────────┘
                           ▼
                   Weighted Fusion
              final = 0.7*vector + 0.3*bm25
                           │
                           ▼
                   [0.85, 0.72, 0.68]
                           │
                           ▼
                   Топ-K результатів
```

### Що таке embeddings?

**Embedding** — це представлення тексту у вигляді вектора чисел.

**Приклад:**
```
Текст: "олівці кольорові"
       ↓
Embedding: [0.234, -0.567, 0.891, ..., 0.123]  // 4096 чисел
```

**Чому це корисно:**
- Схожі тексти мають схожі вектори
- Можна обчислити відстань між векторами
- Ефективний пошук найближчих сусідів (KNN)

**Візуалізація (спрощено до 2D):**
```
       олівці •
              │ \
              │  \ (близько)
              │   \
    ручки •───┴────• кольорові олівці
              │
              │ (далеко)
              │
           стіл •
```

---

## Пошук та AI

### Чому пошук іноді повертає мало результатів?

**Причини:**
1. **Адаптивна фільтрація** — система відфільтровує нерелевантні товари
2. **Занадто специфічний запит** — немає точних співпадінь
3. **Високий поріг якості** — тільки релевантні результати

**Рішення:**
- Зробіть запит більш загальним
- Використайте синоніми
- Перевірте правопис

### Як покращити якість пошуку?

**Для користувачів:**
1. **Точні запити:** "олівці кольорові 24 кольори"
2. **Природна мова (AI пошук):** "Що потрібно для школи першокласнику?"
3. **Уточнення:** додайте деталі (бренд, колір, розмір)

**Для адміністраторів:**
```env
# Зменшити поріг фільтрації (більше результатів)
CHAT_SEARCH_SCORE_THRESHOLD_RATIO=0.3

# Збільшити кількість кандидатів
KNN_NUM_CANDIDATES=1000

# Налаштувати баланс hybrid пошуку
HYBRID_ALPHA=0.6  # Більше ваги BM25
```

### Чому AI іноді просить уточнень?

GPT визначає intent як `clarification` коли:
- Запит занадто розмитий: "щось цікаве"
- Потрібні додаткові деталі: "подарунок" (кому? скільки років?)
- Запит не про товари: "як погода?"

**Приклад:**
```
Запит: "подарунок"
       ↓
AI: "Будь ласка, уточніть: 
     - Кому подарунок? (дитині, дорослому, колезі)
     - З якої нагоди? (день народження, свято)
     - Який бюджет?"
```

### Як працюють рекомендації?

1. **Grounded recommendations** (за замовчуванням):
   - Базуються на знайдених товарах
   - Пояснюють, чому товар підходить
   - Топ-3 найрелевантніші

2. **Free-form recommendations** (опціонально):
   - Загальні поради
   - Можуть згадувати товари, яких немає в результатах

**Налаштування:**
```env
GROUNDED_RECOMMENDATIONS=true  # Тільки знайдені товари
RECO_DETAILED_COUNT=3          # Кількість детальних рекомендацій
```

---

## Продуктивність

### Чому перший пошук повільніший?

**Cold start ефект:**
- Embedding кеш порожній
- Elasticsearch cache порожній
- HTTP connections ще не встановлені

**Час:**
- Перший запит: 1-2 секунди
- Наступні: 300-500ms

**Рішення:**
- **Warming up:** зробити кілька тестових запитів після старту
- **Persistent cache:** використати Redis

### Як збільшити швидкість пошуку?

**1. Збільшити кеш:**
```env
EMBED_CACHE_SIZE=5000
CACHE_TTL_SECONDS=7200
```

**2. Зменшити кількість підзапитів:**
```env
# У промптах GPT попросити генерувати не більше 3 підзапитів
```

**3. Використати Redis для shared cache:**
```python
# Замість in-memory cache
import redis
cache = redis.Redis(host='redis', port=6379)
```

**4. Оптимізувати Elasticsearch:**
```bash
curl -X PUT "http://localhost:9200/products_qwen3_8b/_settings" \
  -H "Content-Type: application/json" \
  -d '{
    "index": {
      "refresh_interval": "30s",
      "number_of_replicas": 0
    }
  }'
```

**5. Додати більше API інстансів** (load balancing)

### Скільки RAM потрібно?

**Мінімум (development):**
- Elasticsearch: 2GB
- API: 512MB
- Nginx: 128MB
- **Загалом:** 3GB

**Рекомендовано (production):**
- Elasticsearch cluster: 8GB+ (4GB на node)
- API instances: 1GB на інстанс
- Redis: 2GB
- **Загалом:** 12-16GB

### Скільки коштує OpenAI API?

**GPT-4o-mini ціни (станом на 2025):**
- Input: $0.15 / 1M tokens
- Output: $0.60 / 1M tokens

**Середній чат-пошук:**
- Input: ~300 tokens (аналіз) + 1000 tokens (рекомендації) = 1300 tokens
- Output: ~200 tokens (аналіз) + 400 tokens (рекомендації) = 600 tokens

**Вартість:**
- Один пошук: ~$0.0005 (0.0005$)
- 1000 пошуків: ~$0.50
- 10000 пошуків: ~$5.00

**Як зменшити витрати:**
```env
# Відключити рекомендації для деяких категорій
GROUNDED_RECOMMENDATIONS=false

# Зменшити max tokens
GPT_MAX_TOKENS_RECO=300

# Використовувати тільки для складних запитів
ENABLE_GPT_CHAT=conditional  # Власна логіка
```

---

## Deployment

### Docker vs Kubernetes?

| Характеристика | Docker Compose | Kubernetes |
|----------------|----------------|------------|
| Складність | 🟢 Просто | 🔴 Складно |
| Масштабування | 🟡 Вертикальне | 🟢 Горизонтальне |
| HA | ❌ Ні | ✅ Так |
| Auto-scaling | ❌ Ні | ✅ Так |
| Підходить для | Dev, small prod | Medium-large prod |

**Рекомендації:**
- **< 10k запитів/день:** Docker Compose
- **> 10k запитів/день:** Kubernetes

### Як налаштувати SSL?

**З Let's Encrypt (безкоштовно):**
```bash
# Встановити certbot
sudo apt install certbot python3-certbot-nginx

# Отримати сертифікат
sudo certbot --nginx -d your-domain.com

# Автоматичне оновлення
sudo certbot renew --dry-run
```

**З власним сертифікатом:**
```nginx
server {
    listen 443 ssl;
    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;
}
```

### Як зробити backup?

**Elasticsearch snapshot:**
```bash
# Створити snapshot repository
curl -X PUT "localhost:9200/_snapshot/backup" \
  -H "Content-Type: application/json" \
  -d '{
    "type": "fs",
    "settings": {
      "location": "/backups/elasticsearch"
    }
  }'

# Створити snapshot
curl -X PUT "localhost:9200/_snapshot/backup/snapshot_1?wait_for_completion=true"

# Відновити
curl -X POST "localhost:9200/_snapshot/backup/snapshot_1/_restore"
```

**Docker volumes:**
```bash
# Backup
docker run --rm \
  -v embeddingsqwen3_elasticsearch-data:/data \
  -v $(pwd)/backups:/backup \
  alpine tar czf /backup/es-data.tar.gz -C /data .

# Restore
docker run --rm \
  -v embeddingsqwen3_elasticsearch-data:/data \
  -v $(pwd)/backups:/backup \
  alpine tar xzf /backup/es-data.tar.gz -C /data
```

### Чи можна запустити без Docker?

**Так, але складніше:**

```bash
# 1. Встановити Elasticsearch
wget https://artifacts.elastic.co/downloads/elasticsearch/elasticsearch-8.11.1-linux-x86_64.tar.gz
tar -xzf elasticsearch-8.11.1-linux-x86_64.tar.gz
./elasticsearch-8.11.1/bin/elasticsearch

# 2. Встановити Python залежності
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 3. Запустити API
uvicorn main:app --host 0.0.0.0 --port 8000

# 4. Налаштувати nginx
sudo cp nginx.conf /etc/nginx/sites-available/semantic-search
sudo ln -s /etc/nginx/sites-available/semantic-search /etc/nginx/sites-enabled/
sudo systemctl reload nginx

# 5. Налаштувати Ollama окремо
```

**Docker простіше та надійніше!** 🐳

---

## Troubleshooting

### Пошук не працює / повертає помилку 500

**Діагностика:**
```bash
# 1. Перевірити логи API
docker-compose logs api

# 2. Перевірити Elasticsearch
curl http://localhost:9200/_cluster/health

# 3. Перевірити embedding API
curl -X POST http://10.2.0.171:9001/api/embeddings \
  -H "Content-Type: application/json" \
  -d '{"model": "dengcao/Qwen3-Embedding-8B:Q8_0", "prompt": "тест"}'

# 4. Перевірити health endpoint
curl http://localhost:8080/health
```

**Поширені причини:**
1. Elasticsearch недоступний
2. Embedding API не відповідає
3. OpenAI API key невалідний
4. Індекс не створений

### SSE з'єднання обривається

**Причини:**
- Nginx таймаут
- Проксі таймаут
- Firewall блокує

**Рішення в nginx.conf:**
```nginx
location /chat/search/sse {
    proxy_pass http://api:8000/chat/search/sse;
    proxy_read_timeout 3600s;  # 1 година
    proxy_buffering off;
    proxy_cache off;
    chunked_transfer_encoding off;
}
```

### Elasticsearch: "max virtual memory areas vm.max_map_count too low"

```bash
# Тимчасово
sudo sysctl -w vm.max_map_count=262144

# Постійно
echo "vm.max_map_count=262144" | sudo tee -a /etc/sysctl.conf
sudo sysctl -p
```

### Out of Memory (OOM)

**Симптоми:**
- Container зупиняється
- Лог: "Killed"
- Java heap space errors

**Діагностика:**
```bash
# Перевірити використання пам'яті
docker stats

# Elasticsearch heap
docker exec elasticsearch-qwen3 cat /proc/1/environ | tr '\0' '\n' | grep ES_JAVA_OPTS
```

**Рішення:**
```yaml
# docker-compose.yml
services:
  elasticsearch:
    environment:
      - ES_JAVA_OPTS=-Xms2g -Xmx2g  # Зменшити якщо потрібно
```

### Кеш не працює / низький hit rate

**Перевірка:**
```bash
curl http://localhost:8080/cache/stats
```

**Причини:**
1. **Малий розмір кешу:**
   ```env
   EMBED_CACHE_SIZE=5000  # Збільшити
   ```

2. **Короткий TTL:**
   ```env
   CACHE_TTL_SECONDS=7200  # Збільшити
   ```

3. **Різні формулювання запитів** — нормально, це не баг

### GPT повертає помилки

**Помилка 429: "Rate limit exceeded"**
```
Рішення: Зачекати або збільшити ліміт в OpenAI dashboard
```

**Помилка 401: "Invalid API key"**
```env
# Перевірити ключ
OPENAI_API_KEY=sk-...  # Має починатися з sk-
```

**Timeout:**
```env
# Збільшити timeout
GPT_ANALYZE_TIMEOUT_SECONDS=15.0
GPT_RECO_TIMEOUT_SECONDS=20.0
```

---

## Контакти та підтримка

### Де отримати допомогу?

1. **Документація:** Перевірте всі MD файли в `/docs`
2. **Логи:** `docker-compose logs -f`
3. **GitHub Issues:** Створіть issue з деталями
4. **Email:** support@ta-da.net.ua

### Як повідомити про баг?

**Шаблон issue:**
```markdown
## Опис проблеми
Короткий опис

## Кроки відтворення
1. Відкрити...
2. Натиснути...
3. Побачити помилку...

## Очікувана поведінка
Що має відбутися

## Фактична поведінка
Що відбувається насправді

## Середовище
- OS: Ubuntu 22.04
- Docker version: 24.0.5
- Browser: Chrome 118

## Логи
```
Вставити relevant логи
```

## Скріншоти
Якщо можливо
```

---

**Версія:** 1.0.0  
**Дата оновлення:** 13 жовтня 2025

**Не знайшли відповідь?** Створіть issue на GitHub! 🚀

