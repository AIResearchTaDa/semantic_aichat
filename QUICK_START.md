# ⚡ Швидкий старт — Семантичний Пошук TA-DA!

## 🚀 Запуск за 5 хвилин

### Крок 1: Клонування та налаштування

```bash
# Клонувати репозиторій
git clone <repository-url>
cd EmbeddingsQwen3

# Створити Docker мережу
docker network create embeddingsqwen3_semantic-search-net

# Створити volume
docker volume create embeddingsqwen3_elasticsearch-data
```

### Крок 2: Налаштування змінних середовища

```bash
# Створити .env файл
cat > backend/.env << 'EOF'
# Elasticsearch
ELASTIC_URL=http://elasticsearch-qwen3:9200
INDEX_NAME=products_qwen3_8b

# Embedding API (замініть на ваш IP)
EMBEDDING_API_URL=http://10.2.0.171:9001/api/embeddings
OLLAMA_MODEL_NAME=dengcao/Qwen3-Embedding-8B:Q8_0

# OpenAI (опціонально)
OPENAI_API_KEY=sk-your-key-here
ENABLE_GPT_CHAT=true

# TA-DA API
TA_DA_API_TOKEN=your-token-here
EOF
```

### Крок 3: Запуск

```bash
# Запустити всі сервіси
docker-compose up -d

# Перевірити статус
docker-compose ps
```

### Крок 4: Перевірка

```bash
# Перевірити здоров'я сервісів
curl http://localhost:8080/health

# Відкрити веб-інтерфейс
open http://localhost:8080
```

### Крок 5: Індексація товарів (якщо потрібно)

```bash
docker exec -it api_qwen3 python reindex_products.py
```

## ✅ Готово!

Система запущена та готова до використання!

---

## 📚 Що далі?

### Для користувачів
- Відкрийте http://localhost:8080
- Спробуйте **Простий пошук**: "олівці кольорові"
- Спробуйте **AI пошук**: "Що подарувати дитині на 5 років?"

### Для розробників
- Читайте [Developer Guide](docs/DEVELOPER_GUIDE.md)
- Вивчіть [API Documentation](docs/API_DOCUMENTATION.md)
- Перегляньте [Architecture](docs/ARCHITECTURE.md)

### Для адміністраторів
- Налаштуйте згідно [Deployment Guide](docs/DEPLOYMENT_GUIDE.md)
- Встановіть моніторинг
- Налаштуйте backup

---

## 🔧 Швидкі команди

```bash
# Переглянути логи
docker-compose logs -f

# Перезапустити сервіс
docker-compose restart api

# Зупинити все
docker-compose down

# Очистити кеш
curl -X POST http://localhost:8080/cache/clear

# Подивитися статистику
curl http://localhost:8080/stats
```

---

## ❓ Проблеми?

Дивіться [FAQ](docs/FAQ.md) або [Troubleshooting](docs/DEPLOYMENT_GUIDE.md#troubleshooting)

---

## 📖 Повна документація

- **[README.md](README.md)** — Повний опис проекту
- **[API_DOCUMENTATION.md](docs/API_DOCUMENTATION.md)** — Документація API
- **[ARCHITECTURE.md](docs/ARCHITECTURE.md)** — Архітектура системи
- **[DEPLOYMENT_GUIDE.md](docs/DEPLOYMENT_GUIDE.md)** — Інструкція з deployment
- **[DEVELOPER_GUIDE.md](docs/DEVELOPER_GUIDE.md)** — Посібник для розробників
- **[FAQ.md](docs/FAQ.md)** — Поширені питання

---

**Версія:** 1.0.0  
**Автор:** TA-DA! Development Team  
**Дата:** 13 жовтня 2025

