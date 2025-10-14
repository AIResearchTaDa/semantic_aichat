# Швидке налаштування проекту

## 1. Клонування репозиторію

```bash
git clone https://github.com/AIResearchTaDa/semantic_aichat.git
cd semantic_aichat
```

## 2. Налаштування змінних середовища

Створіть файл `backend/.env` на основі прикладу:

```bash
cp backend/.env.example backend/.env
```

Відредагуйте `backend/.env` та додайте свої API ключі:

```bash
# ВАЖЛИВО: Заміните на ваші реальні ключі!
OPENAI_API_KEY=your_openai_api_key_here
TA_DA_API_TOKEN=your_ta_da_api_token_here
```

### Де отримати API ключі:

- **OpenAI API Key**: https://platform.openai.com/api-keys
- **TA-DA API Token**: з вашого TA-DA dashboard

## 3. Запуск проекту

```bash
docker-compose up -d
```

Проект буде доступний за адресою: http://localhost

## 4. Індексація продуктів

```bash
docker exec -it backend-qwen3 python reindex_products.py
```

## 🔒 Безпека

**ВАЖЛИВО**: Файл `backend/.env` містить секретні ключі і не повинен потрапляти в git!
- ✅ `.env` додано в `.gitignore`
- ✅ Використовуйте `.env.example` як шаблон
- ❌ Ніколи не commit'те файл `.env`

## 📚 Детальна документація

Дивіться повну документацію:
- [README.md](README.md) - загальний огляд проекту
- [QUICK_START.md](QUICK_START.md) - швидкий старт
- [docs/](docs/) - детальна документація

