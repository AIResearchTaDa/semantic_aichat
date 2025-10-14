# 📁 Структура проекту — Семантичний Пошук TA-DA!

## Повна структура файлів та директорій

```
EmbeddingsQwen3/
│
├── 📄 README.md                          # Головний документ проекту
├── 📄 QUICK_START.md                     # Швидкий старт (5 хвилин)
├── 📄 CHANGELOG.md                       # Історія змін
├── 📄 LICENSE                            # Ліцензія (Proprietary)
├── 📄 CONTRIBUTING.md                    # Гайд для контрибуторів
├── 📄 PROJECT_STRUCTURE.md               # Цей файл
│
├── 📄 docker-compose.yml                 # Docker Compose конфігурація
├── 📄 nginx.conf                         # Nginx конфігурація
├── 📄 .gitignore                         # Git ignore файл
│
├── 📂 docs/                              # Документація
│   ├── 📄 INDEX.md                       # Індекс документації
│   ├── 📄 API_DOCUMENTATION.md           # API документація (30 хв)
│   ├── 📄 ARCHITECTURE.md                # Архітектура системи (45 хв)
│   ├── 📄 DEPLOYMENT_GUIDE.md            # Deployment гайд (60 хв)
│   ├── 📄 DEVELOPER_GUIDE.md             # Гайд для розробників (40 хв)
│   └── 📄 FAQ.md                         # Поширені питання (30 хв)
│
├── 📂 backend/                           # Backend додаток (Python)
│   ├── 📄 main.py                        # Головний FastAPI додаток (~3150 рядків)
│   ├── 📄 search_logger.py               # Модуль логування пошуку (282 рядки)
│   ├── 📄 reindex_products.py            # Скрипт реіндексації (345 рядків)
│   ├── 📄 requirements.txt               # Python залежності
│   ├── 📄 Dockerfile                     # Docker образ для API
│   ├── 📄 .env                           # Змінні середовища (НЕ в git)
│   ├── 📄 .env.example                   # Приклад .env
│   ├── 📄 products.json                  # Дані товарів
│   ├── 📂 __pycache__/                   # Python cache
│   └── 📂 search_logs/                   # Логи пошуку
│       ├── 📄 search_queries.json        # JSON логи
│       └── 📄 search_queries_readable.txt # Читабельні логи
│
├── 📂 web/                               # Frontend (HTML/CSS/JS)
│   ├── 📄 index.html                     # Головна сторінка (269 рядків)
│   ├── 📄 scripts.js                     # JavaScript логіка (~4411 рядків)
│   ├── 📄 styles.css                     # CSS стилі (~2676 рядків)
│   └── 📂 images/                        # Зображення та іконки
│       ├── 🖼️ logo_aitada.png            # Логотип AI (головний)
│       ├── 🖼️ logo_aitada4.png           # Логотип AI (варіант 4)
│       ├── 🖼️ logo_iatada2.png           # Логотип (варіант 2)
│       ├── 🖼️ tada_logo2.png             # Логотип TA-DA
│       ├── 🖼️ icon_ai2.png               # Іконка AI
│       └── 🖼️ icon_search.png            # Іконка пошуку
│
└── 📂 elasticsearch/                     # Elasticsearch конфігурація
    └── 📄 Dockerfile                     # Dockerfile з українським плагіном
```

---

## Детальний опис компонентів

### 📄 Кореневі файли

| Файл | Призначення | Для кого |
|------|-------------|----------|
| `README.md` | Повний опис проекту | Всі |
| `QUICK_START.md` | Швидкий старт за 5 хвилин | Всі |
| `CHANGELOG.md` | Історія змін проекту | Всі |
| `LICENSE` | Ліцензія (Proprietary) | Всі |
| `CONTRIBUTING.md` | Правила контрибуції | Розробники |
| `PROJECT_STRUCTURE.md` | Структура проекту (цей файл) | Всі |
| `docker-compose.yml` | Конфігурація Docker сервісів | DevOps |
| `nginx.conf` | Конфігурація веб-сервера | DevOps |

---

### 📂 Директорія `docs/`

**Повна документація проекту**

| Файл | Розмір | Час читання | Призначення |
|------|--------|-------------|-------------|
| `INDEX.md` | ~6 KB | 10 хв | Індекс всієї документації |
| `API_DOCUMENTATION.md` | ~35 KB | 30 хв | Повна API специфікація |
| `ARCHITECTURE.md` | ~45 KB | 45 хв | Архітектура та алгоритми |
| `DEPLOYMENT_GUIDE.md` | ~50 KB | 60 хв | Production deployment |
| `DEVELOPER_GUIDE.md` | ~40 KB | 40 хв | Гайд для розробників |
| `FAQ.md` | ~30 KB | 30 хв | Поширені питання |

