# 📊 Інструкція по використанню Kibana для перегляду даних Elasticsearch

## 🎯 Що таке Kibana?

Kibana - це веб-інтерфейс для Elasticsearch, який дозволяє:
- 🔍 Переглядати та шукати дані в індексах
- 📈 Створювати візуалізації та дашборди
- 🔧 Управляти Elasticsearch (для адміністраторів)
- 📊 Аналізувати дані в реальному часі

---

## 🚀 Швидкий старт

### 1. Відкрийте Kibana в браузері

```
http://10.2.0.171:5601
```

або з локального сервера:
```
http://localhost:5601
```

### 2. Виберіть обліковий запис для входу

**👤 Для адміністраторів (повний доступ):**
- **Логін:** `elastic`
- **Пароль:** `elastic`

**👁️ Для перегляду даних (тільки читання):**
- **Логін:** `kibana_viewer`
- **Пароль:** `kibana_viewer`

> ⚠️ **ВАЖЛИВО:** Змініть паролі після першого входу!

---

## 📖 Основні можливості Kibana

### 🔍 1. Discover - Пошук та перегляд документів

**Як використовувати:**

1. **Відкрийте меню** (☰ зліва зверху) → **Discover**

2. **Створіть Data View** (якщо ще немає):
   - Натисніть **"Create a data view"**
   - **Name:** `Products`
   - **Index pattern:** `products*` (це знайде всі індекси що починаються з "products")
   - **Timestamp field:** оберіть якщо є, або залиште порожнім
   - Натисніть **"Save data view to Kibana"**

3. **Перегляд даних:**
   - Оберіть ваш Data View `Products` у верхньому лівому куті
   - Ви побачите всі документи (товари) з індексу
   - Ліворуч - доступні поля (title_ua, description_ua, price, etc.)
   - Праворуч - самі документи

4. **Пошук:**
   - У рядку пошуку зверху можна вводити запити
   - Приклади:
     ```
     title_ua:"ноутбук"
     price > 10000
     category:"Електроніка"
     sku:123456
     ```

5. **Фільтрація полів:**
   - Натискайте на назви полів ліворуч
   - Оберіть **"Add field as column"** щоб додати колонку
   - Можна додати: `title_ua`, `price`, `category`, `quantity`

### 📊 2. Dev Tools - Консоль для запитів

**Як використовувати:**

1. **Відкрийте** ☰ → **Management** → **Dev Tools**

2. **Перегляд індексу:**
   ```json
   GET /products_qwen3_8b/_search
   {
     "size": 10,
     "query": {
       "match_all": {}
     }
   }
   ```

3. **Пошук за назвою:**
   ```json
   GET /products_qwen3_8b/_search
   {
     "query": {
       "match": {
         "title_ua": "ноутбук"
       }
     }
   }
   ```

4. **Статистика індексу:**
   ```json
   GET /products_qwen3_8b/_stats
   ```

5. **Інформація про mapping (структуру):**
   ```json
   GET /products_qwen3_8b/_mapping
   ```

6. **Пошук товарів в діапазоні цін:**
   ```json
   GET /products_qwen3_8b/_search
   {
     "query": {
       "range": {
         "price": {
           "gte": 1000,
           "lte": 5000
         }
       }
     }
   }
   ```

7. **Агрегації - топ категорій:**
   ```json
   GET /products_qwen3_8b/_search
   {
     "size": 0,
     "aggs": {
       "categories": {
         "terms": {
           "field": "category.keyword",
           "size": 10
         }
       }
     }
   }
   ```

### 📈 3. Visualize - Візуалізації

**Створення діаграм:**

1. **Відкрийте** ☰ → **Visualize Library**
2. **Create visualization**
3. **Оберіть тип:**
   - **Pie chart** - розподіл товарів по категоріях
   - **Bar chart** - ціновий діапазон
   - **Data table** - топ дорогих товарів
   - **Metric** - загальна кількість товарів

**Приклад: Діаграма розподілу по категоріях**
1. Оберіть **Pie**
2. Оберіть Data View `Products`
3. У **Buckets** → **Add** → **Split slices**
4. **Aggregation:** Terms
5. **Field:** `category.keyword`
6. Натисніть **Update** ▶
7. **Save** збережіть візуалізацію

### 🗺️ 4. Dashboard - Дашборди

**Створення дашборду:**

1. ☰ → **Dashboard** → **Create dashboard**
2. **Add** → Додайте створені візуалізації
3. Можна змінювати розмір та розташування
4. **Save** → дайте назву "Products Overview"

---

## 🔧 Корисні запити для вашого індексу products

### Загальна інформація

```json
# Кількість документів
GET /products_qwen3_8b/_count

# Статистика
GET /products_qwen3_8b/_stats

# Перші 20 товарів
GET /products_qwen3_8b/_search
{
  "size": 20,
  "_source": ["title_ua", "price", "category", "quantity"]
}
```

### Аналітичні запити

