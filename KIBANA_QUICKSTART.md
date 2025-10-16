# 🚀 Kibana - Швидкий старт

## ✅ Все вже налаштовано!

### 📍 Доступ до Kibana

**URL:** http://10.2.0.171:5601

*(з локального сервера: http://localhost:5601)*

### 👤 Облікові записи

| Користувач | Логін | Пароль | Права |
|------------|-------|--------|-------|
| **Адміністратор** | `elastic` | `changeme` | Повний доступ |
| **Перегляд даних** | `kibana_viewer` | `viewer123` | Тільки читання |

⚠️ **Обов'язково змініть паролі після першого входу!**

---

## 🎯 Перші кроки

### 1. Відкрийте Kibana
Перейдіть на http://10.2.0.171:5601 та увійдіть

### 2. Створіть Data View
1. ☰ → **Discover**
2. **Create a data view**
3. **Index pattern:** `products*`
4. **Save**

### 3. Почніть працювати
- **Discover** - пошук та перегляд товарів
- **Dev Tools** - запити до Elasticsearch
- **Visualize** - створення графіків
- **Dashboard** - дашборди

---

## 📖 Детальна інструкція

Дивіться повну інструкцію в файлі: **[KIBANA_GUIDE.md](./KIBANA_GUIDE.md)**

---

## 🔧 Управління

### Запуск/зупинка
```bash
# Запустити все
docker-compose up -d

# Тільки Kibana
docker-compose restart kibana

# Зупинити
docker-compose down
```

### Перегляд логів
```bash
docker logs kibana-qwen3
docker logs elasticsearch-qwen3
```

### Зміна пароля
```bash
curl -X POST "http://localhost:9200/_security/user/kibana_viewer/_password" \
  -u elastic:changeme \
  -H 'Content-Type: application/json' \
  -d '{"password": "НОВИЙ_ПАРОЛЬ"}'
```

---

## 🆘 Проблеми?

**Kibana не відкривається?**
- Зачекайте 30-60 секунд після запуску
- Перевірте: `docker logs kibana-qwen3`

**Не можу увійти?**
- Перевірте логін/пароль
- За замовчуванням: `elastic` / `changeme`

**Не бачу дані?**
- Переконайтеся що індекс існує: http://localhost:9200/_cat/indices?v
- Створіть Data View з патерном `products*`

---

Успіхів! 🎉

