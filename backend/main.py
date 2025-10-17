import asyncio
import base64
import hashlib
import json
import logging
import os
import re
import time
from collections import OrderedDict
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, Generator, List, Optional, Set, Tuple
from urllib.parse import urlparse

import httpx
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response, StreamingResponse


def _urlsafe_b64_to_json(b64: str) -> Optional[Any]:
    """Декодує URL-safe base64 в JSON"""
    if not b64:
        return None
    
    try:
        # Додаємо padding якщо потрібен
        padded = b64 + "=" * (-len(b64) % 4)
        decoded_bytes = base64.urlsafe_b64decode(padded.encode())
        decoded_str = decoded_bytes.decode("utf-8")
        return json.loads(decoded_str)
    except (ValueError, json.JSONDecodeError, UnicodeDecodeError) as e:
        logger.debug(f"Failed to decode base64 JSON: {e}")
        return None
    except Exception as e:
        logger.warning(f"Unexpected error in base64 decode: {e}")
        return None


from dotenv import load_dotenv
from elasticsearch import AsyncElasticsearch
from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

# Logging configuration
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("search-backend")
load_dotenv()


def log_performance_metrics(
    operation: str,
    duration_ms: float,
    metadata: Optional[Dict[str, Any]] = None
):
    """Логує метрики продуктивності"""
    log_data = {
        "operation": operation,
        "duration_ms": round(duration_ms, 2),
        "timestamp": time.time()
    }
    
    if metadata:
        log_data.update(metadata)
    
    # Попередження про повільні операції
    if duration_ms > 5000:  # > 5 секунд
        logger.warning(f"⏱️ SLOW: {operation} took {duration_ms:.1f}ms", extra=log_data)
    elif duration_ms > 2000:  # > 2 секунди
        logger.info(f"⏱️ {operation} took {duration_ms:.1f}ms", extra=log_data)


def _safe_chunks(text: str, chunk_size: int = 1) -> Generator[str, None, None]:
    """Розбиває текст на чанки безпечно (по межах символів)"""
    if not text:
        return
    
    for i in range(0, len(text), chunk_size):
        chunk = text[i:i + chunk_size]
        if chunk:  # Перевірка на пустоту
            yield chunk


# Settings
class Settings(BaseSettings):
    # ES / Embeddings
    elastic_url: str = Field(default="http://elasticsearch:9200", env="ELASTIC_URL")
    elastic_user: str = Field(default="elastic", env="ELASTIC_USER")
    elastic_password: str = Field(default="elastic", env="ELASTIC_PASSWORD")
    embedding_api_url: str = Field(default="http://10.2.0.171:9001/api/embeddings", env="EMBEDDING_API_URL")
    ollama_model_name: str = Field(default="dengcao/Qwen3-Embedding-8B:Q8_0", env="OLLAMA_MODEL_NAME")
    index_name: str = Field(default="products_qwen3_8b", env="INDEX_NAME")
    vector_dimension: int = Field(default=4096, env="VECTOR_DIMENSION")
    embed_cache_size: int = Field(default=2000, env="EMBED_CACHE_SIZE")
    request_timeout: int = Field(default=30, env="REQUEST_TIMEOUT")
    max_retries: int = Field(default=3, env="MAX_RETRIES")
    cache_ttl_seconds: int = Field(default=3600, env="CACHE_TTL_SECONDS")
    knn_num_candidates: int = Field(default=500, env="KNN_NUM_CANDIDATES")
    hybrid_alpha: float = Field(default=0.7, env="HYBRID_ALPHA")
    hybrid_fusion: str = Field(default="weighted", env="HYBRID_FUSION")
    bm25_min_score: float = Field(default=2.5, env="BM25_MIN_SCORE")
    vector_field_name: str = Field(default="description_vector", env="VECTOR_FIELD_NAME")

    # GPT
    openai_api_key: str = Field(default="", env="OPENAI_API_KEY")
    gpt_model: str = Field(default="gpt-4o-mini", env="GPT_MODEL")
    enable_gpt_chat: bool = Field(default=True, env="ENABLE_GPT_CHAT")
    gpt_temperature: float = Field(default=0.3, env="GPT_TEMPERATURE")
    gpt_analyze_timeout_seconds: float = Field(default=15.0, env="GPT_ANALYZE_TIMEOUT_SECONDS")

    # Tokens
    gpt_max_tokens_analyze: int = Field(default=2000, env="GPT_MAX_TOKENS_ANALYZE")
    gpt_max_tokens_reco: int = Field(default=2500, env="GPT_MAX_TOKENS_RECO")
    gpt_reco_timeout_seconds: float = Field(default=30.0, env="GPT_RECO_TIMEOUT_SECONDS")

    # Recommendations
    reco_detailed_count: int = Field(default=3, env="RECO_DETAILED_COUNT")
    grounded_recommendations: bool = Field(default=True, env="GROUNDED_RECOMMENDATIONS")

    # History
    search_history_ttl_days: int = Field(default=7, env="SEARCH_HISTORY_TTL_DAYS")
    max_search_history: int = Field(default=20, env="MAX_SEARCH_HISTORY")
    max_chat_display_items: int = Field(default=100, env="MAX_CHAT_DISPLAY_ITEMS")

    # Lazy loading settings
    initial_products_batch: int = Field(default=20, env="INITIAL_PRODUCTS_BATCH")
    load_more_batch_size: int = Field(default=20, env="LOAD_MORE_BATCH_SIZE")
    search_results_ttl_seconds: int = Field(default=3600, env="SEARCH_RESULTS_TTL_SECONDS")
    max_sessions: int = Field(default=300, env="MAX_SEARCH_SESSIONS")

    # Embedding concurrency settings
    embedding_max_concurrent: int = Field(default=2, env="EMBEDDING_MAX_CONCURRENT")
    embedding_single_timeout: float = Field(default=20.0, env="EMBEDDING_SINGLE_TIMEOUT")

    # Chat search relevance settings
    chat_search_score_threshold_ratio: float = Field(default=0.35, env="CHAT_SEARCH_SCORE_THRESHOLD_RATIO")
    chat_search_min_score_absolute: float = Field(default=0.35, env="CHAT_SEARCH_MIN_SCORE_ABSOLUTE")
    chat_search_subquery_weight_decay: float = Field(default=0.85, env="CHAT_SEARCH_SUBQUERY_WEIGHT_DECAY")
    chat_search_max_k_per_subquery: int = Field(default=25, env="CHAT_SEARCH_MAX_K_PER_SUBQUERY")
    
    # SSE settings
    sse_slow_mode: bool = Field(default=False, env="SSE_SLOW_MODE")
    sse_delay_seconds: float = Field(default=0.02, env="SSE_DELAY_SECONDS")

    # TA-DA external API proxy
    ta_da_api_base_url: str = Field(default="https://api.ta-da.net.ua/v1.2/mobile", env="TA_DA_API_BASE_URL")
    ta_da_api_token: str = Field(default="", env="TA_DA_API_TOKEN")
    ta_da_default_shop_id: str = Field(default="8", env="TA_DA_DEFAULT_SHOP_ID")
    ta_da_default_language: str = Field(default="ua", env="TA_DA_DEFAULT_LANGUAGE")

    # Background tasks
    cleanup_interval_seconds: int = Field(default=300, env="CLEANUP_INTERVAL_SECONDS")

    # CORS
    frontend_origins_csv: str = Field(default="*", env="FRONTEND_ORIGINS")

    @field_validator("request_timeout")
    @classmethod
    def _validate_timeout(cls, v: int) -> int:
        if v < 5 or v > 300:
            raise ValueError("Request timeout must be between 5 and 300 seconds")
        return v

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False, extra="ignore")


settings = Settings()


# Compute CORS settings
def _compute_cors():
    origins = [o.strip() for o in settings.frontend_origins_csv.split(",") if o.strip()]
    wildcard = len(origins) == 1 and origins[0] == "*"
    allow_credentials = not wildcard
    return origins, allow_credentials


_CORS_ORIGINS, _CORS_CREDENTIALS = _compute_cors()

# GPT guard at startup
if settings.enable_gpt_chat and not settings.openai_api_key:
    logger.warning("ENABLE_GPT_CHAT=True but OPENAI_API_KEY is empty → disabling GPT")
    settings.enable_gpt_chat = False

# Try to import search logger - optional dependency
try:
    from search_logger import SearchLogger

    search_logger = SearchLogger(logs_dir="search_logs")
    SEARCH_LOGGER_AVAILABLE = True
except ImportError:
    logger.warning("search_logger module not found - logging disabled")
    search_logger = None
    SEARCH_LOGGER_AVAILABLE = False


# Dependency Injection container
@dataclass
class Dependencies:
    es_client: Optional[AsyncElasticsearch] = None
    http_client: Optional[httpx.AsyncClient] = None
    embedding_cache: Optional["TTLCache"] = None
    gpt_service: Optional["GPTService"] = None
    context_manager: Optional["SearchContextManager"] = None


dependencies = Dependencies()


# TTL Cache
class TTLCache:
    def __init__(self, capacity: int = 1000, ttl_seconds: int = 3600):
        self.capacity = capacity
        self.ttl_seconds = ttl_seconds
        self.cache: OrderedDict = OrderedDict()
        self.timestamps: Dict[str, float] = {}
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> Optional[Any]:
        async with self._lock:
            if key not in self.cache:
                return None
            if time.time() - self.timestamps.get(key, 0) > self.ttl_seconds:
                self.cache.pop(key, None)
                self.timestamps.pop(key, None)
                return None
            self.cache.move_to_end(key)
            return self.cache[key]

    async def put(self, key: str, value: Any) -> None:
        async with self._lock:
            now = time.time()
            if key in self.cache:
                self.cache.move_to_end(key)
            self.cache[key] = value
            self.timestamps[key] = now
            if len(self.cache) > self.capacity:
                oldest_key, _ = self.cache.popitem(last=False)
                self.timestamps.pop(oldest_key, None)

    async def cleanup_expired(self) -> int:
        async with self._lock:
            now = time.time()
            expired_keys = [k for k, t in self.timestamps.items() if now - t > self.ttl_seconds]
            for k in expired_keys:
                self.cache.pop(k, None)
                self.timestamps.pop(k, None)
            return len(expired_keys)

    async def clear(self) -> None:
        async with self._lock:
            self.cache.clear()
            self.timestamps.clear()

    def __len__(self) -> int:
        return len(self.cache)


# Pydantic Models
class SearchRequest(BaseModel):
    query: str = Field(min_length=2, max_length=500)
    k: int = Field(default=50, ge=1, le=500)
    min_score: float = Field(default=0.1, ge=0.0, le=1.0)
    mode: str = Field(default="bm25", description="knn | hybrid | bm25")


class SearchResult(BaseModel):
    id: str
    score: float
    title_ua: Optional[str] = None
    title_ru: Optional[str] = None
    description_ua: Optional[str] = None
    description_ru: Optional[str] = None
    sku: Optional[str] = None
    good_code: Optional[str] = None
    uktzed: Optional[str] = None
    measurement_unit_ua: Optional[str] = None
    vat: Optional[str] = None
    discounted: Optional[bool] = None
    height: Optional[float] = None
    width: Optional[float] = None
    length: Optional[float] = None
    weight: Optional[float] = None
    availability: bool = True
    highlight: Optional[Dict[str, List[str]]] = None

    @classmethod
    def from_hit(cls, hit: Dict[str, Any]) -> "SearchResult":
        doc_id, src = hit.get("_id", ""), hit.get("_source", {}) or {}
        return cls(
            id=doc_id,
            score=float(hit.get("_score", 0.0)),
            title_ua=src.get("title_ua"),
            title_ru=src.get("title_ru"),
            description_ua=src.get("description_ua"),
            description_ru=src.get("description_ru"),
            sku=src.get("sku"),
            good_code=src.get("good_code"),
            uktzed=src.get("uktzed"),
            measurement_unit_ua=src.get("measurement_unit_ua"),
            vat=src.get("vat"),
            discounted=src.get("discounted"),
            height=src.get("height"),
            width=src.get("width"),
            length=src.get("length"),
            weight=src.get("weight"),
            availability=src.get("availability", True),
            highlight=hit.get("highlight"),
        )


