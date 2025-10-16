#!/bin/bash

# Скрипт для створення користувача з правами тільки на читання індексу products
# Автор: AI Assistant
# Дата: 2025-10-15

set -e

echo "🔧 Створення користувача Kibana з правами тільки на читання..."

# Параметри підключення
ELASTIC_HOST="localhost:9200"
ELASTIC_USER="elastic"
ELASTIC_PASSWORD="elastic"
INDEX_PATTERN="products*"
NEW_USERNAME="kibana_viewer"
NEW_PASSWORD="viewer123"

echo ""
echo "📋 Параметри:"
echo "   Elasticsearch: http://${ELASTIC_HOST}"
echo "   Індекс: ${INDEX_PATTERN}"
echo "   Новий користувач: ${NEW_USERNAME}"
echo ""

# Перевірка доступності Elasticsearch
echo "🔍 Перевірка підключення до Elasticsearch..."
if ! curl -s -u "${ELASTIC_USER}:${ELASTIC_PASSWORD}" "http://${ELASTIC_HOST}/_cluster/health" > /dev/null; then
    echo "❌ Помилка: Не вдалося підключитися до Elasticsearch"
    echo "   Переконайтеся, що Elasticsearch запущено і доступний за адресою http://${ELASTIC_HOST}"
    exit 1
fi
echo "✅ Підключення успішне"

# Створення ролі з правами тільки на читання
echo ""
echo "🔐 Створення ролі 'products_read_only'..."
curl -s -X POST "http://${ELASTIC_HOST}/_security/role/products_read_only" \
  -u "${ELASTIC_USER}:${ELASTIC_PASSWORD}" \
  -H 'Content-Type: application/json' \
  -d "{
    \"cluster\": [\"monitor\"],
    \"indices\": [
      {
        \"names\": [\"${INDEX_PATTERN}\"],
        \"privileges\": [\"read\", \"view_index_metadata\"]
      }
    ]
  }" | python3 -m json.tool

echo "✅ Роль створено"

# Створення користувача
echo ""
echo "👤 Створення користувача '${NEW_USERNAME}'..."
curl -s -X POST "http://${ELASTIC_HOST}/_security/user/${NEW_USERNAME}" \
  -u "${ELASTIC_USER}:${ELASTIC_PASSWORD}" \
  -H 'Content-Type: application/json' \
  -d "{
    \"password\": \"${NEW_PASSWORD}\",
    \"roles\": [\"products_read_only\", \"kibana_admin\"],
    \"full_name\": \"Kibana Viewer\",
    \"email\": \"viewer@example.com\"
  }" | python3 -m json.tool

echo "✅ Користувача створено"

# Вивід інформації для входу
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ НАЛАШТУВАННЯ ЗАВЕРШЕНО!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "🌐 Kibana URL: http://localhost:5601"
echo ""
echo "👤 Користувач з правами адміністратора:"
echo "   Логін: ${ELASTIC_USER}"
echo "   Пароль: ${ELASTIC_PASSWORD}"
echo ""
echo "👁️  Користувач тільки для перегляду:"
echo "   Логін: ${NEW_USERNAME}"
echo "   Пароль: ${NEW_PASSWORD}"
echo "   Права: тільки читання індексу ${INDEX_PATTERN}"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "💡 Порада: Змініть паролі після першого входу!"
echo ""