**Загальний обсяг документації:** ~206 KB, ~3.5 години читання

---

### 📂 Директорія `backend/`

**Python Backend (FastAPI)**

#### Основні файли

**`main.py`** (~3150 рядків)
```python
# Структура:
1. Імпорти та налаштування (1-100)
2. Data Models (100-250)
3. Кеш та утиліти (250-500)
4. Embedding Manager (500-800)
5. GPT Integration (800-1200)
6. Search Engine (1200-2000)
7. API Endpoints (2000-3000)
8. Search Logging (3000-3150)
```

**`search_logger.py`** (282 рядки)
```python
# Класи:
- SearchLogger: Основний клас логування
  
# Методи:
- log_search_query(): Логувати запит
- get_session_logs(): Отримати логи сесії
- generate_session_report(): Створити звіт
- export_all_sessions_report(): Експорт звітів
```

**`reindex_products.py`** (345 рядків)
```python
# Функції:
- combine_product_text_for_embedding(): Об'єднати поля
- generate_embedding(): Згенерувати embedding
- load_products(): Завантажити товари
- reindex_products(): Головна функція реіндексації
```

#### Конфігураційні файли

**`requirements.txt`** (12 залежностей)
```
fastapi==0.104.1
uvicorn[standard]==0.24.0
elasticsearch==8.11.0
httpx==0.25.2
pydantic==2.5.0
pydantic-settings==2.1.0
python-dotenv==1.0.0
tenacity==8.2.3
tqdm==4.66.1
aiohttp==3.9.1
pytest==7.4.4
pytest-asyncio==0.23.3
```

**`.env`** (змінні середовища)
```env
# Розділи:
- Elasticsearch
- Embedding API
- GPT
- Search settings
- Chat search
- Lazy loading
- Recommendations
- TA-DA API
```

#### Дані

**`products.json`** — База товарів
- Формат: JSON Lines (JSONL)
- Структура: Масив об'єктів товарів
- Поля: uuid, title_ua, title_ru, description_ua, description_ru, price, category, sku, etc.

#### Логи

**`search_logs/`** — Директорія логів
- `search_queries.json` — JSON формат для програмної обробки
- `search_queries_readable.txt` — Форматований текст для людей

---

### 📂 Директорія `web/`

**Frontend (Vanilla JavaScript)**

#### HTML

**`index.html`** (269 рядків)
```html
<!-- Секції: -->
1. <head> — Meta, fonts, styles (1-16)
2. <header> — Навігація та пошук (18-84)
3. <main> — Контент сторінок (85-204)
   - #welcomePage — Привітальна сторінка
   - #simpleSearchPage — Простий пошук
   - #chatSearchPage — AI чат-пошук
4. <footer> — Футер (248-249)
5. Модальні вікна (210-260)
   - #full-cart — Повний кошик
   - #image-zoom-overlay — Зум зображень
```

#### JavaScript

**`scripts.js`** (~4411 рядків)
```javascript
// Модулі:
1. Конфігурація (1-100)
2. Глобальні змінні (100-200)
3. Утиліти (200-400)
4. UI Management (400-800)
5. Простий пошук (800-1200)
6. AI Чат-пошук (1200-2500)
7. Product Rendering (2500-3200)
8. Cart Management (3200-3800)
9. Event Listeners (3800-4400)
```

**Основні функції:**
- `performSimpleSearch()` — Простий пошук
- `performChatSearch()` — AI пошук
- `handleSSEStream()` — SSE потік
- `renderProductCard()` — Картка товару
- `addToCart()` / `removeFromCart()` — Кошик
- `updateCartUI()` — Оновлення UI кошика

#### CSS

**`styles.css`** (~2676 рядків)
```css
/* Структура: */
1. Reset & Base styles (1-200)
2. Layout (200-500)
3. Header & Navigation (500-800)
4. Pages (800-1200)
   - Welcome page
   - Search page
   - Chat page
5. Components (1200-2000)
   - Product cards
   - Carousel
   - Cart
   - Recommendations
6. Animations (2000-2300)
7. Responsive (2300-2676)
   - Mobile (< 768px)
   - Tablet (768px - 1024px)
   - Desktop (> 1024px)
```