class SearchResponse(BaseModel):
    results: List[SearchResult]
    total_found: int
    search_time_ms: float
    mode: str


class HealthResponse(BaseModel):
    status: str
    elasticsearch: str
    index: str
    documents_count: int
    cache_size: int
    uptime_seconds: float


class StatsResponse(BaseModel):
    index: str
    documents_count: int
    index_size_bytes: int
    health: str
    embedding_cache_size: int
    embedding_model: str
    uptime_seconds: float


class TadaFindRequest(BaseModel):
    shop_id: str = Field(default_factory=lambda: settings.ta_da_default_shop_id)
    good_code: str
    user_language: Optional[str] = Field(default=None)


class SearchHistoryItem(BaseModel):
    query: str
    keywords: List[str] = Field(default_factory=list)
    timestamp: float
    results_count: int = 0


class ChatSearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=500)
    search_history: List[SearchHistoryItem] = Field(default_factory=list)
    session_id: str
    k: int = Field(default=50, ge=1, le=200)
    dialog_context: Optional[Dict[str, Any]] = None
    selected_category: Optional[str] = Field(default=None)


class LoadMoreRequest(BaseModel):
    session_id: str
    offset: int = Field(ge=0)
    limit: int = Field(default=20, ge=1, le=50)


class QueryAnalysis(BaseModel):
    original_query: str
    expanded_query: str
    keywords: List[str]
    context_used: bool
    intent: str
    atomic_queries: List[str] = Field(default_factory=list)
    es_dsl: Optional[Dict[str, Any]] = Field(default=None)
    filters: Optional[Dict[str, Any]] = Field(default=None)
    semantic_subqueries: List[str] = Field(default_factory=list)
    intent_description: Optional[str] = Field(default=None)


class ProductRecommendation(BaseModel):
    product_id: str
    relevance_score: float
    reason: str
    title: Optional[str] = None
    bucket: Optional[str] = Field(default=None)


class ChatSearchResponse(BaseModel):
    query_analysis: QueryAnalysis
    results: List[SearchResult]
    recommendations: List[ProductRecommendation]
    search_time_ms: float
    context_used: bool
    assistant_message: Optional[str] = None
    dialog_state: Optional[str] = None
    dialog_context: Optional[Dict[str, Any]] = None
    needs_user_input: bool = True
    actions: Optional[List[Dict[str, Any]]] = Field(default=None)
    categories: Optional[List[Dict[str, Any]]] = Field(default=None)
    stage_timings_ms: Optional[Dict[str, float]] = Field(default=None)


# 🎯 ПОКРАЩЕНА СИСТЕМА КАТЕГОРІЙ (на основі реального асортименту TA-DA)
CATEGORY_SCHEMA: Dict[str, Dict[str, Any]] = {
    # ОДЯГ
    "clothing": {
        "label": "Одяг",
        "emoji": "👕",
        "keywords": [
            "одяг",
            "одежд",
            "футболк",
            "сороч",
            "штан",
            "брюк",
            "джинс",
            "куртк",
            "кофт",
            "светр",
            "худі",
            "платт",
            "сукн",
            "спідниц",
        ],
        "parent": None,
    },
    "clothing_men": {"label": "Чоловічий одяг", "emoji": "👔", "keywords": ["чоловіч", "мужск"], "parent": "clothing"},
    "clothing_women": {"label": "Жіночий одяг", "emoji": "👗", "keywords": ["жіноч", "женск"], "parent": "clothing"},
    "clothing_kids": {
        "label": "Дитячий одяг",
        "emoji": "👶",
        "keywords": ["дитяч", "детск", "для хлопчик", "для дівчинк"],
        "parent": "clothing",
    },
    # ВЗУТТЯ
    "footwear": {
        "label": "Взуття",
        "emoji": "👟",
        "keywords": ["взутт", "обув", "капці", "тапочк", "шльопанц", "черевик", "чобіт", "кросівк", "туфл", "босоніжк"],
        "parent": None,
    },
    # АКСЕСУАРИ
    "accessories": {
        "label": "Аксесуари",
        "emoji": "🧦",
        "keywords": [
            "шкарп",
            "носк",
            "колгот",
            "панчох",
            "шапк",
            "шарф",
            "рукавиц",
            "перчатк",
            "ремін",
            "пояс",
            "сумк",
            "рюкзак",
        ],
        "parent": None,
    },
    # ІГРАШКИ
    "toys": {
        "label": "Іграшки",
        "emoji": "🧸",
        "keywords": ["іграш", "игруш", "ляльк", "кукл", "машинк", "конструктор", "пазл", "м'яч", "плюш"],
        "parent": None,
    },
    "toys_educational": {
        "label": "Розвиваючі іграшки",
        "emoji": "🎓",
        "keywords": ["розвива", "навчал", "освітн"],
        "parent": "toys",
    },
    # КУХНЯ
    "kitchen": {
        "label": "Кухонні товари",
        "emoji": "🍳",
        "keywords": ["посуд", "кухн", "кастр", "сковор", "таріл", "чашк", "келих", "ложк", "вилк", "ніж"],
        "parent": None,
    },
    # ПОБУТОВА ХІМІЯ
    "household": {
        "label": "Побутова хімія",
        "emoji": "🧹",
        "keywords": ["миюч", "чист", "прання", "засіб", "порошок", "гель", "швабр", "щітк", "губк", "ганчір"],
        "parent": None,
    },
    # КОСМЕТИКА
    "cosmetics": {
        "label": "Косметика та гігієна",
        "emoji": "💄",
        "keywords": ["косметик", "гігієн", "шампун", "мило", "крем", "зубн паст", "дезодоран"],
        "parent": None,
    },
    # КАНЦЕЛЯРІЯ
    "stationery": {
        "label": "Канцелярія",
        "emoji": "✏️",
        "keywords": ["зошит", "ручк", "олівц", "карандаш", "пенал", "папір", "блокнот", "фарб", "маркер"],
        "parent": None,
    },
    # ДЛЯ ДОМУ
    "home": {
        "label": "Товари для дому",
        "emoji": "🏠",
        "keywords": ["для дому", "домашн", "декор", "текстиль", "рушник", "постільн", "подушк", "ковдр"],
        "parent": None,
    },
    # СПЕЦІАЛЬНА КАТЕГОРІЯ
    "recommended": {
        "label": "⭐ Рекомендовано для вас",
        "emoji": "⭐",
        "keywords": [],
        "parent": None,
        "special": True,
    },
}


def _get_category_hierarchy() -> Dict[str, List[str]]:
    """Повертає ієрархію категорій (батько -> діти)"""
    hierarchy: Dict[str, List[str]] = {}
    for code, data in CATEGORY_SCHEMA.items():
        parent = data.get("parent")
        if parent:
            hierarchy.setdefault(parent, []).append(code)
    return hierarchy


def _find_matching_categories(text: str, top_n: int = 3) -> List[str]:
    """Знаходить найбільш релевантні категорії для тексту"""
    text_lower = text.lower()
    scores: Dict[str, int] = {}

    for code, data in CATEGORY_SCHEMA.items():
        if data.get("special"):  # Пропускаємо спеціальні категорії
            continue
        score = 0
        for keyword in data.get("keywords", []):
            if keyword in text_lower:
                score += 1
        if score > 0:
            scores[code] = score

    # Сортуємо за кількістю збігів
    sorted_codes = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    return [code for code, _ in sorted_codes[:top_n]]


def _assign_category_code(sr: "SearchResult") -> Optional[str]:
    """Автоматично присвоює категорію товару"""
    text = " ".join(filter(None, [sr.title_ua, sr.title_ru, sr.description_ua, sr.description_ru])).lower()

    if not text:
        return None

    matches = _find_matching_categories(text, top_n=1)
    return matches[0] if matches else None


def _aggregate_categories(
    products: List["SearchResult"],
) -> Tuple[Dict[str, List[SearchResult]], List[Tuple[str, int]]]:
    """Групує товари по категоріям"""
    buckets: Dict[str, List[SearchResult]] = {}
    for p in products:
        code = _assign_category_code(p)
        if code:
            buckets.setdefault(code, []).append(p)

    # Якщо товарів багато в дочірніх категоріях - об'єднуємо в батьківську
    hierarchy = _get_category_hierarchy()
    for parent, children in hierarchy.items():
        child_count = sum(len(buckets.get(child, [])) for child in children)
        parent_count = len(buckets.get(parent, []))

        # Якщо в дітях більше товарів - показуємо батьківську категорію
        if child_count > parent_count and child_count >= 3:
            all_products = []
            for child in children:
                all_products.extend(buckets.pop(child, []))
            if parent not in buckets:
                buckets[parent] = all_products
            else:
                buckets[parent].extend(all_products)

    counts = sorted(((c, len(v)) for c, v in buckets.items()), key=lambda x: x[1], reverse=True)
    return buckets, counts


def _categories_payload(id_buckets: Dict[str, List[str]]) -> List[Dict[str, Any]]:
    """Формує payload для категорій з емодзі та іконками"""
    cats: List[Dict[str, Any]] = []

    # Спочатку recommended, якщо є
    if "recommended" in id_buckets:
        cats.append(
            {
                "code": "recommended",
                "label": CATEGORY_SCHEMA["recommended"]["label"],
                "emoji": CATEGORY_SCHEMA["recommended"]["emoji"],
                "count": len(id_buckets["recommended"]),
                "special": True,
            }
        )

    # Потім решта категорій
    for code, ids in id_buckets.items():
        if code == "recommended":
            continue
        schema = CATEGORY_SCHEMA.get(code, {})
        cats.append(
            {"code": code, "label": schema.get("label", code), "emoji": schema.get("emoji", "📦"), "count": len(ids)}
        )

    # Сортуємо за кількістю (окрім recommended)
    recommended_cat = [c for c in cats if c.get("special")]
    other_cats = sorted([c for c in cats if not c.get("special")], key=lambda x: x["count"], reverse=True)

    return recommended_cat + other_cats


def _build_human_reason(query: str, sr: "SearchResult") -> str:
    """Будує людське пояснення чому товар підходить"""
    return "Відповідає вашому запиту"


def _validate_query_basic(query: str) -> Tuple[bool, Optional[str]]:
    """Базова валідація запиту"""
    if not query or not query.strip():
        return False, "Запит не може бути порожнім"

    query = query.strip()

    if len(query) < 2:
        return False, "Запит занадто короткий. Напишіть хоча б 2 символи."

    if len(query) > 500:
        return False, "Запит занадто довгий. Максимум 500 символів."

    if re.match(r"^[\d\s\W]+$", query) and not re.search(r"[a-zA-Zа-яА-ЯіїєґІЇЄҐ]", query):
        return False, "Будь ласка, напишіть текстовий запит."

    if re.search(r"(.)\1{7,}", query):
        return False, "Будь ласка, напишіть коректний запит."

    return True, None


def _extract_json_safely(text: str) -> Dict[str, Any]:
    """Витягує JSON з відповіді GPT"""
    if not text:
        return {}

    # Спробувати code block
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    # Знайти JSON об'єкт
    stack, start_index = [], -1
    best_json = {}
    max_len = 0

    for i, char in enumerate(text):
        if char == "{":
            if not stack:
                start_index = i
            stack.append("{")
        elif char == "}":
            if stack:
                stack.pop()
                if not stack and start_index != -1:
                    substring = text[start_index : i + 1]
                    try:
                        parsed = json.loads(substring)
                        if len(substring) > max_len:
                            best_json, max_len = parsed, len(substring)
                    except json.JSONDecodeError:
                        continue

    if best_json:
        return best_json

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        logger.warning(f"Failed to extract JSON: {text[:200]}...")
        return {}


