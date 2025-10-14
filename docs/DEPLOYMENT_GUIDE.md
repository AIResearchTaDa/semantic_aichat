# 🚀 Deployment Guide — Семантичний Пошук TA-DA!

## Зміст
- [Передумови](#передумови)
- [Development Environment](#development-environment)
- [Production Deployment](#production-deployment)
- [Конфігурація середовищ](#конфігурація-середовищ)
- [Моніторинг](#моніторинг)
- [Резервне копіювання](#резервне-копіювання)
- [Troubleshooting](#troubleshooting)

---

## Передумови

### Системні вимоги

**Мінімальні:**
- CPU: 4 cores
- RAM: 8 GB
- Disk: 50 GB SSD
- OS: Ubuntu 20.04+ / CentOS 8+ / macOS

**Рекомендовані (Production):**
- CPU: 8+ cores
- RAM: 16+ GB
- Disk: 100+ GB SSD (NVMe)
- OS: Ubuntu 22.04 LTS

### Програмне забезпечення

**Обов'язково:**
- Docker 24.0+
- Docker Compose 2.20+
- Git

**Опціонально:**
- kubectl (для Kubernetes)
- nginx (якщо не в Docker)
- certbot (для SSL)

---

## Development Environment

### 1. Клонування репозиторію

```bash
git clone <repository-url>
cd EmbeddingsQwen3
```

### 2. Налаштування змінних середовища

Створіть файл `backend/.env`:

```bash
cat > backend/.env << 'EOF'
# Elasticsearch
ELASTIC_URL=http://elasticsearch-qwen3:9200
INDEX_NAME=products_qwen3_8b
VECTOR_DIMENSION=4096
VECTOR_FIELD_NAME=description_vector

# Embedding API (Ollama)
EMBEDDING_API_URL=http://10.2.0.171:9001/api/embeddings
OLLAMA_MODEL_NAME=dengcao/Qwen3-Embedding-8B:Q8_0
EMBED_CACHE_SIZE=2000
CACHE_TTL_SECONDS=3600
EMBEDDING_MAX_CONCURRENT=2

# Search settings
KNN_NUM_CANDIDATES=500
HYBRID_ALPHA=0.7
HYBRID_FUSION=weighted
BM25_MIN_SCORE=5.0

# GPT (опціонально)
OPENAI_API_KEY=sk-your-key-here
GPT_MODEL=gpt-4o-mini
ENABLE_GPT_CHAT=true
GPT_TEMPERATURE=0.3
GPT_MAX_TOKENS_ANALYZE=250
GPT_MAX_TOKENS_RECO=500
GPT_ANALYZE_TIMEOUT_SECONDS=10.0
GPT_RECO_TIMEOUT_SECONDS=15.0

# Chat search
CHAT_SEARCH_SCORE_THRESHOLD_RATIO=0.4
CHAT_SEARCH_MIN_SCORE_ABSOLUTE=0.3
CHAT_SEARCH_SUBQUERY_WEIGHT_DECAY=0.85
CHAT_SEARCH_MAX_K_PER_SUBQUERY=20

# Lazy loading
INITIAL_PRODUCTS_BATCH=20
LOAD_MORE_BATCH_SIZE=20
SEARCH_RESULTS_TTL_SECONDS=3600

# Recommendations
RECO_DETAILED_COUNT=3
GROUNDED_RECOMMENDATIONS=true

# TA-DA API
TA_DA_API_BASE_URL=https://api.ta-da.net.ua/v1.2/mobile
TA_DA_API_TOKEN=your-token-here
TA_DA_DEFAULT_SHOP_ID=8
TA_DA_DEFAULT_LANGUAGE=ua
EOF
```

### 3. Створення Docker мережі та volumes

```bash
# Створити мережу
docker network create embeddingsqwen3_semantic-search-net

# Створити volume для Elasticsearch
docker volume create embeddingsqwen3_elasticsearch-data
```

### 4. Запуск сервісів

```bash
# Запустити всі сервіси
docker-compose up -d

# Переглянути логи
docker-compose logs -f

# Перевірити статус
docker-compose ps
```

### 5. Перевірка здоров'я

```bash
# Elasticsearch
curl http://localhost:9200/_cluster/health

# API
curl http://localhost:8080/health

# Web UI
open http://localhost:8080
```

### 6. Індексація товарів

```bash
# Якщо файл products.json існує
docker exec -it api_qwen3 python reindex_products.py

# Подивитися прогрес
docker exec -it api_qwen3 tail -f /app/indexing.log
```

---

## Production Deployment

### Архітектура Production

```
Internet
    ↓
[CloudFlare CDN] (опціонально)
    ↓
[Load Balancer / nginx]
    ↓
┌────────────────────────────────┐
│      Docker Host / K8s         │
│                                │
│  ┌──────────────────────────┐ │
│  │  nginx (SSL termination)  │ │
│  └────────────┬──────────────┘ │
│               │                │
│  ┌────────────┴──────────────┐ │
│  │  API Instances (x2+)      │ │
│  │  (Load balanced)          │ │
│  └────────────┬──────────────┘ │
│               │                │
│  ┌────────────┴──────────────┐ │
│  │  Elasticsearch Cluster    │ │
│  │  (3 nodes minimum)        │ │
│  └───────────────────────────┘ │
│                                │
│  ┌───────────────────────────┐ │
│  │  Redis (Shared cache)     │ │
│  └───────────────────────────┘ │
└────────────────────────────────┘
         │
         ▼
[External Services]
- Ollama API
- OpenAI API
- TA-DA API
```

### 1. Підготовка сервера

```bash
# Оновлення системи
sudo apt update && sudo apt upgrade -y

# Встановлення Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker $USER

# Встановлення Docker Compose
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose

# Налаштування системних лімітів
sudo sysctl -w vm.max_map_count=262144
echo "vm.max_map_count=262144" | sudo tee -a /etc/sysctl.conf

# Налаштування file descriptors
sudo tee -a /etc/security/limits.conf << EOF
* soft nofile 65536
* hard nofile 65536
EOF
```

### 2. SSL сертифікати (Let's Encrypt)

```bash
# Встановлення certbot
sudo apt install certbot python3-certbot-nginx

# Отримання сертифікату
sudo certbot certonly --standalone \
  -d your-domain.com \
  -d www.your-domain.com

# Автоматичне оновлення
sudo certbot renew --dry-run
```

### 3. Production nginx.conf

Створіть `/etc/nginx/sites-available/semantic-search`:

```nginx
# Upstream для API
upstream api_backend {
    least_conn;
    server 127.0.0.1:8001 max_fails=3 fail_timeout=30s;
    server 127.0.0.1:8002 max_fails=3 fail_timeout=30s;
    keepalive 32;
}

# HTTP → HTTPS redirect
server {
    listen 80;
    server_name your-domain.com www.your-domain.com;
    return 301 https://$server_name$request_uri;
}

# HTTPS server
server {
    listen 443 ssl http2;
    server_name your-domain.com www.your-domain.com;

    # SSL certificates
    ssl_certificate /etc/letsencrypt/live/your-domain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/your-domain.com/privkey.pem;
    ssl_trusted_certificate /etc/letsencrypt/live/your-domain.com/chain.pem;

    # SSL configuration
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;
    ssl_prefer_server_ciphers on;
    ssl_session_cache shared:SSL:10m;
    ssl_session_timeout 10m;

    # Security headers
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    add_header X-Frame-Options DENY;
    add_header X-Content-Type-Options nosniff;
    add_header X-XSS-Protection "1; mode=block";

    # Compression
    gzip on;
    gzip_vary on;
    gzip_min_length 1024;
    gzip_types text/plain text/css text/xml text/javascript application/javascript application/json;

    # Static files
    root /var/www/semantic-search;
    index index.html;

    # Static assets with caching
    location ~* \.(css|js|jpg|jpeg|png|gif|ico|svg|woff|woff2|ttf)$ {
        expires 1y;
        add_header Cache-Control "public, immutable";
    }

    # API endpoints
    location /api/ {
        proxy_pass http://api_backend/;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 180s;
        proxy_connect_timeout 30s;
    }

    # SSE endpoint
    location /chat/search/sse {
        proxy_pass http://api_backend/chat/search/sse;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_buffering off;
        proxy_cache off;
        chunked_transfer_encoding off;
        add_header Cache-Control "no-cache";
        add_header X-Accel-Buffering "no";
        proxy_read_timeout 3600s;
    }

    # Default location
    location / {
        try_files $uri $uri/ /index.html;
    }

    # Rate limiting
    limit_req_zone $binary_remote_addr zone=api_limit:10m rate=60r/m;
    limit_req zone=api_limit burst=20 nodelay;

    # Access and error logs
    access_log /var/log/nginx/semantic-search-access.log;
    error_log /var/log/nginx/semantic-search-error.log;
}
```

Активувати:
```bash
sudo ln -s /etc/nginx/sites-available/semantic-search /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

### 4. Production docker-compose.yml

```yaml
version: '3.8'

services:
  # Elasticsearch cluster
  elasticsearch-master:
    image: elasticsearch:8.11.1
    container_name: es-master
    environment:
      - node.name=es-master
      - cluster.name=semantic-search-cluster
      - discovery.seed_hosts=es-data1,es-data2
      - cluster.initial_master_nodes=es-master
      - xpack.security.enabled=true
      - ELASTIC_PASSWORD=${ELASTIC_PASSWORD}
      - bootstrap.memory_lock=true
      - ES_JAVA_OPTS=-Xms4g -Xmx4g
    ulimits:
      memlock:
        soft: -1
        hard: -1
      nofile:
        soft: 65536
        hard: 65536
    volumes:
      - es-master-data:/usr/share/elasticsearch/data
    networks:
      - semantic-search-net
    restart: always

  elasticsearch-data1:
    image: elasticsearch:8.11.1
    container_name: es-data1
    environment:
      - node.name=es-data1
      - cluster.name=semantic-search-cluster
      - discovery.seed_hosts=es-master,es-data2
      - cluster.initial_master_nodes=es-master
      - xpack.security.enabled=true
      - ELASTIC_PASSWORD=${ELASTIC_PASSWORD}
      - bootstrap.memory_lock=true
      - ES_JAVA_OPTS=-Xms4g -Xmx4g
    ulimits:
      memlock:
        soft: -1
        hard: -1
      nofile:
        soft: 65536
        hard: 65536
    volumes:
      - es-data1-data:/usr/share/elasticsearch/data
    networks:
      - semantic-search-net
    restart: always

  elasticsearch-data2:
    image: elasticsearch:8.11.1
    container_name: es-data2
    environment:
      - node.name=es-data2
      - cluster.name=semantic-search-cluster
      - discovery.seed_hosts=es-master,es-data1
      - cluster.initial_master_nodes=es-master
      - xpack.security.enabled=true
      - ELASTIC_PASSWORD=${ELASTIC_PASSWORD}
      - bootstrap.memory_lock=true
      - ES_JAVA_OPTS=-Xms4g -Xmx4g
    ulimits:
      memlock:
        soft: -1
        hard: -1
      nofile:
        soft: 65536
        hard: 65536
    volumes:
      - es-data2-data:/usr/share/elasticsearch/data
    networks:
      - semantic-search-net
    restart: always

  # Redis для shared cache
  redis:
    image: redis:7-alpine
    container_name: redis-cache
    command: redis-server --appendonly yes --maxmemory 2gb --maxmemory-policy allkeys-lru
    volumes:
      - redis-data:/data
    networks:
      - semantic-search-net
    restart: always

  # API instances
  api1:
    build: ./backend
    container_name: api_instance_1
    expose:
      - "8000"
    ports:
      - "8001:8000"
    env_file:
      - ./backend/.env.production
    environment:
      - INSTANCE_ID=1
      - REDIS_URL=redis://redis:6379
    volumes:
      - ./backend/search_logs:/app/search_logs
    depends_on:
      - elasticsearch-master
      - redis
    networks:
      - semantic-search-net
    restart: always
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3

  api2:
    build: ./backend
    container_name: api_instance_2
    expose:
      - "8000"
    ports:
      - "8002:8000"
    env_file:
      - ./backend/.env.production
    environment:
      - INSTANCE_ID=2
      - REDIS_URL=redis://redis:6379
    volumes:
      - ./backend/search_logs:/app/search_logs
    depends_on:
      - elasticsearch-master
      - redis
    networks:
      - semantic-search-net
    restart: always
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3

networks:
  semantic-search-net:
    driver: bridge

volumes:
  es-master-data:
  es-data1-data:
  es-data2-data:
  redis-data:
```

### 5. Запуск production

```bash
# Встановити змінні середовища
export ELASTIC_PASSWORD="your-strong-password"

# Запустити сервіси
docker-compose -f docker-compose.prod.yml up -d

# Перевірити
docker-compose -f docker-compose.prod.yml ps
```

---

## Конфігурація середовищ

### Development (.env)

```env
# Debug mode
LOG_LEVEL=DEBUG
ENABLE_CORS=true

# Менші timeout'и для швидкої розробки
REQUEST_TIMEOUT=10
GPT_ANALYZE_TIMEOUT_SECONDS=5.0

# Менший кеш
EMBED_CACHE_SIZE=500
```

### Staging (.env.staging)

```env
# Production-like but smaller
LOG_LEVEL=INFO
ENABLE_CORS=true

# Normal timeouts
REQUEST_TIMEOUT=30
GPT_ANALYZE_TIMEOUT_SECONDS=10.0

# Medium cache
EMBED_CACHE_SIZE=1000

# Test API keys
OPENAI_API_KEY=sk-test-...
```

### Production (.env.production)

```env
# Production settings
LOG_LEVEL=WARNING
ENABLE_CORS=false
ALLOWED_ORIGINS=https://your-domain.com,https://www.your-domain.com

# Full timeouts
REQUEST_TIMEOUT=30
GPT_ANALYZE_TIMEOUT_SECONDS=10.0
GPT_RECO_TIMEOUT_SECONDS=15.0

# Full cache
EMBED_CACHE_SIZE=5000
CACHE_TTL_SECONDS=7200

# Production API keys
OPENAI_API_KEY=sk-prod-...
TA_DA_API_TOKEN=prod-token-...

# Redis
REDIS_URL=redis://redis:6379

# Security
ENABLE_RATE_LIMITING=true
MAX_REQUESTS_PER_MINUTE=120
```

---

## Моніторинг

### 1. Health Checks

```bash
#!/bin/bash
# health-check.sh

# API health
API_HEALTH=$(curl -s http://localhost:8080/health | jq -r '.status')
if [ "$API_HEALTH" != "healthy" ]; then
    echo "API unhealthy!"
    exit 1
fi

# Elasticsearch health
ES_HEALTH=$(curl -s http://localhost:9200/_cluster/health | jq -r '.status')
if [ "$ES_HEALTH" != "green" ] && [ "$ES_HEALTH" != "yellow" ]; then
    echo "Elasticsearch unhealthy!"
    exit 1
fi

echo "All services healthy"
exit 0
```

### 2. Prometheus Metrics

Додайте до `main.py`:

```python
from prometheus_client import Counter, Histogram, generate_latest

# Metrics
search_requests = Counter('search_requests_total', 'Total search requests')
search_duration = Histogram('search_duration_seconds', 'Search duration')
cache_hits = Counter('cache_hits_total', 'Cache hits')
cache_misses = Counter('cache_misses_total', 'Cache misses')

@app.get("/metrics")
async def metrics():
    return Response(
        content=generate_latest(),
        media_type="text/plain"
    )
```

### 3. Grafana Dashboard

```yaml
# docker-compose.monitoring.yml
services:
  prometheus:
    image: prom/prometheus:latest
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml
      - prometheus-data:/prometheus
    ports:
      - "9090:9090"
    networks:
      - semantic-search-net

  grafana:
    image: grafana/grafana:latest
    volumes:
      - grafana-data:/var/lib/grafana
    ports:
      - "3000:3000"
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=admin
    networks:
      - semantic-search-net
```

`prometheus.yml`:
```yaml
global:
  scrape_interval: 15s

scrape_configs:
  - job_name: 'api'
    static_configs:
      - targets: ['api1:8000', 'api2:8000']
  
  - job_name: 'elasticsearch'
    static_configs:
      - targets: ['elasticsearch-master:9200']
```

### 4. Логування (ELK Stack)

```yaml
services:
  elasticsearch-logs:
    image: elasticsearch:8.11.1
    environment:
      - discovery.type=single-node
    volumes:
      - logs-data:/usr/share/elasticsearch/data

  logstash:
    image: logstash:8.11.1
    volumes:
      - ./logstash.conf:/usr/share/logstash/pipeline/logstash.conf
    depends_on:
      - elasticsearch-logs

  kibana:
    image: kibana:8.11.1
    ports:
      - "5601:5601"
    environment:
      - ELASTICSEARCH_HOSTS=http://elasticsearch-logs:9200
    depends_on:
      - elasticsearch-logs
```

---

## Резервне копіювання

### 1. Backup скрипт

```bash
#!/bin/bash
# backup.sh

BACKUP_DIR="/backups/semantic-search"
DATE=$(date +%Y%m%d_%H%M%S)

# Створити директорію
mkdir -p "$BACKUP_DIR/$DATE"

# Elasticsearch snapshot
docker exec es-master curl -X PUT "localhost:9200/_snapshot/backup/$DATE?wait_for_completion=true"

# Копіювати дані
docker run --rm -v embeddingsqwen3_elasticsearch-data:/data \
  -v "$BACKUP_DIR/$DATE":/backup \
  alpine tar czf /backup/es-data.tar.gz -C /data .

# Redis backup
docker exec redis-cache redis-cli SAVE
docker cp redis-cache:/data/dump.rdb "$BACKUP_DIR/$DATE/redis-dump.rdb"

# Логи
docker cp api_qwen3:/app/search_logs "$BACKUP_DIR/$DATE/logs"

# Стиснути
cd "$BACKUP_DIR"
tar czf "backup_$DATE.tar.gz" "$DATE"
rm -rf "$DATE"

echo "Backup completed: backup_$DATE.tar.gz"
```

### 2. Cron job

```bash
# Додати до crontab
crontab -e

# Щоденний backup о 2:00
0 2 * * * /opt/semantic-search/backup.sh

# Тижневий backup з ротацією
0 3 * * 0 /opt/semantic-search/backup.sh && find /backups -mtime +30 -delete
```

### 3. Відновлення

```bash
#!/bin/bash
# restore.sh

BACKUP_FILE=$1

if [ -z "$BACKUP_FILE" ]; then
    echo "Usage: ./restore.sh <backup_file.tar.gz>"
    exit 1
fi

# Розпакувати
tar xzf "$BACKUP_FILE"
BACKUP_DIR=$(basename "$BACKUP_FILE" .tar.gz | sed 's/backup_//')

# Зупинити сервіси
docker-compose down

# Відновити Elasticsearch
docker run --rm -v embeddingsqwen3_elasticsearch-data:/data \
  -v "$(pwd)/$BACKUP_DIR":/backup \
  alpine tar xzf /backup/es-data.tar.gz -C /data

# Відновити Redis
docker-compose up -d redis
docker cp "$BACKUP_DIR/redis-dump.rdb" redis-cache:/data/dump.rdb
docker-compose restart redis

# Відновити логи
docker cp "$BACKUP_DIR/logs" api_qwen3:/app/search_logs

# Запустити сервіси
docker-compose up -d

echo "Restore completed from $BACKUP_FILE"
```

---

## Troubleshooting

### Проблема: Elasticsearch не запускається

**Симптоми:**
```
max virtual memory areas vm.max_map_count [65530] is too low
```

**Рішення:**
```bash
sudo sysctl -w vm.max_map_count=262144
echo "vm.max_map_count=262144" | sudo tee -a /etc/sysctl.conf
```

---

### Проблема: Out of Memory

**Симптоми:**
- Container killed
- Java heap space errors

**Рішення:**
```bash
# Збільшити heap для Elasticsearch
ES_JAVA_OPTS=-Xms4g -Xmx4g  # в docker-compose.yml

# Обмежити кеш
EMBED_CACHE_SIZE=1000  # в .env
```

---

### Проблема: Повільний пошук

**Діагностика:**
```bash
# Перевірити статистику
curl http://localhost:8080/stats

# Перевірити кеш
curl http://localhost:8080/cache/stats

# Перевірити Elasticsearch
curl "http://localhost:9200/_cluster/health?pretty"
curl "http://localhost:9200/_nodes/stats?pretty"
```

**Рішення:**
```bash
# Збільшити кеш
EMBED_CACHE_SIZE=5000

# Оптимізувати ES
curl -X PUT "http://localhost:9200/products_qwen3_8b/_settings" \
  -H "Content-Type: application/json" \
  -d '{"index": {"refresh_interval": "30s"}}'

# Додати більше API інстансів
```

---

### Проблема: SSL сертифікат прострочений

```bash
# Оновити сертифікат
sudo certbot renew

# Перезавантажити nginx
sudo systemctl reload nginx

# Перевірити термін дії
sudo certbot certificates
```

---

### Проблема: Диск заповнений

```bash
# Перевірити використання
df -h

# Очистити Docker
docker system prune -a --volumes

# Ротація логів
find /var/log/nginx -name "*.log" -mtime +30 -delete

# Очистити старі backup'и
find /backups -mtime +30 -delete
```

---

## Checklist перед Production Deploy

- [ ] SSL сертифікати налаштовані
- [ ] Firewall правила встановлені (тільки 80, 443, 22)
- [ ] Secrets та API ключі в безпеці (не в git)
- [ ] Backup система налаштована та протестована
- [ ] Моніторинг працює (Prometheus + Grafana)
- [ ] Health checks налаштовані
- [ ] Rate limiting увімкнений
- [ ] CORS правильно налаштований
- [ ] Логи ротуються
- [ ] Elasticsearch cluster здоровий (green/yellow)
- [ ] API instances load balanced
- [ ] Redis працює та персистить дані
- [ ] Перевірено на staging
- [ ] Документація оновлена
- [ ] Команда проінформована

---

**Версія:** 1.0.0  
**Дата оновлення:** 13 жовтня 2025