#### Зображення

**`images/`** — Графічні ресурси
- Формат: PNG
- Використання: Логотипи, іконки, UI елементи
- Оптимізація: Стиснуті для веб

---

### 📂 Директорія `elasticsearch/`

**Elasticsearch Docker Image**

**`Dockerfile`** (3 рядки)
```dockerfile
FROM elasticsearch:8.11.1
RUN bin/elasticsearch-plugin install analysis-ukrainian
```

**Призначення:**
- Базовий образ Elasticsearch 8.11.1
- Плагін для української морфології
- Використовується в docker-compose.yml

---

## Розміри та метрики

### Кількість рядків коду

| Компонент | Мова | Рядків коду |
|-----------|------|-------------|
| Backend | Python | ~3,800 |
| Frontend HTML | HTML | ~270 |
| Frontend JS | JavaScript | ~4,400 |
| Frontend CSS | CSS | ~2,700 |
| **Загалом код** | | **~11,170** |
| Документація | Markdown | ~206 KB |

### Розмір файлів

```bash
# Backend
main.py              ~130 KB
search_logger.py     ~8 KB
reindex_products.py  ~12 KB

# Frontend
index.html           ~12 KB
scripts.js           ~160 KB
styles.css           ~85 KB

# Images
logo_aitada.png      ~150 KB
other images         ~50-100 KB each

# Documentation
README.md            ~45 KB
API_DOCUMENTATION.md ~35 KB
ARCHITECTURE.md      ~45 KB
DEPLOYMENT_GUIDE.md  ~50 KB
DEVELOPER_GUIDE.md   ~40 KB
FAQ.md              ~30 KB
```

---

## Docker Volumes

```bash
# Створені volumes:
embeddingsqwen3_elasticsearch-data    # Дані Elasticsearch
embeddingsqwen3_semantic-search-net   # Docker network
```

---

## Gitignore

**Що ігнорується:**

```gitignore
# Python
__pycache__/
*.py[cod]
*$py.class
venv/
env/

# Environment
.env
.env.local
.env.production

# Logs
*.log
search_logs/*.json
search_logs/*.txt

# Docker
docker-compose.override.yml

# IDE
.vscode/
.idea/
*.swp

# OS
.DS_Store
Thumbs.db

# Backups
*.tar.gz
backup_*/

# Data
products.json (якщо великий)
```

---

## Порядок читання документації

### Для початківців
1. ✅ README.md (20 хв)
2. ✅ QUICK_START.md (5 хв)
3. ✅ FAQ.md (30 хв)

### Для розробників
1. ✅ README.md (20 хв)
2. ✅ DEVELOPER_GUIDE.md (40 хв)
3. ✅ ARCHITECTURE.md (45 хв)
4. ✅ API_DOCUMENTATION.md (30 хв)

### Для DevOps
1. ✅ README.md (20 хв)
2. ✅ DEPLOYMENT_GUIDE.md (60 хв)
3. ✅ ARCHITECTURE.md (45 хв)

### Для архітекторів
1. ✅ README.md (20 хв)
2. ✅ ARCHITECTURE.md (45 хв)
3. ✅ API_DOCUMENTATION.md (30 хв)

---

## Швидкі посилання

### Документація
- 📘 [README](README.md)
- ⚡ [Quick Start](QUICK_START.md)
- 📚 [Docs Index](docs/INDEX.md)
- 📡 [API Docs](docs/API_DOCUMENTATION.md)
- 🏗️ [Architecture](docs/ARCHITECTURE.md)
- 🚀 [Deployment](docs/DEPLOYMENT_GUIDE.md)
- 👨‍💻 [Developer Guide](docs/DEVELOPER_GUIDE.md)
- ❓ [FAQ](docs/FAQ.md)

### Код
- 🐍 [Backend Main](backend/main.py)
- 📊 [Search Logger](backend/search_logger.py)
- 🔄 [Reindex Script](backend/reindex_products.py)
- 🌐 [Frontend HTML](web/index.html)
- ⚙️ [Frontend JS](web/scripts.js)
- 🎨 [Frontend CSS](web/styles.css)

### Конфігурація
- 🐳 [Docker Compose](docker-compose.yml)
- 🔧 [Nginx Config](nginx.conf)
- 🔍 [ES Dockerfile](elasticsearch/Dockerfile)

---

**Версія:** 1.0.0  
**Дата оновлення:** 13 жовтня 2025  
**Статус:** Complete ✅