# Services
class EmbeddingService:
    def __init__(self, http_client: httpx.AsyncClient, cache: TTLCache):
        self.http_client = http_client
        self.cache = cache

    @staticmethod
    def _hash_text(text: str) -> str:
        base = f"{settings.ollama_model_name}|{settings.vector_dimension}|{text}".encode("utf-8")
        return hashlib.md5(base).hexdigest()

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type((httpx.RequestError, httpx.TimeoutException)),
    )
    async def _call_ollama_api(self, text: str) -> Optional[List[float]]:
        payload_candidates = [
            {"model": settings.ollama_model_name, "prompt": text},
            {"model": settings.ollama_model_name, "input": text},
            {"model": settings.ollama_model_name, "input": [text]},
        ]

        last_exc = None
        for payload in payload_candidates:
            try:
                r = await self.http_client.post(
                    settings.embedding_api_url, json=payload, timeout=settings.embedding_single_timeout
                )
                r.raise_for_status()
                data = r.json()

                emb = None
                if isinstance(data, dict):
                    if isinstance(data.get("embedding"), list):
                        emb = data["embedding"]
                    elif isinstance(data.get("embeddings"), list):
                        emb = data["embeddings"]
                    elif isinstance(data.get("data"), list) and data["data"]:
                        maybe = data["data"][0]
                        if isinstance(maybe, dict) and isinstance(maybe.get("embedding"), list):
                            emb = maybe["embedding"]

                if isinstance(emb, list) and emb and isinstance(emb[0], list):
                    emb = emb[0]

                expected = int(settings.vector_dimension)
                if not isinstance(emb, list):
                    continue
                if expected > 0 and len(emb) != expected:
                    logger.error(f"Embedding dimension mismatch: expected {expected}, got {len(emb)}; discarding")
                    continue
                return emb

            except Exception as e:
                last_exc = e
                logger.debug(f"Embedding payload variant failed: {e}")
                continue

        if last_exc:
            logger.error(f"Failed to call embedding API: {last_exc}")
        return None

    async def generate_embedding(self, text: str) -> Optional[List[float]]:
        text = (text or "").strip()
        if not text:
            return None

        key = self._hash_text(text)
        cached = await self.cache.get(key)
        if cached is not None:
            logger.debug("Embedding cache hit")
            return cached

        try:
            t0 = time.time()
            emb = await asyncio.wait_for(self._call_ollama_api(text), timeout=settings.embedding_single_timeout)
            if emb:
                await self.cache.put(key, emb)
                logger.info(f"Embedding generated in {time.time()-t0:.2f}s")
                return emb
        except asyncio.TimeoutError:
            logger.warning(f"⏱️ Embedding timeout after {settings.embedding_single_timeout}s")
        except Exception as e:
            logger.error(f"Embedding generation error: {e}")

        return None

    async def generate_embeddings_parallel(
        self, texts: List[str], max_concurrent: Optional[int] = None
    ) -> List[Optional[List[float]]]:
        if not texts:
            return []

        max_concurrent = max_concurrent or settings.embedding_max_concurrent
        semaphore = asyncio.Semaphore(max_concurrent)

        async def generate_with_semaphore(text: str) -> Optional[List[float]]:
            async with semaphore:
                return await self.generate_embedding(text)

        tasks = [generate_with_semaphore(text) for text in texts]
        embeddings = await asyncio.gather(*tasks, return_exceptions=True)

        result = []
        success_count = 0

        for i, emb in enumerate(embeddings):
            if isinstance(emb, Exception):
                logger.error(f"❌ Embedding error: {emb}")
                result.append(None)
            elif emb is None:
                logger.warning(f"⚠️ Embedding returned None")
                result.append(None)
            else:
                result.append(emb)
                success_count += 1

        logger.info(f"📊 Parallel embedding: {success_count}/{len(texts)} successful")

        return result


class ElasticsearchService:
    def __init__(self, es_client: AsyncElasticsearch):
        self.es_client = es_client

    async def _search_knn(self, params: Dict[str, Any]) -> List[Dict]:
        try:
            # Preferred: query.knn (ES 8.13+)
            body = {"query": {"knn": params["knn"]}}
            res = await self.es_client.search(
                index=params["index"], size=params["size"], body=body, _source=params.get("_source")
            )
            return res.get("hits", {}).get("hits", [])
        except Exception as e1:
            try:
                # Fallback: top-level knn (ES 8.14+/OpenSearch)
                res = await self.es_client.search(**params)
                return res.get("hits", {}).get("hits", [])
            except Exception as e2:
                logger.error(f"kNN search failed (both modes): {e1} | {e2}")
                return []

    async def semantic_search(self, query_vector: List[float], k: int = 10) -> List[Dict]:
        try:
            _source = [
                "title_ua",
                "title_ru",
                "description_ua",
                "description_ru",
                "sku",
                "good_code",
                "uktzed",
                "measurement_unit_ua",
                "vat",
                "discounted",
                "height",
                "width",
                "length",
                "weight",
                "availability",
            ]
            search_params = {
                "index": settings.index_name,
                "size": k,
                "knn": {
                    "field": settings.vector_field_name,
                    "query_vector": query_vector,
                    "k": k,
                    "num_candidates": min(settings.knn_num_candidates, max(100, k * 20)),
                },
                "_source": _source,
            }
            hits = await self._search_knn(search_params)

            if not hits and settings.vector_field_name != "description_vector":
                logger.warning(f"Fallback to description_vector")
                search_params["knn"]["field"] = "description_vector"
                hits = await self._search_knn(search_params)

            return hits
        except Exception as e:
            logger.error(f"Semantic search error: {e}")
            return []

    async def multi_semantic_search(
        self, query_vectors: List[Tuple[str, List[float]]], k_per_query: int = 20
    ) -> Dict[str, List[Dict]]:
        if not query_vectors:
            return {}

        tasks = []
        subquery_names = []

        for subquery, vector in query_vectors:
            if vector is not None:
                tasks.append(self.semantic_search(vector, k_per_query))
                subquery_names.append(subquery)

        if not tasks:
            return {}

        results = await asyncio.gather(*tasks, return_exceptions=True)

        output = {}
        for i, (subquery, result) in enumerate(zip(subquery_names, results)):
            if not isinstance(result, Exception):
                output[subquery] = result
            else:
                logger.warning(f"Search error for '{subquery}': {result}")
                output[subquery] = []

        return output

    async def bm25_search(self, query_text: str, k: int = 10) -> List[Dict]:
        try:
            _source = [
                "title_ua",
                "title_ru",
                "description_ua",
                "description_ru",
                "sku",
                "good_code",
                "uktzed",
                "measurement_unit_ua",
                "vat",
                "discounted",
                "height",
                "width",
                "length",
                "weight",
                "availability",
            ]
            res = await self.es_client.search(
                index=settings.index_name,
                min_score=float(settings.bm25_min_score),
                query={
                    "bool": {
                        "should": [
                            {
                                "multi_match": {
                                    "query": query_text,
                                    "fields": ["title_ua^6", "title_ru^6"],
                                    "type": "phrase",
                                    "boost": 5.0,
                                }
                            },
                            {
                                "multi_match": {
                                    "query": query_text,
                                    "fields": ["title_ua^5", "title_ru^5"],
                                    "type": "best_fields",
                                    "fuzziness": "AUTO",
                                    "boost": 4.0,
                                }
                            },
                            {
                                "multi_match": {
                                    "query": query_text,
                                    "fields": ["description_ua^2", "description_ru^2"],
                                    "type": "best_fields",
                                    "fuzziness": "AUTO",
                                    "boost": 2.0,
                                }
                            },
                            {
                                "multi_match": {
                                    "query": query_text,
                                    "fields": ["sku^3", "good_code^2", "uktzed^1"],
                                    "type": "best_fields",
                                    "boost": 3.0,
                                }
                            },
                        ],
                        "minimum_should_match": 1,
                    }
                },
                size=k,
                _source=_source,
                highlight={
                    "fields": {
                        "title_ua": {},
                        "title_ru": {},
                        "description_ua": {},
                        "description_ru": {},
                    }
                },
            )
            return res.get("hits", {}).get("hits", [])
        except Exception as e:
            logger.error(f"BM25 search error: {e}")
            return []

    async def hybrid_search(
        self, query_vector: Optional[List[float]], query_text_semantic: str, query_text_bm25: str, k: int = 10
    ) -> List[Dict]:
        try:
            if not query_vector:
                raise ValueError("Query vector required")

            candidates = max(k * 2, 50)

            sem_task = asyncio.create_task(self.semantic_search(query_vector, candidates))
            bm_task = asyncio.create_task(self.bm25_search(query_text_bm25, candidates))

            sem, bm = await asyncio.gather(sem_task, bm_task)

            return self._merge(sem, bm, k)

        except Exception as e:
            logger.error(f"Hybrid search error: {e}")
            raise

    def _merge(self, sem: List[Dict], bm: List[Dict], k: int) -> List[Dict]:
        if settings.hybrid_fusion.lower() == "rrf":
            return self._rrf_merge(sem, bm, k)
        return self._weighted_merge(sem, bm, k)

    def _weighted_merge(self, sem: List[Dict], bm: List[Dict], k: int) -> List[Dict]:
        alpha = settings.hybrid_alpha
        beta = 1.0 - alpha

        sem_scores = [h.get("_score", 0.0) for h in sem]
        bm_scores = [h.get("_score", 0.0) for h in bm]
        max_sem = max(sem_scores) if sem_scores else 0.0
        max_bm = max(bm_scores) if bm_scores else 0.0

        if max_sem <= 0:
            alpha = 0.0
            beta = 1.0
        if max_bm <= 0:
            beta = 0.0
            alpha = 1.0

        combined: Dict[str, float] = {}
        pool: Dict[str, Dict] = {}

        for h in sem:
            _id = h["_id"]
            pool[_id] = h
            normalized_score = (h.get("_score", 0.0) / max_sem) if max_sem > 0 else 0.0
            combined[_id] = combined.get(_id, 0.0) + alpha * normalized_score

        for h in bm:
            _id = h["_id"]
            pool[_id] = pool.get(_id) or h
            normalized_score = (h.get("_score", 0.0) / max_bm) if max_bm > 0 else 0.0
            combined[_id] = combined.get(_id, 0.0) + beta * normalized_score

        ordered = sorted(combined.items(), key=lambda x: x[1], reverse=True)

        out = []
        for _id, sc in ordered[:k]:
            hit = pool[_id]
            hit["_score"] = sc
            out.append(hit)

        return out

    def _rrf_merge(self, sem: List[Dict], bm: List[Dict], k: int, c: int = 30) -> List[Dict]:
        scores: Dict[str, float] = {}
        pool: Dict[str, Dict] = {}

        for r, h in enumerate(sem):
            pool[h["_id"]] = h
            scores[h["_id"]] = scores.get(h["_id"], 0.0) + 1.0 / (c + r + 1)

        for r, h in enumerate(bm):
            pool[h["_id"]] = pool.get(h["_id"]) or h
            scores[h["_id"]] = scores.get(h["_id"], 0.0) + 1.0 / (c + r + 1)

        ordered = sorted(scores.items(), key=lambda x: x[1], reverse=True)

        out = []
        for _id, sc in ordered[:k]:
            hit = pool[_id]
            hit["_score"] = sc
            out.append(hit)

        return out

    async def get_index_stats(self) -> Dict[str, Any]:
        try:
            stats_task = self.es_client.indices.stats(index=settings.index_name)
            health_task = self.es_client.cluster.health(index=settings.index_name)
            stats, health = await asyncio.gather(stats_task, health_task)

            idx = stats.get("indices", {}).get(settings.index_name, {})
            total = idx.get("total") or {}
            docs = ((total.get("docs") or {}).get("count")) or 0
            size = ((total.get("store") or {}).get("size_in_bytes")) or 0
            status = health.get("status", "unknown")

            return {"documents_count": int(docs), "index_size_bytes": int(size), "health": status}
        except Exception as e:
            logger.error(f"Index stats error: {e}")
            return {"documents_count": 0, "index_size_bytes": 0, "health": "unknown"}