```json
# Середня ціна товарів
GET /products_qwen3_8b/_search
{
  "size": 0,
  "aggs": {
    "avg_price": {
      "avg": {
        "field": "price"
      }
    },
    "min_price": {
      "min": {
        "field": "price"
      }
    },
    "max_price": {
      "max": {
        "field": "price"
      }
    }
  }
}

# Товари в наявності vs закінчились
GET /products_qwen3_8b/_search
{
  "size": 0,
  "aggs": {
    "stock_status": {
      "range": {
        "field": "quantity",
        "ranges": [
          { "key": "Немає в наявності", "to": 1 },
          { "key": "Мало", "from": 1, "to": 5 },
          { "key": "В наявності", "from": 5 }
        ]
      }
    }
  }
}

# Топ-10 найдорожчих товарів
GET /products_qwen3_8b/_search
{
  "size": 10,
  "sort": [
    { "price": "desc" }
  ],
  "_source": ["title_ua", "price", "category"]
}
```

### Пошук за текстом

```json
# Повнотекстовий пошук
GET /products_qwen3_8b/_search
{
  "query": {
    "multi_match": {
      "query": "ігровий ноутбук",
      "fields": ["title_ua^3", "description_ua", "title_ru", "description_ru"]
    }
  }
}

# Пошук з автодоповненням
GET /products_qwen3_8b/_search
{
  "query": {
    "match_phrase_prefix": {
      "title_ua": "ноут"
    }
  }
}
```

---

## 🛡️ Управління користувачами (тільки для elastic)

### Зміна пароля

```bash
# Через консоль
curl -X POST "http://localhost:9200/_security/user/kibana_viewer/_password" \
  -u elastic:changeme \
  -H 'Content-Type: application/json' \
  -d '{"password": "новий_пароль"}'
```

Або через Kibana:
1. ☰ → **Stack Management** → **Security** → **Users**
2. Оберіть користувача
3. **Change password**

### Створення нового користувача read-only

```bash
# 1. Створіть роль
curl -X POST "http://localhost:9200/_security/role/products_readonly" \
  -u elastic:changeme \
  -H 'Content-Type: application/json' \
  -d '{
    "cluster": ["monitor"],
    "indices": [{
      "names": ["products*"],
      "privileges": ["read", "view_index_metadata"]
    }]
  }'

# 2. Створіть користувача
curl -X POST "http://localhost:9200/_security/user/новий_користувач" \
  -u elastic:changeme \
  -H 'Content-Type: application/json' \
  -d '{
    "password": "пароль",
    "roles": ["products_readonly", "kibana_admin"]
  }'
```

---

## 🔍 Моніторинг та діагностика

### Перевірка здоров'я кластера

```json
GET /_cluster/health

GET /_cat/indices?v

GET /_cat/nodes?v
```

### Перегляд активних запитів

```json
GET /_tasks?detailed=true&actions=*search*
```

---

## 💡 Корисні поради

### 1. **Продуктивність**
- Обмежуйте розмір результатів (`"size": 100` замість `10000`)
- Використовуйте фільтри замість запитів де можливо
- Для великих датасетів використовуйте aggregations

### 2. **Пошук**
- `^3` в multi_match - це boost (підвищення важливості поля)
- `match` - повнотекстовий пошук з аналізом
- `term` - точний пошук (для keyword полів)
- `match_phrase` - пошук фрази

### 3. **Безпека**
- Регулярно змінюйте паролі
- Не давайте права адміністратора без потреби
- Користувач `kibana_viewer` має тільки читання - безпечно для аналітиків

### 4. **Експорт даних**
- У Discover можна експортувати в CSV через меню Share
- Для великих експортів краще використовувати API

---

## 🆘 Вирішення проблем

### Kibana не відкривається
```bash
# Перевірте статус контейнера
docker ps | grep kibana

# Перегляньте логи
docker logs kibana-qwen3
```

### Не можу увійти
- Переконайтеся що використовуєте правильний логін/пароль
- За замовчуванням: `elastic` / `changeme`
- Зачекайте 30 секунд після запуску контейнерів

### Не бачу індекс products
```bash
# Перевірте чи існує індекс
curl -u elastic:changeme http://localhost:9200/_cat/indices?v
```

### Помилка авторизації
- Переконайтеся що в `.env` правильні `ELASTIC_USER` та `ELASTIC_PASSWORD`
- Перезапустіть контейнери: `docker-compose restart`

---

## 📚 Додаткові ресурси

- [Офіційна документація Kibana](https://www.elastic.co/guide/en/kibana/current/index.html)
- [Query DSL](https://www.elastic.co/guide/en/elasticsearch/reference/current/query-dsl.html)
- [Aggregations](https://www.elastic.co/guide/en/elasticsearch/reference/current/search-aggregations.html)

---

## 🎓 Висновок

Тепер ви маєте повністю налаштовану Kibana для перегляду та аналізу ваших товарів!

**Швидкий чеклист:**
- ✅ Kibana доступна на http://localhost:5601
- ✅ Користувач адміністратора: `elastic` / `changeme`
- ✅ Користувач для перегляду: `kibana_viewer` / `viewer123`
- ✅ Індекс: `products_qwen3_8b`
- ✅ Elasticsearch з автентифікацією працює

**Наступні кроки:**
1. 🔐 Змініть паролі на безпечні
2. 📊 Створіть Data View для вашого індексу
3. 🔍 Почніть досліджувати дані в Discover
4. 📈 Створіть візуалізації та дашборди

Успішної роботи! 🚀