class GPTService:
    def __init__(self, http_client: httpx.AsyncClient):
        self.http_client = http_client
        self.base_url = "https://api.openai.com/v1"

    @retry(
        stop=stop_after_attempt(settings.max_retries),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        retry=retry_if_exception_type((httpx.RequestError, httpx.TimeoutException)),
    )
    async def _chat(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        r = await self.http_client.post(
            f"{self.base_url}/chat/completions",
            headers={"Authorization": f"Bearer {settings.openai_api_key}", "Content-Type": "application/json"},
            json=payload,
            timeout=settings.request_timeout,
        )
        if r.status_code != 200:
            logger.error(f"OpenAI error: {r.status_code}, {r.text[:200]}")
        r.raise_for_status()
        return r.json()

    async def unified_chat_assistant(
        self, query: str, search_history: List[SearchHistoryItem], dialog_context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """🎯 ПОКРАЩЕНИЙ УНІВЕРСАЛЬНИЙ GPT АСИСТЕНТ для TA-DA"""

        if not settings.enable_gpt_chat or not settings.openai_api_key:
            raise ValueError("GPT is disabled")

        # Формуємо контекст історії
        context = ""
        if search_history:
            recent = search_history[-3:]
            context = "**Історія діалогу:**\n" + "\n".join(
                [f'- "{h.query}" (знайдено {h.results_count} товарів)' for h in recent]
            )

        # Перевірка чи було уточнення
        clarification_note = ""
        if dialog_context and dialog_context.get("clarification_asked"):
            clarification_note = """
⚠️ **КРИТИЧНО ВАЖЛИВО**: Користувач ВЖЕ отримав уточнення раніше!
🚫 НЕ ПИТАЙ БІЛЬШЕ уточнень!
✅ ОБОВ'ЯЗКОВО дай action: "product_search"
✅ Використай відповідь користувача для створення semantic_subqueries
"""

        # 🎯 ПОКРАЩЕНИЙ ПРОМПТ з реальною інформацією про TA-DA
        prompt = f"""Ти - розумний AI консультант інтернет-магазину **TA-DA!** (https://ta-da.ua/)

📍 **ПРО МАГАЗИН TA-DA!:**
TA-DA! - це великий український онлайн-гіпермаркет товарів для дому та родини. У нас 38,000+ товарів:

🏪 **ОСНОВНИЙ АСОРТИМЕНТ:**
• **Одяг** (чоловічий, жіночий, дитячий): футболки, штани, піжами, спортивні костюми
• **Взуття**: домашні капці, шльопанці, чоботи, кросівки
• **Аксесуари**: шкарпетки, колготи, шапки, сумки, рюкзаки
• **Іграшки**: ляльки, конструктори, розвиваючі іграшки, м'ячі
• **Кухонний посуд**: каструлі, сковорідки, тарілки, чашки, столові прибори
• **Побутова хімія**: засоби для прання, миття посуду, прибирання
• **Косметика та гігієна**: шампуні, гелі для душу, зубні пасти, креми
• **Канцелярія**: зошити, ручки, олівці, папір, фарби
• **Товари для дому**: текстиль (рушники, постільна білизна), декор, організатори

💡 **ОСОБЛИВОСТІ:**
- Доступні ціни для українських родин
- Великий вибір товарів для дітей різного віку
- Сезонні товари (літні, зимові, святкові)
- Товари для дому та побуту
- Швидка доставка по Україні

{context}{clarification_note}

**Запит користувача:** "{query}"

---

## 🎯 ТВОЯ РОЛЬ - РОЗУМНИЙ АСИСТЕНТ

Ти маєш **4 типи дій** які можеш виконати:

### 1️⃣ ACTION: "greeting"
Коли користувач:
- Вітається: "привіт", "доброго дня", "hello"
- Прощається: "до побачення", "бувай"
- Дякує: "дякую", "спасибі"

**Твоя відповідь:** Коротке привітання/прощання (1-2 речення)

### 2️⃣ ACTION: "invalid" 
Коли запит ЯВНО не стосується товарів:
- ❌ "як приготувати борщ", "погода сьогодні"
- ❌ "asdfgh123", "....."

⚠️ НЕ використовуй для:
- ✅ "що подарувати на день народження" → product_search (іграшки, посуд)
- ✅ "до школи" → product_search (канцелярія, рюкзаки)

**Твоя відповідь:** Лаконічно поясни що не можеш допомогти

### 3️⃣ ACTION: "clarification"
Коли запит ДУЖЕ ЗАГАЛЬНИЙ і потрібне уточнення:
- ✅ "що у вас є?", "покажи каталог" → покажи ТОП категорії
- ✅ "щось для дому" → уточни конкретніше (кухня? прибирання? декор?)
- ✅ "іграшки" → уточни вік дитини або тип іграшки

❌ НЕ уточнюй якщо:
- "футболки для хлопчика" → достатньо конкретно
- "капці 41 розмір" → достатньо конкретно

**Твоя відповідь:**
- Задай КОРОТКЕ уточнююче питання (1 речення)
- Поверни 4-8 варіантів у полі "categories"
- Використовуй категорії: Одяг, Взуття, Іграшки, Кухня, Побутова хімія, Косметика, Канцелярія, Для дому

### 4️⃣ ACTION: "product_search" (НАЙЧАСТІШЕ!)
Коли користувач шукає конкретні товари:
- ✅ "футболка чорна чоловіча"
- ✅ "капці для дому"
- ✅ "іграшки для дитини 5 років"
- ✅ "що подарувати мамі" (шукай: косметика, посуд, текстиль)

**Твоя відповідь:**
- Напиши коротке повідомлення (1-2 речення)
- **ГОЛОВНЕ:** створи 2-5 "semantic_subqueries" - різні варіанти пошуку

**📝 Приклади semantic_subqueries:**

1. **Конкретний товар:**
   - Запит: "футболка чоловіча чорна"
   - Subqueries: ["футболка чоловіча чорна", "футболка чорна бавовна", "футболка базова чорна"]

2. **З контекстом історії:**
   - Історія: "червона футболка" 
   - Запит: "а синя?"
   - Subqueries: ["футболка синя", "футболка синя чоловіча", "футболка базова синя"]

3. **Ситуаційний запит:**
   - Запит: "подарунок мамі на день народження"
   - Subqueries: ["косметичний набір", "набір рушників", "посуд святковий", "декор для дому"]

4. **Дитячі товари:**
   - Запит: "іграшки для хлопчика 5 років"
   - Subqueries: ["конструктор для дітей 5 років", "машинки іграшкові", "розвиваючі іграшки 5+"]

---

## 📋 ФОРМАТ ВІДПОВІДІ (JSON):

{{
  "action": "greeting|invalid|clarification|product_search",
  "confidence": 0.85,
  "assistant_message": "Текст українською (1-3 речення)",
  "semantic_subqueries": ["підзапит1", "підзапит2"],  // ТІЛЬКИ для product_search
  "categories": ["Категорія1", "Категорія2"],  // ТІЛЬКИ для clarification
  "needs_user_input": true
}}

---

## ⚡ КРИТИЧНІ ПРАВИЛА:

1. **КОНТЕКСТ**: Якщо є історія і запит неповний ("а синя?") - доповни з історії!
2. **УКРАЇНОМОВНІСТЬ**: Всі відповіді ТІЛЬКИ українською мовою
3. **ЛАКОНІЧНІСТЬ**: Коротко і по суті (1-3 речення)
4. **РЕЛЕВАНТНІСТЬ**: semantic_subqueries мають бути дійсно про товари з TA-DA
5. **CLARIFICATION**: Якщо було раніше - більше НЕ питай, відразу product_search!

Проаналізуй запит користувача та дай відповідь у форматі JSON."""

        try:
            data = await asyncio.wait_for(
                self._chat(
                    {
                        "model": settings.gpt_model,
                        "messages": [{"role": "user", "content": prompt}],
                        "temperature": settings.gpt_temperature,
                        "response_format": {"type": "json_object"},
                        "max_tokens": settings.gpt_max_tokens_analyze,
                    }
                ),
                timeout=settings.gpt_analyze_timeout_seconds,
            )

            content = data["choices"][0]["message"]["content"]
            result = _extract_json_safely(content)

            if "action" not in result:
                raise ValueError("Missing 'action' in GPT response")

            # Defaults
            result.setdefault("confidence", 0.8)
            result.setdefault("assistant_message", "Шукаю для вас товари...")
            result.setdefault("semantic_subqueries", [])
            result.setdefault("categories", None)
            result.setdefault("needs_user_input", result["action"] in ["greeting", "invalid", "clarification"])

            logger.info(f"✅ GPT: action={result['action']}, conf={result['confidence']:.2f}")
            return result

        except asyncio.TimeoutError:
            logger.error("⏱️ GPT timeout")
            raise TimeoutError("GPT timeout")
        except Exception as e:
            logger.error(f"❌ GPT error: {e}", exc_info=True)
            raise

    async def analyze_products(
        self, products: List[SearchResult], query: str
    ) -> Tuple[List[ProductRecommendation], Optional[str]]:
        """🎯 ПОКРАЩЕНИЙ АНАЛІЗ ТОВАРІВ з урахуванням специфіки TA-DA"""

        if not products:
            return [], "На жаль, не знайдено відповідних товарів."

        if not settings.enable_gpt_chat or not settings.openai_api_key:
            return self._local_recommendations(products, query)

        items = [
            {
                "index": i + 1,
                "id": p.id,
                "title": p.title_ua or p.title_ru or "",
                "desc": (p.description_ua or p.description_ru or "")[:200],
            }
            for i, p in enumerate(products[:25])
        ]

        # 🎯 ПОКРАЩЕНИЙ ПРОМПТ для аналізу
        prompt = f"""Ти - експертний консультант магазину TA-DA! (https://ta-da.ua/)

📌 **КОНТЕКСТ:**
TA-DA! - український гіпермаркет товарів для дому з 38,000+ позицій.
Основні категорії: одяг, взуття, аксесуари, іграшки, кухонний посуд, побутова хімія, косметика, канцелярія.

**Запит користувача:** "{query}"

**Знайдені товари ({len(items)} кандидатів):**
{json.dumps(items, ensure_ascii=False, indent=1)}

---

## 🎯 ЗАВДАННЯ: Порекомендуй 7-12 НАЙКРАЩИХ товарів

### КРИТЕРІЇ ВИБОРУ:

1. **РЕЛЕВАНТНІСТЬ** (найважливіше!):
   - Товар має ТОЧНО відповідати запиту
   - Якщо згадано колір/розмір/бренд - враховуй це
   - Приклад: запит "футболка чорна" → обирай чорні футболки

2. **РІЗНОМАНІТНІСТЬ**:
   - Якщо запит загальний ("іграшки") - вибирай РІЗНІ типи
   - Якщо конкретний ("футболка чорна 48") - можна схожі варіанти

3. **ЯКІСТЬ ОПИСУ**:
   - Товари з детальним описом краще
   - Повна назва краща за загальну

4. **relevance_score** (оцінка 0-1):
   - **0.85-1.0**: ІДЕАЛЬНО підходить (точна назва, всі характеристики)
   - **0.70-0.84**: ДУЖЕ ДОБРЕ (підходить категорія + деякі характеристики)
   - **0.55-0.69**: ДОБРЕ (підходить категорія)
   - **0.40-0.54**: ПРИЙНЯТНО (схожа категорія)
   
   ⚠️ НЕ рекомендуй товари з score < 0.4

### ФОРМАТ ВІДПОВІДІ (JSON):

{{
  "recommendations": [
    {{
      "product_index": 1,
      "relevance_score": 0.92,
      "reason": "Ідеально підходить: футболка Beki чорна 48 розмір - точно те що ви шукали",
      "bucket": "must_have"
    }},
    {{
      "product_index": 3,
      "relevance_score": 0.78,
      "reason": "Чудова альтернатива: футболка базова чорна, зручна бавовна",
      "bucket": "good_to_have"
    }}
  ],
  "assistant_message": "Я підібрав для вас 8 варіантів чорних футболок. Топ-3 найкращі варіанти враховують ваш розмір та стиль."
}}

### ⚡ ВАЖЛИВО:

- Рекомендуй **МІНІМУМ 7 товарів** (якщо є релевантні)
- **reason** має бути КОНКРЕТНИМ (згадуй назву товару!)
  - ✅ ДОБРЕ: "Футболка Beki чорна - класична базова модель з якісної бавовни"
  - ❌ ПОГАНО: "Підходить за запитом"
- **bucket**: 
  - "must_have" - топ-3 найкращі
  - "good_to_have" - решта хороших варіантів
- **assistant_message**: 2-3 речення, поясни що підібрав і чому ці товари хороші

Проаналізуй товари та дай рекомендації у JSON форматі."""

        try:
            data = await asyncio.wait_for(
                self._chat(
                    {
                        "model": settings.gpt_model,
                        "messages": [{"role": "user", "content": prompt}],
                        "temperature": 0.2,  # Нижча температура для точніших рекомендацій
                        "response_format": {"type": "json_object"},
                        "max_tokens": settings.gpt_max_tokens_reco,
                    }
                ),
                timeout=settings.gpt_reco_timeout_seconds,
            )

            content = data["choices"][0]["message"]["content"]
            obj = _extract_json_safely(content)

            recs: List[ProductRecommendation] = []
            raw_recos = obj.get("recommendations", [])

            for r in raw_recos:
                if not isinstance(r, dict):
                    continue
                idx = int(r.get("product_index", 0)) - 1
                relevance = float(r.get("relevance_score", 0.0))

                # Приймаємо score >= 0.4 (трохи нижче для більшого recall)
                if relevance >= 0.4 and 0 <= idx < len(products):
                    prod = products[idx]
                    recs.append(
                        ProductRecommendation(
                            product_id=prod.id,
                            relevance_score=relevance,
                            reason=r.get("reason", "Рекомендовано"),
                            title=prod.title_ua or prod.title_ru,
                            bucket=r.get("bucket", "good_to_have"),
                        )
                    )

            recs.sort(key=lambda x: x.relevance_score, reverse=True)
            
            # Гарантуємо мінімум 5 рекомендацій якщо є товари
            if len(recs) < 5 and len(products) >= 5:
                logger.warning(f"Only {len(recs)} recs with score>=0.4, adding more")
                
                # Знаходимо max_score для нормалізації
                max_score = max([float(p.score) for p in products], default=1.0) or 1.0
                
                # Додаємо ще товари з нижчим score
                existing_ids = {r.product_id for r in recs}
                for i, prod in enumerate(products):
                    if len(recs) >= 7:
                        break
                    if prod.id not in existing_ids:
                        recs.append(
                            ProductRecommendation(
                                product_id=prod.id,
                                relevance_score=max(0.35, float(prod.score) / max_score),
                                reason="Потенційно відповідає вашому запиту",
                                title=prod.title_ua or prod.title_ru,
                                bucket="also_consider"
                            )
                        )
                        existing_ids.add(prod.id)
                
                recs.sort(key=lambda x: x.relevance_score, reverse=True)
            
            msg = obj.get("assistant_message") or f"Я підібрав для вас {len(recs)} варіантів."

            logger.info(f"🎯 GPT: {len(recs)} products from {len(products)}")

            if not recs:
                return self._local_recommendations(products, query)

            return recs, msg

        except Exception as e:
            logger.warning(f"⚠️ GPT analysis failed: {e}")
            return self._local_recommendations(products, query)

    def _local_recommendations(
        self, products: List[SearchResult], query: str
    ) -> Tuple[List[ProductRecommendation], str]:
        """Локальний fallback для рекомендацій з гарантією мінімуму"""
        q_tokens = [t for t in re.split(r"\W+", (query or "").lower()) if t and len(t) > 2]
        max_es = max((float(p.score) for p in products), default=1.0) or 1.0

        def score_for(p: SearchResult) -> float:
            base = float(p.score) / max_es
            text = " ".join(filter(None, [p.title_ua, p.title_ru])).lower()
            bonus = sum(0.05 for t in q_tokens if t in text)
            return min(1.0, base + min(0.3, bonus))

        ranked = sorted(products, key=lambda x: score_for(x), reverse=True)
        top = ranked[: min(25, len(ranked))]

        # Підвищили поріг з 0.4 до 0.5
        recs = [
            ProductRecommendation(
                product_id=p.id,
                relevance_score=score_for(p),
                reason=_build_human_reason(query, p),
                title=p.title_ua or p.title_ru,
                bucket="must_have" if i < 3 else "good_to_have",
            )
            for i, p in enumerate(top)
            if score_for(p) >= 0.5
        ]
        
        # Гарантуємо хоча б 3 рекомендації якщо є товари
        if not recs and top:
            logger.info(f"No recs with score>=0.5, taking top-3")
            recs = [
                ProductRecommendation(
                    product_id=p.id,
                    relevance_score=score_for(p),
                    reason=_build_human_reason(query, p),
                    title=p.title_ua or p.title_ru,
                    bucket="must_have"
                )
                for p in top[:3]
            ]

        msg = f"Я підібрав {len(recs)} варіантів на основі відповідності вашому запиту."
        return recs, msg

    async def categorize_products(
        self, products: List[SearchResult], query: str, timeout_seconds: float = 15.0
    ) -> Tuple[List[str], Dict[str, List[str]]]:
        """Категоризація товарів (локальна - швидша і надійніша)"""
        # Використовуємо локальну категоризацію - вона швидша і точніша
        return self._local_categorize(products, query)

    def _local_categorize(self, products: List[SearchResult], query: str) -> Tuple[List[str], Dict[str, List[str]]]:
        """🎯 ПОКРАЩЕНА локальна категоризація з динамічною кількістю"""
        logger.info(f"Local categorization: {len(products)} products")

        buckets, counts = _aggregate_categories(products)

        # Фільтруємо слабкі категорії (< 2 товари)
        valid_buckets = {code: prods for code, prods in buckets.items() if len(prods) >= 2}

        if not valid_buckets:
            return ["Всі товари"], {"misc": [p.id for p in products[:50]]}

        # Сортуємо за кількістю
        sorted_codes = sorted(valid_buckets.keys(), key=lambda c: len(valid_buckets[c]), reverse=True)

        # Динамічна кількість категорій: 4-10 в залежності від розподілу
        total_products = len(products)
        if total_products < 20:
            max_categories = 4
        elif total_products < 50:
            max_categories = 6
        elif total_products < 100:
            max_categories = 8
        else:
            max_categories = 10
        
        # Беремо топ категорії, але не менше ніж 70% покриття товарів
        top_codes = []
        covered_products = 0
        target_coverage = total_products * 0.7  # 70% покриття
        
        for code in sorted_codes:
            if len(top_codes) >= max_categories:
                break
            
            top_codes.append(code)
            covered_products += len(valid_buckets[code])
            
            if covered_products >= target_coverage:
                break
        
        # Гарантуємо мінімум 3 категорії
        if len(top_codes) < 3:
            top_codes = sorted_codes[:min(3, len(sorted_codes))]

        # Формуємо labels та id_buckets
        labels = [CATEGORY_SCHEMA.get(code, {}).get("label", code) for code in top_codes]
        id_buckets = {code: [p.id for p in valid_buckets[code]] for code in top_codes}

        logger.info(
            f"Categories: {len(labels)} selected covering {covered_products}/{total_products} products → {labels}"
        )

        return labels, id_buckets


async def execute_chat_search_logic(
    query: str,
    session_id: str,
    k: int,
    selected_category: Optional[str],
    dialog_context: Optional[Dict[str, Any]],
    search_history: List[SearchHistoryItem],
    gpt_service: GPTService,
    embedding_service: EmbeddingService,
    es_service: ElasticsearchService,
    context_manager: "SearchContextManager",
    status_callback: Optional[Callable[[str, str], Awaitable[None]]] = None
) -> Dict[str, Any]:
    """
    🎯 Загальна логіка чат-пошуку для POST та SSE ендпоінтів.
    
    Returns:
        Dict з ключами:
        - action: str
        - state: str (greeting|invalid|clarification|product_search|error)
        - assistant_message: str
        - results: List[SearchResult]
        - recommendations: List[ProductRecommendation]
        - categories_payload: List[Dict]
        - dialog_context: Dict
        - query_analysis: QueryAnalysis
        - search_time_ms: float
        - actions: Optional[List[Dict]]
    """
    t0 = time.time()
    
    # 1. Validation
    is_valid, validation_error = _validate_query_basic(query)
    if not is_valid:
        return {
            "state": "validation_error",
            "action": "invalid",
            "assistant_message": validation_error,
            "results": [],
            "recommendations": [],
            "categories_payload": [],
            "dialog_context": None,
            "query_analysis": QueryAnalysis(
                original_query=query,
                expanded_query=query,
                keywords=[],
                context_used=False,
                intent="invalid"
            ),
            "search_time_ms": (time.time() - t0) * 1000.0,
            "actions": None
        }
    
    # 2. GPT Assistant
    try:
        assistant_response = await gpt_service.unified_chat_assistant(
            query=query,
            search_history=search_history,
            dialog_context=dialog_context
        )
    except Exception as e:
        logger.error(f"GPT assistant failed: {e}", exc_info=True)
        return {
            "state": "error",
            "action": "error",
            "assistant_message": "Вибачте, виникла помилка. Спробуйте ще раз.",
            "results": [],
            "recommendations": [],
            "categories_payload": [],
            "dialog_context": None,
            "query_analysis": QueryAnalysis(
                original_query=query,
                expanded_query=query,
                keywords=[],
                context_used=False,
                intent="error"
            ),
            "search_time_ms": (time.time() - t0) * 1000.0,
            "actions": None
        }
    
    action = assistant_response["action"]
    logger.info(f"🤖 Action: {action} (conf={assistant_response.get('confidence', 0):.2f})")
    
    # 3. Handle greeting
    if action == "greeting":
        return {
            "state": "greeting",
            "action": "greeting",
            "assistant_message": assistant_response["assistant_message"],
            "results": [],
            "recommendations": [],
            "categories_payload": [],
            "dialog_context": None,
            "query_analysis": QueryAnalysis(
                original_query=query,
                expanded_query=query,
                keywords=[],
                context_used=False,
                intent="greeting"
            ),
            "search_time_ms": (time.time() - t0) * 1000.0,
            "actions": None
        }
    
    # 4. Handle invalid
    if action == "invalid":
        return {
            "state": "invalid_query",
            "action": "invalid",
            "assistant_message": assistant_response["assistant_message"],
            "results": [],
            "recommendations": [],
            "categories_payload": [],
            "dialog_context": None,
            "query_analysis": QueryAnalysis(
                original_query=query,
                expanded_query=query,
                keywords=[],
                context_used=False,
                intent="invalid"
            ),
            "search_time_ms": (time.time() - t0) * 1000.0,
            "actions": None
        }
    
    # 5. Handle clarification
    if action == "clarification":
        categories = assistant_response.get("categories", [])
        actions = None
        if categories:
            actions = [
                {
                    "type": "button",
                    "action": "search_category",
                    "value": cat,
                    "label": cat
                }
                for cat in categories[:8]
            ]
        
        return {
            "state": "clarification",
            "action": "clarification",
            "assistant_message": assistant_response["assistant_message"],
            "results": [],
            "recommendations": [],
            "categories_payload": [],
            "dialog_context": {
                "clarification_asked": True,
                "categories_suggested": categories
            },
            "query_analysis": QueryAnalysis(
                original_query=query,
                expanded_query=query,
                keywords=[],
                context_used=False,
                intent="clarification"
            ),
            "search_time_ms": (time.time() - t0) * 1000.0,
            "actions": actions
        }
    
    # 6. Product search - semantic subqueries
    semantic_subqueries = assistant_response.get("semantic_subqueries", [query])
    if not semantic_subqueries:
        semantic_subqueries = [query]
    
    logger.info(f"🔍 Subqueries ({len(semantic_subqueries)}): {semantic_subqueries}")
    
    # 6.5. Notify about database search starting
    if status_callback:
        await status_callback("searching", "Шукаю товари...")
    
    # 7. Generate embeddings
    t_embeddings = time.time()
    embeddings = await embedding_service.generate_embeddings_parallel(
        semantic_subqueries,
        max_concurrent=settings.embedding_max_concurrent
    )
    log_performance_metrics(
        "embeddings_generation",
        (time.time() - t_embeddings) * 1000,
        {"count": len(semantic_subqueries)}
    )
    
    valid_queries = [(sq, emb) for sq, emb in zip(semantic_subqueries, embeddings) if emb]
    
    if not valid_queries:
        logger.error("❌ No valid embeddings generated")
        return {
            "state": "error",
            "action": "error",
            "assistant_message": "Не вдалося обробити запит. Спробуйте інше формулювання.",
            "results": [],
            "recommendations": [],
            "categories_payload": [],
            "dialog_context": None,
            "query_analysis": QueryAnalysis(
                original_query=query,
                expanded_query=query,
                keywords=[],
                context_used=False,
                intent="error"
            ),
            "search_time_ms": (time.time() - t0) * 1000.0,
            "actions": None
        }
    
    logger.info(f"✅ Valid embeddings: {len(valid_queries)}/{len(semantic_subqueries)}")
    
    # 8. Parallel semantic search
    t_search = time.time()
    k_per_subquery = min(
        settings.chat_search_max_k_per_subquery,
        max(10, 50 // len(valid_queries))
    )
    
    search_results = await es_service.multi_semantic_search(valid_queries, k_per_subquery)
    log_performance_metrics(
        "semantic_search",
        (time.time() - t_search) * 1000,
        {"subqueries": len(valid_queries), "k_per_query": k_per_subquery}
    )
    
    # 9. Merge results with weighted scores
    all_hits_dict = {}
    
    for idx, (subquery, hits) in enumerate(search_results.items()):
        weight = 1.0 if idx == 0 else settings.chat_search_subquery_weight_decay ** idx
        logger.debug(f"  Subquery {idx}: '{subquery}' weight={weight:.3f}, hits={len(hits)}")
        
        for hit in hits:
            product_id = hit["_id"]
            base_score = float(hit.get("_score", 0.0))
            weighted_score = base_score * weight
            
            if product_id not in all_hits_dict:
                all_hits_dict[product_id] = hit.copy()
                all_hits_dict[product_id]["_score"] = weighted_score
            else:
                current_score = float(all_hits_dict[product_id].get("_score", 0.0))
                # Зменшили бонус з 0.1 до 0.05 для точнішого ранжування
                all_hits_dict[product_id]["_score"] = max(current_score, weighted_score) + 0.05
    
    all_hits = sorted(
        all_hits_dict.values(),
        key=lambda x: float(x.get("_score", 0.0)),
        reverse=True
    )
    
    logger.info(f"📊 Merged results: {len(all_hits)} unique products")
    
    # 10. Adaptive threshold
    max_score = max([float(h.get("_score", 0.0)) for h in all_hits], default=0.0)
    
    # Покращена логіка порогів
    if len(all_hits) < 5:
        threshold_ratio = 0.25  # Дуже м'який для малих результатів
        adaptive_min = settings.chat_search_min_score_absolute * 0.5
    elif len(all_hits) < 15:
        threshold_ratio = 0.30
        adaptive_min = settings.chat_search_min_score_absolute * 0.7
    elif len(all_hits) < 50:
        threshold_ratio = 0.35
        adaptive_min = settings.chat_search_min_score_absolute * 0.85
    else:
        threshold_ratio = 0.40  # Більш строгий для великих результатів
        adaptive_min = settings.chat_search_min_score_absolute
    
    dynamic_threshold = threshold_ratio * max_score if max_score > 0 else 0.0
    min_score_threshold = max(adaptive_min, dynamic_threshold) if max_score > 0 else 0.0
    
    logger.info(
        f"🎯 Thresholds: hits={len(all_hits)}, max_score={max_score:.3f}, "
        f"dynamic={dynamic_threshold:.3f}, adaptive_min={adaptive_min:.3f}, "
        f"final={min_score_threshold:.3f}"
    )
    
    candidate_results = [
        SearchResult.from_hit(h)
        for h in all_hits
        if float(h.get("_score", 0.0)) >= min_score_threshold
    ]
    
    logger.info(f"✅ After threshold: {len(candidate_results)} candidates")
    
    # 10.5. Обробка порожніх результатів
    assistant_message_prefix = ""  # Ініціалізуємо відразу
    
    if not candidate_results:
        logger.warning(f"No candidates after filtering (max_score={max_score:.3f}, threshold={min_score_threshold:.3f})")
        
        # Спробуємо послабити поріг
        if all_hits and max_score > 0:
            relaxed_threshold = min_score_threshold * 0.5
            candidate_results = [
                SearchResult.from_hit(h)
                for h in all_hits
                if float(h.get("_score", 0.0)) >= relaxed_threshold
            ][:30]  # Обмежуємо до 30
            
            logger.info(f"Relaxed threshold to {relaxed_threshold:.3f}, got {len(candidate_results)} candidates")
            
            if candidate_results:
                assistant_message_prefix = "Не знайшлося точних збігів, але ось схожі товари: "

    if not candidate_results:
        # Реально пусто - повертаємо спеціальну відповідь
        return {
            "state": "no_results",
            "action": "product_search",
            "assistant_message": "На жаль, не знайдено товарів за вашим запитом. Спробуйте інше формулювання або оберіть категорію з меню.",
            "results": [],
            "recommendations": [],
            "categories_payload": [],
            "dialog_context": {"no_results": True, "original_query": query},
            "query_analysis": QueryAnalysis(
                original_query=query,
                expanded_query=query,
                keywords=[w for w in query.split() if len(w) > 2][:5],
                context_used=bool(search_history),
                intent="product_search_no_results",
                semantic_subqueries=semantic_subqueries
            ),
            "search_time_ms": (time.time() - t0) * 1000.0,
            "actions": None
        }
    
    # 11. Categorize products
    t_cat = time.time()
    try:
        labels, id_buckets = await gpt_service.categorize_products(
            candidate_results[:30],
            query
        )
        logger.info(f"📂 Categories: {len(labels)} → {labels}")
        log_performance_metrics("categorization", (time.time() - t_cat) * 1000, {"categories": len(labels)})
    except Exception as e:
        logger.error(f"Categorization failed: {e}")
        labels, id_buckets = [], {}
    
    # 11.5. Notify about recommendations generation
    if status_callback:
        await status_callback("recommending", "Даю рекомендації...")
    
    # 12. Get recommendations
    t_reco = time.time()
    try:
        recommendations, assistant_message = await gpt_service.analyze_products(
            candidate_results[:25],
            query
        )
        logger.info(f"⭐ Recommendations: {len(recommendations)} products")
        log_performance_metrics("recommendations", (time.time() - t_reco) * 1000, {"count": len(recommendations)})
    except Exception as e:
        logger.error(f"Recommendations failed: {e}")
        recommendations = []
        assistant_message = "Ось підібрані товари за вашим запитом."
    
    # Додаємо префікс якщо були послаблені пороги
    if assistant_message_prefix:
        assistant_message = assistant_message_prefix + assistant_message
    
    # 13. Prepare final results
    sorted_candidates = sorted(
        candidate_results,
        key=lambda r: float(r.score),
        reverse=True
    )
    
    candidate_map = {r.id: r for r in sorted_candidates}
    reco_ids = [rec.product_id for rec in recommendations if rec.product_id in candidate_map]
    ordered_from_reco = [candidate_map[rid] for rid in reco_ids]
    remaining = [r for r in sorted_candidates if r.id not in set(reco_ids)]
    
    # 14. Add recommended category
    if reco_ids:
        id_buckets["recommended"] = reco_ids
        logger.info(f"⭐ Added recommended category with {len(reco_ids)} products")
    
    # 15. Apply category filter if selected
    max_display = min(k, settings.max_chat_display_items)
    all_ordered = ordered_from_reco + remaining
    
    dialog_state = "final_results"
    filtered_count = 0
    
    if selected_category:
        if selected_category in id_buckets:
            allowed_ids = set(id_buckets[selected_category])
            all_ordered = [r for r in all_ordered if r.id in allowed_ids]
            filtered_count = len(all_ordered)
            logger.info(f"🔍 Filtered by '{selected_category}': {filtered_count} products")
        else:
            logger.warning(f"⚠️ Category '{selected_category}' not found in buckets")
            assistant_message = (
                assistant_message or "Ось підібрані товари."
            ) + " Обрана категорія недоступна — показую всі результати."
            dialog_state = "category_not_found"
    
    final_results = all_ordered[:max_display]
    
    # 16. Create categories payload
    categories_payload = _categories_payload(id_buckets)
    
    # 17. Create action buttons
    actions = None
    if categories_payload:
        actions = [
            {
                "type": "button",
                "action": "select_category",
                "value": cat["code"],
                "label": cat["label"],
                "emoji": cat.get("emoji", "📦"),
                "count": cat["count"],
                **({"special": "recommended"} if cat.get("special") else {})
            }
            for cat in categories_payload[:10]
        ]
    
    # 18. Store for pagination
    context_manager.store_search_results(
        session_id=session_id,
        all_results=all_ordered,
        total_found=len(candidate_results),
        dialog_context={}
    )
    
    # 19. Create query analysis
    keywords = [w for w in query.split() if len(w) > 2][:5]
    query_analysis = QueryAnalysis(
        original_query=query,
        expanded_query=query,
        keywords=keywords,
        context_used=bool(search_history),
        intent="product_search",
        semantic_subqueries=semantic_subqueries
    )
    
    # 20. Add to history
    context_manager.add_search(
        query=query,
        keywords=keywords,
        results_count=len(final_results)
    )
    
    # 21. Dialog context
    dialog_ctx = {
        "original_query": query,
        "available_categories": [cat["code"] for cat in categories_payload],
        "category_buckets": id_buckets,
        "current_filter": (
            selected_category
            if (selected_category and selected_category in id_buckets)
            else None
        ),
        "filtered_count": filtered_count if selected_category else None
    }
    
    search_time_ms = (time.time() - t0) * 1000.0
    
    logger.info(
        f"✅ Search completed: {len(final_results)} products, "
        f"{len(recommendations)} recommendations, {len(categories_payload)} categories "
        f"in {search_time_ms:.1f}ms"
    )
    
    # 22. Optional logging
    if SEARCH_LOGGER_AVAILABLE and search_logger:
        try:
            top_products = [
                {
                    "id": p.id,
                    "name": p.title_ua or p.title_ru or p.id,
                    "score": round(float(p.score), 4),
                    "recommended": p.id in set(reco_ids)
                }
                for p in final_results[:20]
            ]
            
            search_logger.log_search_query(
                session_id=session_id,
                query=query,
                subqueries=semantic_subqueries,
                total_products_found=len(all_hits),
                products_after_filtering=len(candidate_results),
                max_score=max_score,
                threshold=min_score_threshold,
                adaptive_min=adaptive_min,
                dynamic_threshold=dynamic_threshold,
                top_products=top_products,
                search_time_ms=search_time_ms,
                intent="product_search",
                additional_info={
                    "categories": [cat["label"] for cat in categories_payload],
                    "recommendations_count": len(recommendations),
                    "total_display": len(final_results),
                    "category_filter": selected_category,
                    "filtered_count": filtered_count if selected_category else None
                }
            )
        except Exception as log_error:
            logger.warning(f"Search logging failed (non-critical): {log_error}")
    
    return {
        "state": dialog_state,
        "action": "product_search",
        "assistant_message": assistant_message or "Ось підібрані товари за вашим запитом.",
        "results": final_results,
        "recommendations": recommendations,
        "categories_payload": categories_payload,
        "dialog_context": dialog_ctx,
        "query_analysis": query_analysis,
        "search_time_ms": search_time_ms,
        "actions": actions
    }


class SearchContextManager:
    def __init__(self):
        self.history: List[SearchHistoryItem] = []
        self.search_results: Dict[str, Dict[str, Any]] = {}
        self.max_sessions = settings.max_sessions

    def add_search(self, query: str, keywords: List[str], results_count: int) -> None:
        self.history.append(
            SearchHistoryItem(query=query, keywords=keywords, timestamp=time.time(), results_count=results_count)
        )
        if len(self.history) > settings.max_search_history:
            self.history = self.history[-settings.max_search_history :]

    def get_recent_history(self, limit: int = 5) -> List[SearchHistoryItem]:
        return self.history[-limit:]

    def clear_old_history(self) -> int:
        now = time.time()
        ttl = settings.search_history_ttl_days * 86400
        old_len = len(self.history)
        self.history = [h for h in self.history if now - h.timestamp < ttl]
        return old_len - len(self.history)

    def store_search_results(
        self, session_id: str, all_results: List[SearchResult], total_found: int, dialog_context: Dict[str, Any]
    ) -> None:
        self.search_results[session_id] = {
            "all_results": [r.model_dump() for r in all_results],
            "total_found": total_found,
            "dialog_context": dialog_context,
            "timestamp": time.time(),
        }

        if len(self.search_results) > self.max_sessions:
            # Видаляємо надлишок (найстаріші сесії)
            excess_count = len(self.search_results) - self.max_sessions
            oldest_sessions = sorted(
                self.search_results.items(),
                key=lambda kv: kv[1]["timestamp"]
            )[:excess_count]
            
            for sid, _ in oldest_sessions:
                del self.search_results[sid]
            
            logger.info(f"Removed {excess_count} old sessions (limit: {self.max_sessions})")

    def get_search_results(self, session_id: str, offset: int = 0, limit: int = 20) -> Dict[str, Any]:
        if session_id not in self.search_results:
            return {"products": [], "offset": 0, "has_more": False, "total_found": 0}

        stored = self.search_results[session_id]

        if time.time() - stored["timestamp"] > settings.search_results_ttl_seconds:
            del self.search_results[session_id]
            return {"products": [], "offset": 0, "has_more": False, "total_found": 0}

        all_results = stored["all_results"]
        start_idx = offset
        end_idx = min(offset + limit, len(all_results))

        batch = all_results[start_idx:end_idx]
        has_more = end_idx < len(all_results)

        return {"products": batch, "offset": end_idx, "has_more": has_more, "total_found": stored["total_found"]}

    def clear_search_results(self, session_id: str) -> None:
        self.search_results.pop(session_id, None)

    def cleanup_old_results(self) -> int:
        now = time.time()
        ttl = settings.search_results_ttl_seconds
        expired = [sid for sid, data in self.search_results.items() if now - data["timestamp"] > ttl]
        for sid in expired:
            del self.search_results[sid]
        if expired:
            logger.info(f"Cleaned {len(expired)} expired sessions")
        return len(expired)


# Background tasks
async def periodic_cleanup_task():
    logger.info("Starting periodic cleanup")

    while True:
        try:
            await asyncio.sleep(settings.cleanup_interval_seconds)

            cache = get_embedding_cache()
            expired_cache = await cache.cleanup_expired()

            context_mgr = get_context_manager()
            expired_history = context_mgr.clear_old_history()
            expired_results = context_mgr.cleanup_old_results()

            logger.info(f"Cleanup: cache={expired_cache}, history={expired_history}, results={expired_results}")

        except Exception as e:
            logger.error(f"Cleanup error: {e}", exc_info=True)


# Dependency providers
def get_elasticsearch_client() -> AsyncElasticsearch:
    if dependencies.es_client is None:
        dependencies.es_client = AsyncElasticsearch(
            settings.elastic_url, basic_auth=(settings.elastic_user, settings.elastic_password), request_timeout=30
        )
    return dependencies.es_client


def get_http_client() -> httpx.AsyncClient:
    if dependencies.http_client is None:
        dependencies.http_client = httpx.AsyncClient(timeout=settings.request_timeout)
    return dependencies.http_client


def get_embedding_cache() -> TTLCache:
    if dependencies.embedding_cache is None:
        dependencies.embedding_cache = TTLCache(settings.embed_cache_size, settings.cache_ttl_seconds)
    return dependencies.embedding_cache


def get_embedding_service() -> EmbeddingService:
    return EmbeddingService(get_http_client(), get_embedding_cache())


def get_elasticsearch_service() -> ElasticsearchService:
    return ElasticsearchService(get_elasticsearch_client())


def get_gpt_service() -> GPTService:
    if dependencies.gpt_service is None:
        dependencies.gpt_service = GPTService(get_http_client())
    return dependencies.gpt_service


def get_context_manager() -> SearchContextManager:
    if dependencies.context_manager is None:
        dependencies.context_manager = SearchContextManager()
    return dependencies.context_manager


# FastAPI App
app_start_time = time.time()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 Starting TA-DA! Search System")

    get_elasticsearch_client()
    get_http_client()
    get_embedding_cache()

    cleanup_task = asyncio.create_task(periodic_cleanup_task())

    yield

    logger.info("🛑 Stopping service")

    cleanup_task.cancel()
    try:
        await cleanup_task
    except asyncio.CancelledError:
        pass

    if dependencies.http_client:
        await dependencies.http_client.aclose()
    if dependencies.es_client:
        await dependencies.es_client.close()


app = FastAPI(
    title="TA-DA! Semantic Search",
    description="Smart product search with GPT understanding for TA-DA! hypermarket",
    version="2.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_CORS_ORIGINS,
    allow_credentials=_CORS_CREDENTIALS,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    body = await request.body()
    body_str = body.decode("utf-8", "ignore")
    logger.error(f"Validation error: {exc.errors()} | body={body_str[:500]}")
    return JSONResponse(status_code=422, content={"detail": exc.errors(), "body": body_str})


# ENDPOINTS
@app.get("/health", response_model=HealthResponse)
async def health_check(es_service: ElasticsearchService = Depends(get_elasticsearch_service)):
    try:
        s = await es_service.get_index_stats()
        es_status = "connected" if s.get("health") != "unknown" else "disconnected"
        app_status = "healthy" if es_status == "connected" else "degraded"
    except Exception:
        s = {"documents_count": 0}
        es_status = "disconnected"
        app_status = "degraded"

    cache = get_embedding_cache()
    return HealthResponse(
        status=app_status,
        elasticsearch=es_status,
        index=settings.index_name,
        documents_count=s.get("documents_count", 0),
        cache_size=len(cache),
        uptime_seconds=time.time() - app_start_time,
    )


@app.get("/live")
async def liveness_check():
    """Liveness probe - always returns 200 if app is running"""
    return {"status": "alive", "uptime_seconds": time.time() - app_start_time}


@app.get("/ready")
async def readiness_check(es_service: ElasticsearchService = Depends(get_elasticsearch_service)):
    """Readiness probe - checks dependencies"""
    try:
        # Check ES
        s = await es_service.get_index_stats()
        es_ready = s.get("health") not in ["unknown", "red"]

        # Check GPT (if enabled)
        gpt_ready = True
        if settings.enable_gpt_chat:
            gpt_ready = bool(settings.openai_api_key)

        if es_ready and gpt_ready:
            return JSONResponse(
                status_code=200,
                content={
                    "status": "ready",
                    "elasticsearch": "ok",
                    "gpt": "ok" if settings.enable_gpt_chat else "disabled",
                    "uptime_seconds": time.time() - app_start_time,
                },
            )
        else:
            return JSONResponse(
                status_code=503,
                content={
                    "status": "not_ready",
                    "elasticsearch": "ok" if es_ready else "unavailable",
                    "gpt": "ok" if gpt_ready else ("unavailable" if settings.enable_gpt_chat else "disabled"),
                    "uptime_seconds": time.time() - app_start_time,
                },
            )
    except Exception as e:
        logger.error(f"Readiness check failed: {e}")
        return JSONResponse(
            status_code=503,
            content={"status": "not_ready", "error": str(e), "uptime_seconds": time.time() - app_start_time},
        )


@app.get("/config")
async def get_frontend_config():
    return {"feature_chat_sse": True}


@app.post("/search", response_model=SearchResponse)
async def search_products(
    request: SearchRequest,
    embedding_service: EmbeddingService = Depends(get_embedding_service),
    es_service: ElasticsearchService = Depends(get_elasticsearch_service),
):
    t0 = time.time()

    try:
        if not request.query.strip():
            raise HTTPException(400, "Query empty")

        mode = request.mode.lower().replace("semantic", "knn")
        q = request.query.strip()
        hits: List[Dict] = []
        candidates = max(request.k * 2, 100)

        if mode == "knn":
            v = await embedding_service.generate_embedding(q)
            if not v:
                raise HTTPException(503, "Embedding unavailable")
            hits = await es_service.semantic_search(v, candidates)

        elif mode == "bm25":
            hits = await es_service.bm25_search(q, candidates)

        elif mode == "hybrid":
            v = await embedding_service.generate_embedding(q)
            if not v:
                raise HTTPException(503, "Embedding unavailable")
            hits = await es_service.hybrid_search(v, q, q, candidates)

        else:
            raise HTTPException(400, f"Unknown mode: {request.mode}")

        filtered = hits
        results = [SearchResult.from_hit(h) for h in filtered[: request.k]]

        ms = (time.time() - t0) * 1000.0
        logger.info(f"Search '{q}' ({mode}): {len(results)} in {ms:.1f}ms")

        return SearchResponse(results=results, total_found=len(results), search_time_ms=ms, mode=request.mode)

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Search failed: {e}")
        ms = (time.time() - t0) * 1000.0
        return SearchResponse(results=[], total_found=0, search_time_ms=ms, mode=request.mode)


@app.post("/chat/search", response_model=ChatSearchResponse)
async def chat_search(
    request: ChatSearchRequest,
    gpt_service: GPTService = Depends(get_gpt_service),
    embedding_service: EmbeddingService = Depends(get_embedding_service),
    es_service: ElasticsearchService = Depends(get_elasticsearch_service),
    context_manager: SearchContextManager = Depends(get_context_manager),
):
    """🎯 Чат-пошук товарів з GPT асистентом"""
    try:
        query = request.query.strip()
        if not query:
            raise HTTPException(400, "Query empty")

        logger.info(f"💬 Chat POST: '{query}'")
        
        result = await execute_chat_search_logic(
            query=query,
            session_id=request.session_id,
            k=request.k,
            selected_category=request.selected_category,
            dialog_context=request.dialog_context,
            search_history=request.search_history,
            gpt_service=gpt_service,
            embedding_service=embedding_service,
            es_service=es_service,
            context_manager=context_manager
        )

        return ChatSearchResponse(
            query_analysis=result["query_analysis"],
            results=result["results"],
            recommendations=result["recommendations"],
            search_time_ms=result["search_time_ms"],
            context_used=result["query_analysis"].context_used,
            assistant_message=result["assistant_message"],
            dialog_state=result["state"],
            dialog_context=result["dialog_context"],
            needs_user_input=result["action"] in ["greeting", "invalid", "clarification"],
            actions=result["actions"],
            categories=result["categories_payload"]
        )
        
    except Exception as e:
        logger.exception(f"Chat search failed: {e}")
        return ChatSearchResponse(
            query_analysis=QueryAnalysis(
                original_query=request.query,
                expanded_query=request.query,
                keywords=[],
                context_used=False,
                intent="error"
            ),
            results=[],
            recommendations=[],
            search_time_ms=0,
            context_used=False,
            assistant_message="Вибачте, виникла помилка. Спробуйте ще раз.",
            dialog_state="error",
            dialog_context=None,
            needs_user_input=False
        )


@app.get("/chat/search/sse")
async def chat_search_sse(
    request: Request,
    query: str,
    session_id: str,
    k: int = 50,
    selected_category: Optional[str] = None,
    dialog_context_b64: Optional[str] = None,
    search_history_b64: Optional[str] = None,
    gpt_service: GPTService = Depends(get_gpt_service),
    embedding_service: EmbeddingService = Depends(get_embedding_service),
    es_service: ElasticsearchService = Depends(get_elasticsearch_service),
    context_manager: SearchContextManager = Depends(get_context_manager),
):
    """SSE stream для real-time чат-пошуку з використанням загальної логіки"""

    async def event_generator():
        def sse_event(event: str, data: Dict[str, Any]) -> str:
            return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

        try:
            query_stripped = query.strip()
            logger.info(f"💬 Chat SSE: '{query_stripped}'")

            # Decode context
            dialog_context: Optional[Dict[str, Any]] = None
            if dialog_context_b64:
                decoded = _urlsafe_b64_to_json(dialog_context_b64)
                if isinstance(decoded, dict):
                    dialog_context = decoded

            # Decode history
            search_history: List[SearchHistoryItem] = []
            if search_history_b64:
                decoded = _urlsafe_b64_to_json(search_history_b64)
                if isinstance(decoded, list):
                    for item in decoded:
                        if isinstance(item, dict) and "query" in item:
                            try:
                                search_history.append(
                                    SearchHistoryItem(
                                        query=item.get("query", ""),
                                        keywords=item.get("keywords", []),
                                        timestamp=item.get("timestamp", time.time()),
                                        results_count=item.get("results_count", 0),
                                    )
                                )
                            except Exception as e:
                                logger.debug(f"Failed to parse search history item: {e}")

            # Execute search logic with status callback
            yield sse_event("status", {"message": "Думаю...", "type": "thinking"})
            
            # Create a queue for status updates
            status_queue = asyncio.Queue()
            
            # Define status callback to send status updates during execution
            async def send_status(status_type: str, message: str):
                await status_queue.put({"type": status_type, "message": message})
            
            # Run search logic in background task
            search_task = asyncio.create_task(execute_chat_search_logic(
                query=query_stripped,
                session_id=session_id,
                k=k,
                selected_category=selected_category,
                dialog_context=dialog_context,
                search_history=search_history,
                gpt_service=gpt_service,
                embedding_service=embedding_service,
                es_service=es_service,
                context_manager=context_manager,
                status_callback=send_status
            ))
            
            # Yield status updates as they come
            while not search_task.done():
                try:
                    status_update = await asyncio.wait_for(status_queue.get(), timeout=0.1)
                    yield sse_event("status", status_update)
                except asyncio.TimeoutError:
                    continue
            
            # Get remaining status updates
            while not status_queue.empty():
                status_update = await status_queue.get()
                yield sse_event("status", status_update)
            
            # Get result
            result = await search_task
            
            action = result["action"]
            assistant_message = result["assistant_message"]
            
            # Stream assistant message
            if assistant_message:
                yield sse_event("assistant_start", {"length": len(assistant_message)})
                for chunk in _safe_chunks(assistant_message):
                    yield sse_event("assistant_delta", {"text": chunk})
                    if settings.sse_slow_mode:
                        await asyncio.sleep(settings.sse_delay_seconds)
                yield sse_event("assistant_end", {})

            # Stream additional events for product_search
            if action == "product_search":
                if result["state"] == "no_results":
                    # Спеціальна подія для порожніх результатів
                    yield sse_event("no_results", {
                        "message": assistant_message,
                        "suggestions": [
                            "Спробуйте інше формулювання", 
                            "Оберіть категорію з меню",
                            "Уточніть характеристики товару"
                        ]
                    })
                elif result["results"]:
                    yield sse_event("candidates", {"count": len(result["results"])})
                    
                    if result["categories_payload"]:
                        yield sse_event("categories", {"items": result["categories_payload"]})
                    
                    if result["recommendations"]:
                        yield sse_event("recommendations", {
                            "count": len(result["recommendations"]),
                            "assistant_message": assistant_message
                        })
            
            # Final payload
            payload = ChatSearchResponse(
                query_analysis=result["query_analysis"],
                results=result["results"],
                recommendations=result["recommendations"],
                search_time_ms=result["search_time_ms"],
                context_used=result["query_analysis"].context_used,
                assistant_message=assistant_message,
                dialog_state=result["state"],
                dialog_context=result["dialog_context"],
                needs_user_input=action in ["greeting", "invalid", "clarification"],
                actions=result["actions"],
                categories=result["categories_payload"]
            ).model_dump()

            yield sse_event("final", payload)

        except Exception as e:
            logger.error(f"SSE error: {e}", exc_info=True)
            yield sse_event("error", {"message": f"Вибачте, виникла помилка: {str(e)}"})

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.post("/chat/search/load-more")
async def load_more_products(
    request: LoadMoreRequest, context_manager: SearchContextManager = Depends(get_context_manager)
):
    try:
        result = context_manager.get_search_results(
            session_id=request.session_id, offset=request.offset, limit=request.limit
        )

        if not result["products"]:
            return {"products": [], "offset": request.offset, "has_more": False, "total_found": 0}

        return result

    except Exception as e:
        logger.exception(f"Load more failed: {e}")
        return {"products": [], "offset": request.offset, "has_more": False, "total_found": 0, "error": str(e)}


@app.get("/stats", response_model=StatsResponse)
async def get_stats(es_service: ElasticsearchService = Depends(get_elasticsearch_service)):
    s = await es_service.get_index_stats()
    cache = get_embedding_cache()
    return StatsResponse(
        index=settings.index_name,
        documents_count=s.get("documents_count", 0),
        index_size_bytes=s.get("index_size_bytes", 0),
        health=s.get("health", "unknown"),
        embedding_cache_size=len(cache),
        embedding_model=settings.ollama_model_name,
        uptime_seconds=time.time() - app_start_time,
    )


@app.post("/api/ta-da/find.gcode")
async def ta_da_find_gcode(req: TadaFindRequest, http_client: httpx.AsyncClient = Depends(get_http_client)):
    headers = {
        "User-Language": req.user_language or settings.ta_da_default_language,
        "Content-Type": "application/json",
    }
    if settings.ta_da_api_token:
        headers["Authorization"] = f"Bearer {settings.ta_da_api_token}"
        logger.debug(f"Using TA-DA token: ...{settings.ta_da_api_token[-10:]}")
    else:
        logger.warning("TA-DA API token is not configured!")

    payload = {"shop_id": req.shop_id or settings.ta_da_default_shop_id, "good_code": req.good_code}

    url = f"{settings.ta_da_api_base_url.rstrip('/')}/find.gcode"

    try:
        r = await http_client.post(url, headers=headers, json=payload, timeout=20.0)
        if r.status_code != 200:
            try:
                error_body = r.text
                logger.warning(f"TA-DA API error: status={r.status_code}, body={error_body[:300]}")
            except:
                logger.warning(f"TA-DA API error: status={r.status_code}")
            return {"error": "API unavailable", "price": 0, "rating": 0}

        data = r.json()
        if not isinstance(data, dict):
            logger.warning(f"TA-DA API bad response format: {type(data)}")
            return {"error": "bad_response", "price": 0, "rating": 0}

        return data

    except Exception as e:
        logger.warning(f"TA-DA proxy error: {e}")
        return {"error": "API unavailable", "price": 0, "rating": 0}


@app.post("/cache/clear")
async def clear_cache(cache: TTLCache = Depends(get_embedding_cache)):
    try:
        await cache.clear()
        return {"message": "Cache cleared"}
    except Exception as e:
        return JSONResponse(status_code=200, content={"message": "Error", "error": str(e)})


@app.get("/cache/stats")
async def get_cache_stats(cache: TTLCache = Depends(get_embedding_cache)):
    try:
        expired = await cache.cleanup_expired()
        return {
            "size": len(cache),
            "capacity": cache.capacity,
            "ttl_seconds": cache.ttl_seconds,
            "expired_cleaned": expired,
        }
    except Exception as e:
        return {"size": len(cache), "error": str(e)}


@app.get("/api/image-proxy")
async def image_proxy(url: str, http_client: httpx.AsyncClient = Depends(get_http_client)):
    try:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            raise HTTPException(400, "Invalid URL")
        host = parsed.hostname or ""
        if not (host.endswith("ta-da.net.ua") or host.endswith("ta-da.ua")):
            raise HTTPException(400, "Invalid host")

        headers = {"Range": "bytes=0-10485759"}  # ~10MB
        response = await http_client.get(url, timeout=10.0, follow_redirects=False, headers=headers)
        if 300 <= response.status_code < 400:
            raise HTTPException(400, "Redirects not allowed")

        content_length = response.headers.get("content-length")
        if content_length and int(content_length) > 10_485_760:
            raise HTTPException(413, "Image too large")

        response.raise_for_status()

        return Response(
            content=response.content,
            media_type=response.headers.get("content-type", "image/png"),
            headers={"Cache-Control": "public, max-age=86400", "Access-Control-Allow-Origin": "*"},
        )
    except Exception as e:
        logger.warning(f"Image proxy error: {e}")
        raise HTTPException(404, "Image not found")


# Search logs API
if SEARCH_LOGGER_AVAILABLE and search_logger:

    @app.get("/search-logs/sessions")
    async def get_search_log_sessions():
        try:
            sessions = search_logger.get_all_sessions()
            return {"total": len(sessions), "sessions": sessions}
        except Exception as e:
            raise HTTPException(500, str(e))

    @app.get("/search-logs/session/{session_id}")
    async def get_session_logs(session_id: str):
        try:
            logs = search_logger.get_session_logs(session_id)
            if not logs:
                raise HTTPException(404, f"Session not found")
            return {"session_id": session_id, "total_queries": len(logs), "queries": logs}
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(500, str(e))

    @app.get("/search-logs/report/{session_id}")
    async def get_session_report(session_id: str):
        try:
            report = search_logger.generate_session_report(session_id)
            if "error" in report:
                raise HTTPException(404, report["error"])
            return report
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(500, str(e))

    @app.get("/search-logs/stats")
    async def get_search_logs_stats():
        try:
            sessions = search_logger.get_all_sessions()

            total_queries = 0
            all_scores = []
            all_search_times = []

            for session_id in sessions:
                logs = search_logger.get_session_logs(session_id)
                total_queries += len(logs)

                for log in logs:
                    all_search_times.append(log["search_stats"]["search_time_ms"])
                    all_scores.extend([p["score"] for p in log["top_products"]])

            return {
                "total_sessions": len(sessions),
                "total_queries": total_queries,
                "average_queries_per_session": round(total_queries / len(sessions), 2) if sessions else 0,
                "search_time": {
                    "min": round(min(all_search_times), 2) if all_search_times else 0,
                    "max": round(max(all_search_times), 2) if all_search_times else 0,
                    "avg": round(sum(all_search_times) / len(all_search_times), 2) if all_search_times else 0,
                },
                "scores": {
                    "min": round(min(all_scores), 4) if all_scores else 0,
                    "max": round(max(all_scores), 4) if all_scores else 0,
                    "avg": round(sum(all_scores) / len(all_scores), 4) if all_scores else 0,
                },
            }
        except Exception as e:
            raise HTTPException(500, str(e))


# Run
if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True, log_level="info")
