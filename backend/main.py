import os
import asyncio
import time
import logging
import hashlib
import httpx
import json
import re
from collections import OrderedDict
from typing import List, Optional, Dict, Tuple, Any, Set
from contextlib import asynccontextmanager
from dataclasses import dataclass

from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, StreamingResponse, Response
import base64
from urllib.parse import urlparse
def _urlsafe_b64_to_json(b64: str) -> Optional[Any]:
    try:
        padded = b64 + "=" * (-len(b64) % 4)
        return json.loads(base64.urlsafe_b64decode(padded.encode()).decode())
    except Exception:
        return None

from elasticsearch import AsyncElasticsearch
from dotenv import load_dotenv
from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from tenacity import (
    retry, stop_after_attempt, wait_exponential,
    retry_if_exception_type
)

# Logging configuration
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("search-backend")
load_dotenv()

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
    bm25_min_score: float = Field(default=5.0, env="BM25_MIN_SCORE")
    vector_field_name: str = Field(default="description_vector", env="VECTOR_FIELD_NAME")

    # GPT
    openai_api_key: str = Field(default="", env="OPENAI_API_KEY")
    gpt_model: str = Field(default="gpt-4o-mini", env="GPT_MODEL")
    enable_gpt_chat: bool = Field(default=True, env="ENABLE_GPT_CHAT")
    gpt_temperature: float = Field(default=0.3, env="GPT_TEMPERATURE")
    gpt_analyze_timeout_seconds: float = Field(default=15.0, env="GPT_ANALYZE_TIMEOUT_SECONDS")

    # Tokens
    gpt_max_tokens_analyze: int = Field(default=1500, env="GPT_MAX_TOKENS_ANALYZE")
    gpt_max_tokens_reco: int = Field(default=2000, env="GPT_MAX_TOKENS_RECO")
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
    
    # Embedding concurrency settings
    embedding_max_concurrent: int = Field(default=2, env="EMBEDDING_MAX_CONCURRENT")
    embedding_single_timeout: float = Field(default=20.0, env="EMBEDDING_SINGLE_TIMEOUT")
    
    # Chat search relevance settings
    chat_search_score_threshold_ratio: float = Field(default=0.4, env="CHAT_SEARCH_SCORE_THRESHOLD_RATIO")
    chat_search_min_score_absolute: float = Field(default=0.3, env="CHAT_SEARCH_MIN_SCORE_ABSOLUTE")
    chat_search_subquery_weight_decay: float = Field(default=0.85, env="CHAT_SEARCH_SUBQUERY_WEIGHT_DECAY")
    chat_search_max_k_per_subquery: int = Field(default=20, env="CHAT_SEARCH_MAX_K_PER_SUBQUERY")

    # TA-DA external API proxy
    ta_da_api_base_url: str = Field(default="https://api.ta-da.net.ua/v1.2/mobile", env="TA_DA_API_BASE_URL")
    ta_da_api_token: str = Field(default="", env="TA_DA_API_TOKEN")
    ta_da_default_shop_id: str = Field(default="8", env="TA_DA_DEFAULT_SHOP_ID")
    ta_da_default_language: str = Field(default="ua", env="TA_DA_DEFAULT_LANGUAGE")
    
    # Background tasks
    cleanup_interval_seconds: int = Field(default=300, env="CLEANUP_INTERVAL_SECONDS")

    @field_validator("request_timeout")
    @classmethod
    def _validate_timeout(cls, v: int) -> int:
        if v < 5 or v > 300:
            raise ValueError("Request timeout must be between 5 and 300 seconds")
        return v

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
        extra="ignore"
    )

settings = Settings()

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

# TTL Cache with improvements
class TTLCache:
    def __init__(self, capacity: int = 1000, ttl_seconds: int = 3600):
        self.capacity = capacity
        self.ttl_seconds = ttl_seconds
        self.cache: OrderedDict = OrderedDict()
        self.timestamps: Dict[str, float] = {}
        self._lock = asyncio.Lock()
        self._cleanup_task: Optional[asyncio.Task] = None

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
            highlight=hit.get("highlight")
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
    user_language: Optional[str] = Field(default=None, description="ua|ru|...")

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
    stage_timings_ms: Optional[Dict[str, float]] = Field(default=None)

# Category schema (сокращенная версия)
CATEGORY_SCHEMA: Dict[str, Dict[str, Any]] = {
    "clothes_tshirts": {"label": "Футболки", "keywords": ["футболк", "t-shirt", "tee", "майк"]},
    "clothes_pants": {"label": "Штани", "keywords": ["штан", "брюк", "джинс"]},
    "toys_general": {"label": "Іграшки", "keywords": ["іграш", "игруш", "ляльк", "кукл"]},
    "house_kitchen": {"label": "Кухня", "keywords": ["посуд", "кастр", "сковор", "таріл"]},
    "stationery": {"label": "Канцелярія", "keywords": ["зошит", "ручк", "олівц"]},
    "recommended": {"label": "⭐ Рекомендовано для вас", "keywords": []},
    "misc": {"label": "Релевантні товари", "keywords": []},
}

# ДОП: предкомпилированные паттерны по словоформам
def _w(words: List[str]) -> re.Pattern:
    # границы слова + украинско-русские основы; регистр игнорируем
    # пример: "футболк" матчится на футболка/футболки/футболку и т.п.
    return re.compile(r"(?:\b|[^A-Za-zА-Яа-яІіЇїЄєҐґ0-9])(?:" + "|".join(map(re.escape, words)) + r")[A-Za-zА-Яа-яІіЇїЄєҐґ0-9]*", re.IGNORECASE)

CATEGORY_PATTERNS: Dict[str, re.Pattern] = {
    "clothes_tshirts": _w(["футболк", "t-shirt", "tee", "майк"]),
    "clothes_pants":   _w(["штан", "брюк", "джинс", "джинси"]),
    "toys_general":    _w(["іграш", "игруш", "ляльк", "кукл"]),
    "house_kitchen":   _w(["посуд", "кастр", "сковор", "таріл", "кухн"]),
    "stationery":      _w(["зошит", "ручк", "олівц", "канцел"]),
}

def _categories_payload(id_buckets: Dict[str, List[str]]) -> List[Dict[str, Any]]:
    cats: List[Dict[str, Any]] = []
    for code, ids in id_buckets.items():
        label = CATEGORY_SCHEMA.get(code, {}).get("label", "Релевантні товари" if code == "misc" else code)
        cats.append({"code": code, "label": label, "count": len(ids)})
    cats.sort(key=lambda x: x["count"], reverse=True)
    return cats

def _assign_category_code(sr: "SearchResult") -> Optional[str]:
    """Жёстче и точнее: регэкспы по словоформам + счёт хитов."""
    text = " ".join(filter(None, [sr.title_ua, sr.title_ru, sr.description_ua, sr.description_ru])) or ""
    if not text:
        return None
    hits: List[Tuple[str, int]] = []
    for code, pat in CATEGORY_PATTERNS.items():
        m = pat.findall(text)
        if m:
            hits.append((code, len(m)))
    if not hits:
        return None
    hits.sort(key=lambda x: x[1], reverse=True)
    winner, best = hits[0]
    # отсечь шум: единичные хиты игнорируем (кроме футболок)
    if best < 2 and winner != "clothes_tshirts":
        return None
    return winner

def _allowed_category_codes_for_query(query: str) -> Optional[Set[str]]:
    q = (query or "").lower()
    if any(t in q for t in ["футболк", "майк", "t-shirt", "tee"]):
        return {c for c in CATEGORY_SCHEMA if c.startswith("clothes_")}
    if any(t in q for t in ["штан", "брюк", "джинс", "джинси"]):
        return {"clothes_pants"}
    if any(t in q for t in ["іграш", "игруш", "ляльк", "кукл"]):
        return {c for c in CATEGORY_SCHEMA if c.startswith("toys_")}
    if any(t in q for t in ["посуд", "кастр", "сковор", "таріл", "кухн"]):
        return {c for c in CATEGORY_SCHEMA if c.startswith("house_")}
    if any(t in q for t in ["зошит", "ручк", "олівц", "канцел"]):
        return {"stationery"}
    return None

def _aggregate_categories(products: List["SearchResult"]) -> Tuple[Dict[str, List[SearchResult]], List[Tuple[str, int]]]:
    """Aggregates products by categories."""
    buckets: Dict[str, List[SearchResult]] = {}
    for p in products:
        code = _assign_category_code(p)
        if code:
            buckets.setdefault(code, []).append(p)
    counts = sorted(((c, len(v)) for c, v in buckets.items()), key=lambda x: x[1], reverse=True)
    return buckets, counts

def _build_human_reason(query: str, sr: "SearchResult") -> str:
    """Builds human-readable reason."""
    return "Відповідає вашому запиту"

def _validate_query_basic(query: str) -> Tuple[bool, Optional[str]]:
    """Basic query validation."""
    if not query or not query.strip():
        return False, "Запит не може бути порожнім"
    
    query = query.strip()
    
    if len(query) < 2:
        return False, "Запит занадто короткий. Напишіть хоча б 2 символи."
    
    if len(query) > 500:
        return False, "Запит занадто довгий. Максимум 500 символів."
    
    if re.match(r'^[\d\s\W]+$', query) and not re.search(r'[a-zA-Zа-яА-ЯіїєґІЇЄҐ]', query):
        return False, "Будь ласка, напишіть текстовий запит."
    
    if re.search(r'(.)\1{7,}', query):
        return False, "Будь ласка, напишіть коректний запит."
    
    return True, None

def _extract_json_safely(text: str) -> Dict[str, Any]:
    """Extracts JSON from model response."""
    if not text:
        return {}
    
    # Try code block first
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    # Try finding JSON object
    stack, start_index = [], -1
    best_json = {}
    max_len = 0
    
    for i, char in enumerate(text):
        if char == '{':
            if not stack:
                start_index = i
            stack.append('{')
        elif char == '}':
            if stack:
                stack.pop()
                if not stack and start_index != -1:
                    substring = text[start_index: i + 1]
                    try:
                        parsed = json.loads(substring)
                        if len(substring) > max_len:
                            best_json, max_len = parsed, len(substring)
                    except json.JSONDecodeError:
                        continue
    
    if best_json:
        return best_json

    # Last resort - try parsing entire text
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        logger.warning(f"Failed to extract JSON from text: {text[:200]}...")
        return {}

# Services
class EmbeddingService:
    def __init__(self, http_client: httpx.AsyncClient, cache: TTLCache):
        self.http_client = http_client
        self.cache = cache

    @staticmethod
    def _hash_text(text: str) -> str:
        return hashlib.md5(text.encode("utf-8")).hexdigest()

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type((httpx.RequestError, httpx.TimeoutException))
    )
    async def _call_ollama_api(self, text: str) -> Optional[List[float]]:
        """Calls embedding API with retry logic."""
        payload_candidates = [
            {"model": settings.ollama_model_name, "prompt": text},
            {"model": settings.ollama_model_name, "input": text},
            {"model": settings.ollama_model_name, "input": [text]},
        ]
        
        last_exc = None
        for payload in payload_candidates:
            try:
                r = await self.http_client.post(
                    settings.embedding_api_url,
                    json=payload,
                    timeout=settings.embedding_single_timeout
                )
                r.raise_for_status()
                data = r.json()
                
                # Extract embedding from various response formats
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
                # Normalize 2D -> 1D if needed
                if isinstance(emb, list) and emb and isinstance(emb[0], list):
                    emb = emb[0]
                
                if isinstance(emb, list) and (settings.vector_dimension <= 0 or len(emb) == settings.vector_dimension):
                    return emb
                    
                if emb is not None and isinstance(emb, list):
                    logger.warning(f"Embedding dimension mismatch: expected {settings.vector_dimension}, got {len(emb)}")
                    return emb
                    
            except Exception as e:
                last_exc = e
                logger.debug(f"Embedding payload variant failed: {e}")
                continue
        
        if last_exc:
            logger.error(f"Failed to call embedding API: {last_exc}")
        return None

    async def generate_embedding(self, text: str) -> Optional[List[float]]:
        """Generates embedding for text with caching."""
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
            emb = await asyncio.wait_for(
                self._call_ollama_api(text), 
                timeout=settings.embedding_single_timeout
            )
            if emb:
                await self.cache.put(key, emb)
                logger.info(f"Embedding generated in {time.time()-t0:.2f}s")
                return emb
        except asyncio.TimeoutError:
            logger.warning(f"⏱️ Embedding timeout after {settings.embedding_single_timeout}s for: '{text[:50]}...'")
        except Exception as e:
            logger.error(f"Embedding generation error: {e}")
        
        return None

    async def generate_embeddings_parallel(
        self, 
        texts: List[str], 
        max_concurrent: Optional[int] = None
    ) -> List[Optional[List[float]]]:
        """Generates embeddings in parallel with concurrency limit."""
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
                logger.error(f"❌ Embedding error for '{texts[i][:60]}...': {emb}")
                result.append(None)
            elif emb is None:
                logger.warning(f"⚠️ Embedding returned None for '{texts[i][:60]}...'")
                result.append(None)
            else:
                result.append(emb)
                success_count += 1
        
        logger.info(f"📊 Parallel embedding (max {max_concurrent} concurrent): {success_count}/{len(texts)} successful")
        
        return result

class ElasticsearchService:
    def __init__(self, es_client: AsyncElasticsearch):
        self.es_client = es_client

    async def semantic_search(self, query_vector: List[float], k: int = 10) -> List[Dict]:
        """Semantic search using vector field."""
        try:
            search_params = {
                "index": settings.index_name,
                "size": k,
                "knn": {
                    "field": settings.vector_field_name,
                    "query_vector": query_vector,
                    "k": k,
                    "num_candidates": min(settings.knn_num_candidates, max(100, k * 20))
                }
            }
            res = await self.es_client.search(**search_params)
            hits = res.get("hits", {}).get("hits", [])
            
            # Fallback to description_vector if configured field doesn't work
            if not hits and settings.vector_field_name != "description_vector":
                logger.warning(f"No results from {settings.vector_field_name}, trying description_vector")
                search_params["knn"]["field"] = "description_vector"
                res = await self.es_client.search(**search_params)
                hits = res.get("hits", {}).get("hits", [])
            
            return hits
        except Exception as e:
            logger.error(f"Semantic search error: {e}")
            return []

    async def multi_semantic_search(
        self,
        query_vectors: List[Tuple[str, List[float]]],
        k_per_query: int = 20
    ) -> Dict[str, List[Dict]]:
        """Parallel semantic search for multiple vectors."""
        if not query_vectors:
            return {}
        
        tasks = []
        subquery_names = []
        
        for subquery, vector in query_vectors:
            if vector is not None:
                tasks.append(self.semantic_search(vector, k_per_query))
                subquery_names.append(subquery)
        
        if not tasks:
            logger.warning("multi_semantic_search: no valid vectors")
            return {}
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        output = {}
        for i, (subquery, result) in enumerate(zip(subquery_names, results)):
            if not isinstance(result, Exception):
                output[subquery] = result
                logger.debug(f"'{subquery}': found {len(result)} products")
            else:
                logger.warning(f"Search error for '{subquery}': {result}")
                output[subquery] = []
        
        logger.info(f"Parallel search: {len(output)}/{len(query_vectors)} successful")
        
        return output

    async def bm25_search(self, query_text: str, k: int = 10) -> List[Dict]:
        """BM25 full-text search."""
        try:
            res = await self.es_client.search(
                index=settings.index_name,
                min_score=float(settings.bm25_min_score),
                query={
                    "bool": {
                        "should": [
                            {"multi_match": {"query": query_text, "fields": ["title_ua^6", "title_ru^6"], "type": "phrase", "boost": 5.0}},
                            {"multi_match": {"query": query_text, "fields": ["title_ua^5", "title_ru^5"], "type": "best_fields", "fuzziness": "AUTO", "boost": 4.0}},
                            {"multi_match": {"query": query_text, "fields": ["description_ua^2", "description_ru^2"], "type": "best_fields", "fuzziness": "AUTO", "boost": 2.0}},
                            {"multi_match": {"query": query_text, "fields": ["sku^3", "good_code^2", "uktzed^1"], "type": "best_fields", "boost": 3.0}}
                        ],
                        "minimum_should_match": 1
                    }
                },
                size=k
            )
            return res.get("hits", {}).get("hits", [])
        except Exception as e:
            logger.error(f"BM25 search error: {e}")
            return []

    async def hybrid_search(
        self, 
        query_vector: Optional[List[float]], 
        query_text_semantic: str,
        query_text_bm25: str,
        k: int = 10
    ) -> List[Dict]:
        """Hybrid search combining semantic and BM25."""
        try:
            if not query_vector:
                raise ValueError("Query vector is required for hybrid search")
            
            candidates = max(k * 2, 50)
            
            sem_task = asyncio.create_task(self.semantic_search(query_vector, candidates))
            bm_task = asyncio.create_task(self.bm25_search(query_text_bm25, candidates))
            
            sem, bm = await asyncio.gather(sem_task, bm_task)
            
            logger.info(f"Hybrid search: semantic={len(sem)}, BM25={len(bm)} candidates")
            
            return self._merge(sem, bm, k)
            
        except Exception as e:
            logger.error(f"Hybrid search error: {e}")
            raise

    def _merge(self, sem: List[Dict], bm: List[Dict], k: int) -> List[Dict]:
        """Merges search results."""
        if settings.hybrid_fusion.lower() == "rrf":
            return self._rrf_merge(sem, bm, k)
        return self._weighted_merge(sem, bm, k)

    def _weighted_merge(self, sem: List[Dict], bm: List[Dict], k: int) -> List[Dict]:
        """Weighted merge of results."""
        alpha = settings.hybrid_alpha
        beta = 1.0 - alpha
        
        sem_scores = [h.get("_score", 0.0) for h in sem]
        bm_scores = [h.get("_score", 0.0) for h in bm]
        max_sem = max(sem_scores) if sem_scores else 1.0
        max_bm = max(bm_scores) if bm_scores else 1.0
        
        combined: Dict[str, float] = {}
        pool: Dict[str, Dict] = {}
        
        for h in sem:
            _id = h["_id"]
            pool[_id] = h
            normalized_score = h.get("_score", 0.0) / max_sem
            combined[_id] = combined.get(_id, 0.0) + alpha * normalized_score
        
        for h in bm:
            _id = h["_id"]
            pool[_id] = pool.get(_id) or h
            normalized_score = h.get("_score", 0.0) / max_bm
            combined[_id] = combined.get(_id, 0.0) + beta * normalized_score
        
        ordered = sorted(combined.items(), key=lambda x: x[1], reverse=True)
        
        out = []
        for _id, sc in ordered[:k]:
            hit = pool[_id]
            hit["_score"] = sc
            out.append(hit)
        
        return out

    def _rrf_merge(self, sem: List[Dict], bm: List[Dict], k: int, c: int = 30) -> List[Dict]:
        """RRF merge of results."""
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
        """Gets index statistics."""
        try:
            stats_task = self.es_client.indices.stats(index=settings.index_name)
            health_task = self.es_client.cluster.health(index=settings.index_name)
            stats, health = await asyncio.gather(stats_task, health_task)
            
            idx = stats.get("indices", {}).get(settings.index_name, {})
            total = (idx.get("total") or {})
            docs = ((total.get("docs") or {}).get("count")) or 0
            size = ((total.get("store") or {}).get("size_in_bytes")) or 0
            status = health.get("status", "unknown")
            
            return {
                "documents_count": int(docs),
                "index_size_bytes": int(size),
                "health": status
            }
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
        retry=retry_if_exception_type((httpx.RequestError, httpx.TimeoutException))
    )
    async def _chat(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Calls OpenAI Chat API."""
        r = await self.http_client.post(
            f"{self.base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {settings.openai_api_key}",
                "Content-Type": "application/json"
            },
            json=payload,
            timeout=settings.request_timeout
        )
        if r.status_code != 200:
            logger.error(f"HTTP error from OpenAI: {r.status_code}, text: {r.text[:200]}")
        r.raise_for_status()
        return r.json()

    async def unified_chat_assistant(
        self, 
        query: str, 
        search_history: List[SearchHistoryItem],
        dialog_context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Universal GPT assistant for all query types."""
        if not settings.enable_gpt_chat:
            raise ValueError("GPT chat assistant is disabled")
        
        if not settings.openai_api_key:
            raise ValueError("OpenAI API key is not configured")
        
        # Build context from history
        context = ""
        if search_history:
            recent_history = search_history[-3:]
            context_lines = [f"- Користувач шукав: '{h.query}'" for h in recent_history]
            context = "**Історія попередніх пошуків:**\n" + "\n".join(context_lines)
        
        # Check if clarification was already asked
        already_clarified = dialog_context and dialog_context.get("clarification_asked", False)
        clarification_note = ""
        if already_clarified:
            clarification_note = """
⚠️ **КРИТИЧНО**: Користувач ВЖЕ ОТРИМАВ уточнення!
❌ НЕ ПИТАЙ БІЛЬШЕ!
✅ ОБОВ'ЯЗКОВО action: "product_search"
"""
        
        # Shortened prompt (production version should be optimized further)
        prompt = f"""Ти - AI асистент магазину TA-DA! з 38,000+ товарів.

{context}{clarification_note}

**Запит:** "{query}"

**4 ТИПИ ДІЙ:**
1. "greeting" - привітання/прощання
2. "invalid" - нерелевантний запит (рідко!)
3. "clarification" - потрібне уточнення (БЕЗ товарів!)
4. "product_search" - пошук товарів

**JSON відповідь:**
{{
  "action": "greeting|invalid|clarification|product_search",
  "confidence": 0.8,
  "assistant_message": "Текст українською",
  "semantic_subqueries": ["підзапит1", "підзапит2"],  // ТІЛЬКИ для product_search
  "categories": ["Категорія1", "Категорія2"],  // ТІЛЬКИ для clarification
  "needs_user_input": true
}}

Проаналізуй запит та дай відповідь у форматі JSON."""

        try:
            data = await asyncio.wait_for(
                self._chat({
                    "model": settings.gpt_model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": settings.gpt_temperature,
                    "response_format": {"type": "json_object"},
                    "max_tokens": settings.gpt_max_tokens_analyze
                }),
                timeout=settings.gpt_analyze_timeout_seconds
            )
            
            content = data["choices"][0]["message"]["content"]
            result = _extract_json_safely(content)
            
            if "action" not in result:
                raise ValueError("GPT response missing 'action' field")
            
            # Set defaults
            result.setdefault("confidence", 0.8)
            result.setdefault("assistant_message", "Шукаю для вас товари...")
            result.setdefault("semantic_subqueries", [])
            result.setdefault("categories", None)
            result.setdefault("needs_user_input", result["action"] in ["greeting", "invalid", "clarification"])
            
            logger.info(f"✅ Unified assistant: action={result['action']}, confidence={result['confidence']:.2f}")
            return result
            
        except asyncio.TimeoutError:
            logger.error("⏱️ Unified assistant timeout")
            raise TimeoutError("GPT request timeout")
        except Exception as e:
            logger.error(f"❌ Unified assistant error: {e}", exc_info=True)
            raise
    
    async def analyze_products(
        self, 
        products: List[SearchResult], 
        query: str
    ) -> Tuple[List[ProductRecommendation], Optional[str]]:
        """Analyzes products and returns recommendations."""
        if not products:
            return [], "На жаль, не знайдено відповідних товарів."

        if not settings.enable_gpt_chat or not settings.openai_api_key:
            return self._local_recommendations(products, query)

        items = [{
            "index": i + 1,
            "id": p.id,
            "title": p.title_ua or p.title_ru or "",
            "desc": (p.description_ua or p.description_ru or "")[:150]
        } for i, p in enumerate(products[:20])]  # Limit to 20

        # Shortened prompt
        prompt = f"""Експерт магазину TA-DA!

**Запит:** "{query}"

**Товари ({len(items)}):**
{json.dumps(items, ensure_ascii=False)}

**Завдання:** Рекомендуй 5-10 найкращих товарів.

**JSON:**
{{
  "recommendations": [
    {{
      "product_index": 1,
      "relevance_score": 0.95,
      "reason": "Конкретне пояснення",
      "bucket": "must_have"
    }}
  ],
  "assistant_message": "Повідомлення українською (2-3 речення)"
}}

Мінімум 5 товарів з score >= 0.5"""

        try:
            data = await asyncio.wait_for(
                self._chat({
                    "model": settings.gpt_model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": settings.gpt_temperature,
                    "response_format": {"type": "json_object"},
                    "max_tokens": settings.gpt_max_tokens_reco
                }), 
                timeout=settings.gpt_reco_timeout_seconds
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
                
                # Accept >= 0.5 (slightly higher threshold)
                if relevance >= 0.5 and 0 <= idx < len(products):
                    prod = products[idx]
                    recs.append(ProductRecommendation(
                        product_id=prod.id,
                        relevance_score=relevance,
                        reason=r.get("reason", "Рекомендовано"),
                        title=prod.title_ua or prod.title_ru,
                        bucket=r.get("bucket")
                    ))

            recs.sort(key=lambda x: x.relevance_score, reverse=True)
            msg = obj.get("assistant_message") or "Я підібрав для вас відповідні варіанти."
            
            logger.info(f"🎯 GPT selected {len(recs)} products from {len(products)}")
            
            if not recs:
                return self._local_recommendations(products, query)
            
            return recs, msg
            
        except Exception as e:
            logger.warning(f"⚠️ analyze_products failed: {e}. Using local fallback.")
            return self._local_recommendations(products, query)

    def _local_recommendations(
        self, 
        products: List[SearchResult], 
        query: str
    ) -> Tuple[List[ProductRecommendation], str]:
        """Local fallback for recommendations."""
        q_tokens = [t for t in re.split(r"\W+", (query or "").lower()) if t]
        max_es = max((float(p.score) for p in products), default=1.0) or 1.0

        def score_for(p: SearchResult) -> float:
            base = float(p.score) / max_es
            text = " ".join(filter(None, [p.title_ua, p.title_ru])).lower()
            bonus = sum(0.05 for t in q_tokens if t and t in text)
            return min(1.0, base + min(0.3, bonus))

        ranked = sorted(products, key=lambda x: score_for(x), reverse=True)
        top = ranked[:min(20, len(ranked))]
        
        recs = [
            ProductRecommendation(
                product_id=p.id,
                relevance_score=score_for(p),
                reason=_build_human_reason(query, p),
                title=p.title_ua or p.title_ru,
                bucket="must_have" if i < 3 else "good_to_have"
            )
            for i, p in enumerate(top)
            if score_for(p) >= 0.5
        ]
        
        msg = "Я підібрав варіанти на основі відповідності вашому запиту."
        return recs, msg

    async def categorize_products(
        self, 
        products: List[SearchResult], 
        query: str, 
        timeout_seconds: float = 15.0
    ) -> Tuple[List[str], Dict[str, List[str]]]:
        """Categorizes products."""
        if not products:
            return [], {}

        if not settings.enable_gpt_chat or not settings.openai_api_key:
            return self._local_categorize(products, query)

        items = [{
            "id": p.id,
            "title": p.title_ua or p.title_ru or "",
            "desc": (p.description_ua or p.description_ru or "")[:100]
        } for p in products[:30]]

        category_list = [f"- {cat['label']}" for cat in CATEGORY_SCHEMA.values()]

        # Shortened prompt
        prompt = f"""Розподіли товари по категоріях магазину TA-DA!

**Категорії:**
{chr(10).join(category_list)}

**Запит:** "{query}"

**Товари:**
{json.dumps(items, ensure_ascii=False)}

**JSON:**
{{
  "categories": ["Категорія1", "Категорія2"],
  "buckets": {{
    "Категорія1": ["id1", "id2"],
    "Категорія2": ["id3", "id4"]
  }}
}}

2-6 категорій, мінімум 2 товари в кожній."""

        try:
            data = await asyncio.wait_for(
                self._chat({
                    "model": settings.gpt_model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.1,
                    "response_format": {"type": "json_object"},
                    "max_tokens": 2000
                }), 
                timeout=timeout_seconds
            )

            content = data["choices"][0]["message"]["content"]
            obj = _extract_json_safely(content) or {}
            
            raw_labels = obj.get("categories") or []
            raw_buckets = obj.get("buckets") or {}

            labels = [str(c).strip() for c in raw_labels if isinstance(c, str)]
            valid_ids = {p.id for p in products}

            # НОРМАЛИЗАЦИЯ: если GPT прислал лейблы — маппим в codes
            label2code = {v["label"]: k for k, v in CATEGORY_SCHEMA.items()}
            code_buckets: Dict[str, List[str]] = {}
            if isinstance(raw_buckets, dict):
                for label, ids in raw_buckets.items():
                    if not isinstance(label, str):
                        continue
                    key = label.strip()
                    if not key:
                        continue
                    code = key if key in CATEGORY_SCHEMA else label2code.get(key)
                    if not code:
                        continue
                    arr = [pid for pid in (ids or []) if isinstance(pid, str) and pid in valid_ids]
                    if len(arr) >= 2:
                        code_buckets[code] = arr

            final_codes = list(code_buckets.keys())
            if not final_codes and not code_buckets:
                return self._local_categorize(products, query)

            labels = [CATEGORY_SCHEMA.get(c, {}).get("label", c) for c in final_codes]
            return labels[:20], code_buckets
            
        except Exception as e:
            logger.warning(f"⚠️ categorize_products failed: {e}. Using local fallback.")
            return self._local_categorize(products, query)

    def _local_categorize(
        self, 
        products: List[SearchResult], 
        query: str
    ) -> Tuple[List[str], Dict[str, List[str]]]:
        """Локальна категоризація з поверненням code-бакетів."""
        logger.info(f"Local categorization for {len(products)} products")

        allowed = _allowed_category_codes_for_query(query)

        # соберём корзины по code
        buckets_by_code: Dict[str, List[SearchResult]] = {}
        for p in products:
            code = _assign_category_code(p)
            if not code:
                continue
            if allowed and code not in allowed:
                continue
            buckets_by_code.setdefault(code, []).append(p)

        # отсекаем слабые корзины (<2)
        pruned = {code: arr for code, arr in buckets_by_code.items() if len(arr) >= 2}

        if not pruned:
            return ["Релевантні товари"], {"misc": [p.id for p in products[:30]]}

        counts = sorted(((c, len(v)) for c, v in pruned.items()), key=lambda x: x[1], reverse=True)
        if counts and len(counts) > 1 and counts[0][1] >= 2 * counts[1][1]:
            dominant = counts[0][0]
            return [CATEGORY_SCHEMA.get(dominant, {}).get("label", dominant)], {dominant: [p.id for p in pruned[dominant]]}

        top_codes = [c for c, _ in counts[:6]]
        return (
            [CATEGORY_SCHEMA.get(c, {}).get("label", c) for c in top_codes],
            {c: [p.id for p in pruned[c]] for c in top_codes}
        )

class SearchContextManager:
    """Manages search history and cached results."""
    
    def __init__(self):
        self.history: List[SearchHistoryItem] = []
        self.search_results: Dict[str, Dict[str, Any]] = {}
        self._cleanup_task: Optional[asyncio.Task] = None

    def add_search(self, query: str, keywords: List[str], results_count: int) -> None:
        """Adds search to history."""
        self.history.append(SearchHistoryItem(
            query=query, 
            keywords=keywords, 
            timestamp=time.time(), 
            results_count=results_count
        ))
        if len(self.history) > settings.max_search_history:
            self.history = self.history[-settings.max_search_history:]

    def get_recent_history(self, limit: int = 5) -> List[SearchHistoryItem]:
        """Gets recent search history."""
        return self.history[-limit:]

    def clear_old_history(self) -> int:
        """Clears old history based on TTL."""
        now = time.time()
        ttl = settings.search_history_ttl_days * 86400
        old_len = len(self.history)
        self.history = [h for h in self.history if now - h.timestamp < ttl]
        return old_len - len(self.history)
    
    def store_search_results(
        self, 
        session_id: str, 
        all_results: List[SearchResult], 
        total_found: int, 
        dialog_context: Dict[str, Any]
    ) -> None:
        """Stores search results for pagination."""
        self.search_results[session_id] = {
            "all_results": [r.model_dump() for r in all_results],
            "total_found": total_found,
            "dialog_context": dialog_context,
            "timestamp": time.time()
        }
    
    def get_search_results(
        self, 
        session_id: str, 
        offset: int = 0, 
        limit: int = 20
    ) -> Dict[str, Any]:
        """Gets paginated search results."""
        if session_id not in self.search_results:
            return {"products": [], "offset": 0, "has_more": False, "total_found": 0}
        
        stored = self.search_results[session_id]
        
        # Check expiration
        if time.time() - stored["timestamp"] > settings.search_results_ttl_seconds:
            del self.search_results[session_id]
            return {"products": [], "offset": 0, "has_more": False, "total_found": 0}
        
        all_results = stored["all_results"]
        start_idx = offset
        end_idx = min(offset + limit, len(all_results))
        
        batch = all_results[start_idx:end_idx]
        has_more = end_idx < len(all_results)
        
        return {
            "products": batch,
            "offset": end_idx,
            "has_more": has_more,
            "total_found": stored["total_found"]
        }
    
    def clear_search_results(self, session_id: str) -> None:
        """Clears search results for session."""
        self.search_results.pop(session_id, None)
    
    def cleanup_old_results(self) -> int:
        """Cleans up expired search results."""
        now = time.time()
        ttl = settings.search_results_ttl_seconds
        expired = [sid for sid, data in self.search_results.items() 
                  if now - data["timestamp"] > ttl]
        for sid in expired:
            del self.search_results[sid]
        if expired:
            logger.info(f"Cleaned up {len(expired)} expired sessions")
        return len(expired)

# Background tasks
async def periodic_cleanup_task():
    """Periodic cleanup of caches and expired data."""
    logger.info("Starting periodic cleanup task")
    
    while True:
        try:
            await asyncio.sleep(settings.cleanup_interval_seconds)
            
            # Cleanup embedding cache
            cache = get_embedding_cache()
            expired_cache = await cache.cleanup_expired()
            
            # Cleanup search context
            context_mgr = get_context_manager()
            expired_history = context_mgr.clear_old_history()
            expired_results = context_mgr.cleanup_old_results()
            
            logger.info(
                f"Periodic cleanup: cache={expired_cache}, "
                f"history={expired_history}, results={expired_results}"
            )
            
        except Exception as e:
            logger.error(f"Periodic cleanup error: {e}", exc_info=True)

# Dependency providers
def get_elasticsearch_client() -> AsyncElasticsearch:
    if dependencies.es_client is None:
        dependencies.es_client = AsyncElasticsearch(
            settings.elastic_url,
            basic_auth=(settings.elastic_user, settings.elastic_password),
            request_timeout=30
        )
    return dependencies.es_client

def get_http_client() -> httpx.AsyncClient:
    if dependencies.http_client is None:
        dependencies.http_client = httpx.AsyncClient(timeout=settings.request_timeout)
    return dependencies.http_client

def get_embedding_cache() -> TTLCache:
    if dependencies.embedding_cache is None:
        dependencies.embedding_cache = TTLCache(
            settings.embed_cache_size, 
            settings.cache_ttl_seconds
        )
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
    """Application lifespan manager."""
    logger.info("🚀 Starting semantic search system")
    
    # Initialize dependencies
    get_elasticsearch_client()
    get_http_client()
    get_embedding_cache()
    
    # Start background cleanup task
    cleanup_task = asyncio.create_task(periodic_cleanup_task())
    
    yield
    
    # Cleanup
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
    title="Semantic Search System",
    description="Product search with GPT-powered understanding",
    version="2.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://your-frontend.domain"],  # TODO: replace with actual frontend origin
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Handles validation errors."""
    body = await request.body()
    body_str = body.decode("utf-8", "ignore")
    logger.error(f"Validation error: {exc.errors()} | body={body_str[:500]}")
    return JSONResponse(
        status_code=422, 
        content={"detail": exc.errors(), "body": body_str}
    )

# ENDPOINTS
@app.get("/health", response_model=HealthResponse)
async def health_check(
    es_service: ElasticsearchService = Depends(get_elasticsearch_service)
):
    """Health check endpoint."""
    try:
        s = await es_service.get_index_stats()
        es_status = "connected" if s.get("health", "unknown") != "unknown" else "disconnected"
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
        uptime_seconds=time.time() - app_start_time
    )

@app.get("/config")
async def get_frontend_config():
    """Frontend configuration."""
    return {
        "feature_chat_sse": True,
    }

@app.post("/search", response_model=SearchResponse)
async def search_products(
    request: SearchRequest,
    embedding_service: EmbeddingService = Depends(get_embedding_service),
    es_service: ElasticsearchService = Depends(get_elasticsearch_service)
):
    """Standard product search endpoint."""
    t0 = time.time()
    
    try:
        if not request.query.strip():
            raise HTTPException(400, "Query cannot be empty")

        mode = request.mode.lower().replace("semantic", "knn")
        q = request.query.strip()
        hits: List[Dict] = []
        candidates = max(request.k * 2, 100)

        if mode == "knn":
            v = await embedding_service.generate_embedding(q)
            if not v:
                raise HTTPException(503, "Embedding service unavailable")
            hits = await es_service.semantic_search(v, candidates)
            
        elif mode == "bm25":
            hits = await es_service.bm25_search(q, candidates)
            
        elif mode == "hybrid":
            v = await embedding_service.generate_embedding(q)
            if not v:
                raise HTTPException(503, "Embedding service unavailable")
            hits = await es_service.hybrid_search(v, q, q, candidates)
            
        else:
            raise HTTPException(400, f"Unknown mode: {request.mode}")

        min_score = settings.bm25_min_score if mode == "bm25" else request.min_score
        filtered = [h for h in hits if float(h.get("_score", 0.0)) >= float(min_score)]
        results = [SearchResult.from_hit(h) for h in filtered[:request.k]]

        ms = (time.time() - t0) * 1000.0
        logger.info(f"Search '{q}' ({mode}): {len(results)} results in {ms:.1f}ms")

        return SearchResponse(
            results=results,
            total_found=len(results),
            search_time_ms=ms,
            mode=request.mode
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Search failed: {e}")
        ms = (time.time() - t0) * 1000.0
        return SearchResponse(
            results=[], 
            total_found=0, 
            search_time_ms=ms, 
            mode=request.mode
        )

@app.post("/chat/search", response_model=ChatSearchResponse)
async def chat_search(
    request: ChatSearchRequest,
    gpt_service: GPTService = Depends(get_gpt_service),
    embedding_service: EmbeddingService = Depends(get_embedding_service),
    es_service: ElasticsearchService = Depends(get_elasticsearch_service),
    context_manager: SearchContextManager = Depends(get_context_manager)
):
    """Chat-based product search with GPT understanding."""
    t0 = time.time()
    
    try:
        query = request.query.strip()
        if not query:
            raise HTTPException(400, "Query cannot be empty")
        
        logger.info(f"💬 Chat search: '{query}'")
        
        # Basic validation
        is_valid, validation_error = _validate_query_basic(query)
        if not is_valid:
            ms = (time.time() - t0) * 1000.0
            return ChatSearchResponse(
                query_analysis=QueryAnalysis(
                    original_query=query,
                    expanded_query=query,
                    keywords=[],
                    context_used=False,
                    intent="invalid"
                ),
                results=[],
                recommendations=[],
                search_time_ms=ms,
                context_used=False,
                assistant_message=validation_error,
                dialog_state="validation_error",
                dialog_context=None,
                needs_user_input=True
            )
        
        # Call unified GPT assistant
        assistant_response = await gpt_service.unified_chat_assistant(
            query=query,
            search_history=request.search_history,
            dialog_context=request.dialog_context
        )
        
        action = assistant_response["action"]
        logger.info(f"🤖 Action: {action} (confidence: {assistant_response['confidence']:.2f})")
        
        # Handle greeting
        if action == "greeting":
            ms = (time.time() - t0) * 1000.0
            return ChatSearchResponse(
                query_analysis=QueryAnalysis(
                    original_query=query,
                    expanded_query=query,
                    keywords=[],
                    context_used=False,
                    intent="greeting"
                ),
                results=[],
                recommendations=[],
                search_time_ms=ms,
                context_used=False,
                assistant_message=assistant_response["assistant_message"],
                dialog_state="greeting",
                dialog_context=None,
                needs_user_input=True
            )
        
        # Handle invalid query
        if action == "invalid":
            ms = (time.time() - t0) * 1000.0
            return ChatSearchResponse(
                query_analysis=QueryAnalysis(
                    original_query=query,
                    expanded_query=query,
                    keywords=[],
                    context_used=False,
                    intent="invalid"
                ),
                results=[],
                recommendations=[],
                search_time_ms=ms,
                context_used=False,
                assistant_message=assistant_response["assistant_message"],
                dialog_state="invalid_query",
                dialog_context=None,
                needs_user_input=True
            )
        
        # Handle clarification
        if action == "clarification":
            ms = (time.time() - t0) * 1000.0
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
            
            return ChatSearchResponse(
                query_analysis=QueryAnalysis(
                    original_query=query,
                    expanded_query=query,
                    keywords=[],
                    context_used=False,
                    intent="clarification"
                ),
                results=[],
                recommendations=[],
                search_time_ms=ms,
                context_used=False,
                assistant_message=assistant_response["assistant_message"],
                dialog_state="clarification",
                dialog_context={
                    "clarification_asked": True,
                    "categories_suggested": categories
                },
                needs_user_input=True,
                actions=actions
            )
        
        # Product search
        semantic_subqueries = assistant_response.get("semantic_subqueries", [query])
        if not semantic_subqueries:
            semantic_subqueries = [query]
        
        logger.info(f"🔍 Subqueries: {semantic_subqueries}")
        
        # Generate embeddings in parallel
        embeddings = await embedding_service.generate_embeddings_parallel(
            semantic_subqueries,
            max_concurrent=settings.embedding_max_concurrent
        )
        
        valid_queries = [(sq, emb) for sq, emb in zip(semantic_subqueries, embeddings) if emb]
        
        if not valid_queries:
            raise HTTPException(503, "Embedding service unavailable")
        
        # Parallel semantic search
        k_per_subquery = min(
            settings.chat_search_max_k_per_subquery, 
            max(10, 50 // len(valid_queries))
        )
        
        search_results = await es_service.multi_semantic_search(valid_queries, k_per_subquery)
        
        # Merge results with weighted scores
        all_hits_dict = {}
        for idx, (subquery, hits) in enumerate(search_results.items()):
            weight = 1.0 if idx == 0 else settings.chat_search_subquery_weight_decay ** idx
            
            for hit in hits:
                product_id = hit["_id"]
                base_score = float(hit.get("_score", 0.0))
                weighted_score = base_score * weight
                
                if product_id not in all_hits_dict:
                    all_hits_dict[product_id] = hit.copy()
                    all_hits_dict[product_id]["_score"] = weighted_score
                else:
                    current_score = float(all_hits_dict[product_id].get("_score", 0.0))
                    all_hits_dict[product_id]["_score"] = max(current_score, weighted_score) + 0.1
        
        all_hits = sorted(
            all_hits_dict.values(), 
            key=lambda x: float(x.get("_score", 0.0)), 
            reverse=True
        )
        
        # Adaptive threshold
        max_score = max([float(h.get("_score", 0.0)) for h in all_hits], default=0.0)
        dynamic_threshold = settings.chat_search_score_threshold_ratio * max_score if max_score > 0 else 0.0
        
        # Adjust minimum based on result count
        if len(all_hits) < 10:
            adaptive_min = settings.chat_search_min_score_absolute * 0.7
        elif len(all_hits) < 30:
            adaptive_min = settings.chat_search_min_score_absolute * 0.85
        else:
            adaptive_min = settings.chat_search_min_score_absolute
        
        min_score_threshold = max(adaptive_min, dynamic_threshold) if max_score > 0 else 0.0
        
        candidate_results = [
            SearchResult.from_hit(h) 
            for h in all_hits 
            if float(h.get("_score", 0.0)) >= min_score_threshold
        ]
        
        logger.info(f"✅ Filtered: {len(candidate_results)} from {len(all_hits)}")
        
        # Categorize products
        labels, id_buckets = [], {}
        try:
            labels, id_buckets = await gpt_service.categorize_products(
                candidate_results[:30], 
                query
            )
        except Exception as e:
            logger.error(f"Categorization failed: {e}")
        
        # Get recommendations
        recommendations, assistant_message = await gpt_service.analyze_products(
            candidate_results[:20], 
            query
        )
        
        # Prepare final results
        sorted_candidates = sorted(
            candidate_results, 
            key=lambda r: r.score, 
            reverse=True
        )
        candidate_map = {r.id: r for r in sorted_candidates}
        reco_ids = [rec.product_id for rec in recommendations if rec.product_id in candidate_map]
        ordered_from_reco = [candidate_map[rid] for rid in reco_ids]
        remaining = [r for r in sorted_candidates if r.id not in set(reco_ids)]
        
        max_display = min(request.k, settings.max_chat_display_items)
        final_results = (ordered_from_reco + remaining)[:max_display]

        # Применить выбранную пользователем категорию, если есть
        if request.selected_category and request.selected_category in id_buckets:
            allowed_ids = set(id_buckets[request.selected_category])
            final_results = [r for r in final_results if r.id in allowed_ids]
        
        # Add recommended category (independent of selected category)
        if reco_ids:
            id_buckets["recommended"] = reco_ids
        
        # Create action buttons
        actions = None
        if id_buckets:
            actions = [
                {
                    "type": "button",
                    "action": "select_category",
                    "value": code,
                    "label": CATEGORY_SCHEMA.get(code, {}).get("label", code),
                    "count": len(ids),
                    **({"special": "recommended"} if code == "recommended" else {})
                }
                for code, ids in list(id_buckets.items())[:10]
            ]
        
        # Store for pagination
        context_manager.store_search_results(
            session_id=request.session_id,
            all_results=ordered_from_reco + remaining,
            total_found=len(candidate_results),
            dialog_context={}
        )
        
        ms = (time.time() - t0) * 1000.0
        logger.info(f"✅ Chat search completed: {len(final_results)} products in {ms:.1f}ms")
        
        # Create query analysis
        keywords = [w for w in query.split() if len(w) > 2][:5]
        query_analysis = QueryAnalysis(
            original_query=query,
            expanded_query=query,
            keywords=keywords,
            context_used=bool(request.search_history),
            intent="product_search",
            semantic_subqueries=semantic_subqueries
        )
        
        context_manager.add_search(
            query=query, 
            keywords=keywords, 
            results_count=len(final_results)
        )
        
        # Dialog context for filtering
        dialog_ctx = {
            "original_query": query,
            "available_categories": list(id_buckets.keys()),
            "category_buckets": id_buckets,
            "current_filter": request.selected_category if (request.selected_category in id_buckets) else None
        }
        
        # Log search if logger available
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
                    session_id=request.session_id,
                    query=query,
                    subqueries=semantic_subqueries,
                    total_products_found=len(all_hits),
                    products_after_filtering=len(candidate_results),
                    max_score=max_score,
                    threshold=min_score_threshold,
                    adaptive_min=adaptive_min,
                    dynamic_threshold=dynamic_threshold,
                    top_products=top_products,
                    search_time_ms=ms,
                    intent="product_search",
                    additional_info={
                        "categories": labels,
                        "recommendations_count": len(recommendations),
                        "total_display": len(final_results),
                        "k_per_subquery": k_per_subquery
                    }
                )
            except Exception as log_error:
                logger.warning(f"Failed to log search: {log_error}")
        
        categories_payload = _categories_payload(id_buckets)
        resp = ChatSearchResponse(
            query_analysis=query_analysis,
            results=final_results,
            recommendations=recommendations,
            search_time_ms=ms,
            context_used=query_analysis.context_used,
            assistant_message=assistant_message or "Ось підібрані товари за вашим запитом.",
            dialog_state="final_results",
            dialog_context=dialog_ctx,
            needs_user_input=False,
            actions=actions,
            stage_timings_ms={"total": ms}
        ).model_dump()
        resp["categories"] = categories_payload
        return resp
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Chat search failed: {e}")
        ms = (time.time() - t0) * 1000.0
        return ChatSearchResponse(
            query_analysis=QueryAnalysis(
                original_query=request.query,
                expanded_query=request.query,
                keywords=[],
                context_used=False,
                intent="search"
            ),
            results=[],
            recommendations=[],
            search_time_ms=ms,
            context_used=False,
            assistant_message="Вибачте, виникла помилка. Будь ласка, спробуйте ще раз.",
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
    context_manager: SearchContextManager = Depends(get_context_manager)
):
    """SSE stream for chat search with real-time updates."""
    
    async def event_generator():
        def sse_event(event: str, data: Dict[str, Any]) -> str:
            return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

        t0 = time.time()
        
        try:
            query_stripped = query.strip()
            
            # Decode dialog context
            dialog_context: Optional[Dict[str, Any]] = None
            if dialog_context_b64:
                decoded_dc = _urlsafe_b64_to_json(dialog_context_b64)
                if isinstance(decoded_dc, dict):
                    dialog_context = decoded_dc
            
            # Decode search history
            search_history: List[SearchHistoryItem] = []
            if search_history_b64:
                decoded_sh = _urlsafe_b64_to_json(search_history_b64)
                if isinstance(decoded_sh, list):
                    for item in decoded_sh:
                        if isinstance(item, dict) and "query" in item:
                            try:
                                search_history.append(SearchHistoryItem(
                                    query=item.get("query", ""),
                                    keywords=item.get("keywords", []),
                                    timestamp=item.get("timestamp", time.time()),
                                    results_count=item.get("results_count", 0)
                                ))
                            except Exception as e:
                                logger.warning(f"Failed to parse history item: {e}")
                else:
                    logger.error("Failed to decode search_history: invalid format")
            
            # Basic validation
            is_valid, validation_error = _validate_query_basic(query_stripped)
            if not is_valid:
                yield sse_event("assistant_start", {"length": len(validation_error)})
                for char in validation_error:
                    yield sse_event("assistant_delta", {"text": char})
                    await asyncio.sleep(0.02)
                yield sse_event("assistant_end", {})
                
                ms = (time.time() - t0) * 1000.0
                payload = ChatSearchResponse(
                    query_analysis=QueryAnalysis(
                        original_query=query_stripped,
                        expanded_query=query_stripped,
                        keywords=[],
                        context_used=False,
                        intent="invalid"
                    ),
                    results=[],
                    recommendations=[],
                    search_time_ms=ms,
                    context_used=False,
                    assistant_message=validation_error,
                    dialog_state="validation_error",
                    dialog_context=None,
                    needs_user_input=True
                ).model_dump()
                yield sse_event("final", payload)
                return
            
            # Show thinking status
            yield sse_event("status", {"message": "Думаю...", "type": "thinking"})
            
            # Call unified assistant
            assistant_response = await gpt_service.unified_chat_assistant(
                query=query_stripped,
                search_history=search_history,
                dialog_context=dialog_context
            )
            
            action = assistant_response["action"]
            response_text = assistant_response["assistant_message"]
            
            # Handle greeting
            if action == "greeting":
                yield sse_event("assistant_start", {"length": len(response_text)})
                for char in response_text:
                    yield sse_event("assistant_delta", {"text": char})
                    await asyncio.sleep(0.015)
                yield sse_event("assistant_end", {})
                
                ms = (time.time() - t0) * 1000.0
                payload = ChatSearchResponse(
                    query_analysis=QueryAnalysis(
                        original_query=query_stripped,
                        expanded_query=query_stripped,
                        keywords=[],
                        context_used=False,
                        intent="greeting"
                    ),
                    results=[],
                    recommendations=[],
                    search_time_ms=ms,
                    context_used=False,
                    assistant_message=response_text,
                    dialog_state="greeting",
                    dialog_context=None,
                    needs_user_input=True
                ).model_dump()
                yield sse_event("final", payload)
                return
            
            # Handle invalid
            if action == "invalid":
                yield sse_event("assistant_start", {"length": len(response_text)})
                for char in response_text:
                    yield sse_event("assistant_delta", {"text": char})
                    await asyncio.sleep(0.02)
                yield sse_event("assistant_end", {})
                
                ms = (time.time() - t0) * 1000.0
                payload = ChatSearchResponse(
                    query_analysis=QueryAnalysis(
                        original_query=query_stripped,
                        expanded_query=query_stripped,
                        keywords=[],
                        context_used=False,
                        intent="invalid"
                    ),
                    results=[],
                    recommendations=[],
                    search_time_ms=ms,
                    context_used=False,
                    assistant_message=response_text,
                    dialog_state="invalid_query",
                    dialog_context=None,
                    needs_user_input=True
                ).model_dump()
                yield sse_event("final", payload)
                return
            
            # Handle clarification
            if action == "clarification":
                categories = assistant_response.get("categories", [])
                
                yield sse_event("assistant_start", {"length": len(response_text)})
                for char in response_text:
                    yield sse_event("assistant_delta", {"text": char})
                    await asyncio.sleep(0.02)
                yield sse_event("assistant_end", {})
                
                ms = (time.time() - t0) * 1000.0
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
                
                payload = ChatSearchResponse(
                    query_analysis=QueryAnalysis(
                        original_query=query_stripped,
                        expanded_query=query_stripped,
                        keywords=[],
                        context_used=False,
                        intent="clarification"
                    ),
                    results=[],
                    recommendations=[],
                    search_time_ms=ms,
                    context_used=False,
                    assistant_message=response_text,
                    dialog_state="clarification",
                    dialog_context={
                        "clarification_asked": True,
                        "categories_suggested": categories
                    },
                    needs_user_input=True,
                    actions=actions
                ).model_dump()
                yield sse_event("final", payload)
                return
            
            # Product search
            semantic_subqueries = assistant_response.get("semantic_subqueries", [query_stripped])
            if not semantic_subqueries:
                semantic_subqueries = [query_stripped]
            
            yield sse_event("status", {"message": "Шукаю товари...", "type": "searching"})
            
            keywords = [w for w in query_stripped.split() if len(w) > 2][:5]
            qa = QueryAnalysis(
                original_query=query_stripped,
                expanded_query=query_stripped,
                keywords=keywords,
                context_used=False,
                intent="product_search",
                semantic_subqueries=semantic_subqueries
            )
            
            yield sse_event("analysis", {"query_analysis": qa.model_dump()})
            
            # Generate embeddings
            embeddings = await embedding_service.generate_embeddings_parallel(
                semantic_subqueries,
                max_concurrent=settings.embedding_max_concurrent
            )
            
            valid_queries = [(sq, emb) for sq, emb in zip(semantic_subqueries, embeddings) if emb]
            
            if not valid_queries:
                yield sse_event("error", {
                    "error": "Embedding service unavailable",
                    "message": "Не вдалося згенерувати ембедінги. Спробуйте ще раз."
                })
                return
            
            # Parallel search
            k_per_subquery = min(
                settings.chat_search_max_k_per_subquery, 
                max(10, 50 // len(valid_queries))
            )
            
            search_results = await es_service.multi_semantic_search(valid_queries, k_per_subquery)
            
            # Merge results
            all_hits_dict = {}
            for idx, (subquery, hits) in enumerate(search_results.items()):
                weight = 1.0 if idx == 0 else settings.chat_search_subquery_weight_decay ** idx
                
                for hit in hits:
                    product_id = hit["_id"]
                    base_score = float(hit.get("_score", 0.0))
                    weighted_score = base_score * weight
                    
                    if product_id not in all_hits_dict:
                        all_hits_dict[product_id] = hit.copy()
                        all_hits_dict[product_id]["_score"] = weighted_score
                    else:
                        current_score = float(all_hits_dict[product_id].get("_score", 0.0))
                        all_hits_dict[product_id]["_score"] = max(current_score, weighted_score) + 0.1
            
            all_hits = sorted(
                all_hits_dict.values(), 
                key=lambda x: float(x.get("_score", 0.0)), 
                reverse=True
            )
            
            # Adaptive threshold
            max_score = max([float(h.get("_score", 0.0)) for h in all_hits], default=0.0)
            dynamic_threshold = settings.chat_search_score_threshold_ratio * max_score if max_score > 0 else 0.0
            
            if len(all_hits) < 10:
                adaptive_min = settings.chat_search_min_score_absolute * 0.7
            elif len(all_hits) < 30:
                adaptive_min = settings.chat_search_min_score_absolute * 0.85
            else:
                adaptive_min = settings.chat_search_min_score_absolute
            
            min_score_threshold = max(adaptive_min, dynamic_threshold) if max_score > 0 else 0.0
            
            candidate_results = [
                SearchResult.from_hit(h) 
                for h in all_hits 
                if float(h.get("_score", 0.0)) >= min_score_threshold
            ]
            
            yield sse_event("candidates", {"count": len(candidate_results)})
            
            # Categorize
            labels, id_buckets = [], {}
            try:
                labels, id_buckets = await gpt_service.categorize_products(
                    candidate_results[:30], 
                    query_stripped
                )
            except Exception as e:
                logger.error(f"Categorization failed: {e}")
            
            # Recommendations
            recommendations: List[ProductRecommendation] = []
            assistant_message = ""
            try:
                recommendations, assistant_message = await gpt_service.analyze_products(
                    candidate_results[:20], 
                    query_stripped
                )
            except Exception:
                assistant_message = "Ось підібрані товари за вашим запитом."
            
            # Add recommended category
            reco_ids = [rec.product_id for rec in recommendations]
            if reco_ids:
                id_buckets["recommended"] = reco_ids
            
            yield sse_event("categories", {"items": _categories_payload(id_buckets)})
            yield sse_event("recommendations", {
                "count": len(recommendations),
                "assistant_message": assistant_message
            })
            
            # Stream assistant message
            typed = assistant_message or "Я підібрав для вас добірку товарів."
            yield sse_event("assistant_start", {"length": len(typed)})
            for char in typed:
                yield sse_event("assistant_delta", {"text": char})
                await asyncio.sleep(0.02)
            yield sse_event("assistant_end", {})
            
            # Prepare final results
            sorted_candidates = sorted(
                candidate_results, 
                key=lambda r: float(r.score), 
                reverse=True
            )
            candidate_map = {r.id: r for r in sorted_candidates}
            reco_ids_in_order = [rec.product_id for rec in recommendations if rec.product_id in candidate_map]
            ordered_from_reco = [candidate_map[rid] for rid in reco_ids_in_order]
            remaining = [r for r in sorted_candidates if r.id not in set(reco_ids_in_order)]
            
            max_display = min(k, settings.max_chat_display_items)
            final_results = (ordered_from_reco + remaining)[:max_display]

            # Применить выбранную категорию из query-параметров SSE
            if selected_category and selected_category in id_buckets:
                allowed_ids = set(id_buckets[selected_category])
                final_results = [r for r in final_results if r.id in allowed_ids]
            
            # Create action buttons
            actions = None
            if id_buckets:
                actions = [
                    {
                        "type": "button",
                        "action": "select_category",
                        "value": code,
                        "label": CATEGORY_SCHEMA.get(code, {}).get("label", "Релевантні товари" if code == "misc" else code),
                        "count": len(ids),
                        **({"special": "recommended"} if code == "recommended" else {})
                    }
                    for code, ids in list(id_buckets.items())[:10]
                ]
            
            ms = (time.time() - t0) * 1000.0
            
            # Dialog context
            dialog_ctx = {
                "original_query": query_stripped,
                "available_categories": list(id_buckets.keys()),
                "category_buckets": id_buckets,
                "current_filter": selected_category if (selected_category in id_buckets) else None
            }
            
            # Log search
            if SEARCH_LOGGER_AVAILABLE and search_logger:
                try:
                    top_products = [
                        {
                            "id": p.id,
                            "name": p.title_ua or p.title_ru or p.id,
                            "score": round(float(p.score), 4),
                            "recommended": p.id in set(reco_ids_in_order)
                        }
                        for p in final_results[:20]
                    ]
                    
                    search_logger.log_search_query(
                        session_id=session_id,
                        query=query_stripped,
                        subqueries=qa.semantic_subqueries,
                        total_products_found=len(all_hits),
                        products_after_filtering=len(candidate_results),
                        max_score=max_score,
                        threshold=min_score_threshold,
                        adaptive_min=adaptive_min,
                        dynamic_threshold=dynamic_threshold,
                        top_products=top_products,
                        search_time_ms=ms,
                        intent="product_search",
                        additional_info={
                            "categories": labels,
                            "recommendations_count": len(recommendations),
                            "total_display": len(final_results),
                            "k_per_subquery": k_per_subquery,
                            "method": "SSE"
                        }
                    )
                except Exception as log_error:
                    logger.warning(f"Failed to log search: {log_error}")
            
            payload = ChatSearchResponse(
                query_analysis=qa,
                results=final_results,
                recommendations=recommendations,
                search_time_ms=ms,
                context_used=qa.context_used,
                assistant_message=assistant_message,
                dialog_state="final_results",
                dialog_context=dialog_ctx,
                needs_user_input=False,
                actions=actions,
                stage_timings_ms={"total": ms}
            ).model_dump()
            
            yield sse_event("final", payload)
            
        except Exception as e:
            logger.error(f"SSE error: {e}", exc_info=True)
            yield sse_event("error", {"message": f"Вибачте, виникла помилка: {str(e)}"})

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.post("/chat/search/load-more")
async def load_more_products(
    request: LoadMoreRequest,
    context_manager: SearchContextManager = Depends(get_context_manager)
):
    """Load next batch of products for pagination."""
    try:
        logger.info(f"Load more: session={request.session_id}, offset={request.offset}")
        
        result = context_manager.get_search_results(
            session_id=request.session_id,
            offset=request.offset,
            limit=request.limit
        )
        
        if not result["products"]:
            return {
                "products": [],
                "offset": request.offset,
                "has_more": False,
                "total_found": 0,
                "error": "No saved results"
            }
        
        logger.info(f"Load more: returned {len(result['products'])} products")
        
        return result
        
    except Exception as e:
        logger.exception(f"Load more failed: {e}")
        return {
            "products": [],
            "offset": request.offset,
            "has_more": False,
            "total_found": 0,
            "error": str(e)
        }


@app.get("/stats", response_model=StatsResponse)
async def get_stats(
    es_service: ElasticsearchService = Depends(get_elasticsearch_service)
):
    """System statistics endpoint."""
    s = await es_service.get_index_stats()
    cache = get_embedding_cache()
    return StatsResponse(
        index=settings.index_name,
        documents_count=s.get("documents_count", 0),
        index_size_bytes=s.get("index_size_bytes", 0),
        health=s.get("health", "unknown"),
        embedding_cache_size=len(cache),
        embedding_model=settings.ollama_model_name,
        uptime_seconds=time.time() - app_start_time
    )


@app.post("/api/ta-da/find.gcode")
async def ta_da_find_gcode(
    req: TadaFindRequest,
    http_client: httpx.AsyncClient = Depends(get_http_client)
):
    """Proxy to TA-DA external API."""
    headers = {
        "User-Language": req.user_language or settings.ta_da_default_language,
        "Content-Type": "application/json",
    }
    if settings.ta_da_api_token:
        headers["Authorization"] = f"Bearer {settings.ta_da_api_token}"
    
    payload = {
        "shop_id": req.shop_id or settings.ta_da_default_shop_id,
        "good_code": req.good_code
    }
    
    url = f"{settings.ta_da_api_base_url.rstrip('/')}/find.gcode"
    
    try:
        r = await http_client.post(url, headers=headers, json=payload, timeout=20.0)
        if r.status_code != 200:
            return {"error": "API unavailable", "price": 0, "rating": 0}
        
        data = r.json()
        if not isinstance(data, dict):
            return {"error": "bad_response", "price": 0, "rating": 0}
        
        return data
        
    except Exception as e:
        logger.warning(f"TA-DA proxy error: {e}")
        return {"error": "API unavailable", "price": 0, "rating": 0}


@app.post("/cache/clear")
async def clear_cache(
    cache: TTLCache = Depends(get_embedding_cache)
):
    """Clear embedding cache."""
    try:
        await cache.clear()
        return {"message": "Cache cleared successfully"}
    except Exception as e:
        logger.exception(f"Cache clear failed: {e}")
        return JSONResponse(
            status_code=200,
            content={"message": "Error cleared", "error": str(e)}
        )


@app.get("/cache/stats")
async def get_cache_stats(
    cache: TTLCache = Depends(get_embedding_cache)
):
    """Get cache statistics."""
    try:
        expired = await cache.cleanup_expired()
        return {
            "size": len(cache),
            "capacity": cache.capacity,
            "ttl_seconds": cache.ttl_seconds,
            "expired_cleaned": expired
        }
    except Exception as e:
        logger.exception(f"Cache stats failed: {e}")
        return {
            "size": len(cache),
            "capacity": cache.capacity,
            "ttl_seconds": cache.ttl_seconds,
            "error": str(e)
        }


@app.get("/api/image-proxy")
async def image_proxy(
    url: str,
    http_client: httpx.AsyncClient = Depends(get_http_client)
):
    """Proxy for product images with CORS."""
    try:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            raise HTTPException(400, "Invalid image URL")
        host = parsed.hostname or ""
        if not (host.endswith("ta-da.net.ua") or host.endswith("ta-da.ua")):
            raise HTTPException(400, "Invalid image host")

        logger.debug(f"Image proxy: {url}")

        response = await http_client.get(url, timeout=10.0, follow_redirects=False)
        if 300 <= response.status_code < 400:
            raise HTTPException(400, "Redirects not allowed")
        response.raise_for_status()
        
        return Response(
            content=response.content,
            media_type=response.headers.get("content-type", "image/png"),
            headers={
                "Cache-Control": "public, max-age=86400",
                "Access-Control-Allow-Origin": "*"
            }
        )
    except Exception as e:
        logger.warning(f"Image proxy error: {e}")
        raise HTTPException(404, "Image not found")


# Search logs API (optional - only if search_logger available)
if SEARCH_LOGGER_AVAILABLE and search_logger:
    
    @app.get("/search-logs/sessions")
    async def get_search_log_sessions():
        """Get all logged search sessions."""
        try:
            sessions = search_logger.get_all_sessions()
            return {
                "total": len(sessions),
                "sessions": sessions
            }
        except Exception as e:
            logger.error(f"Failed to get sessions: {e}")
            raise HTTPException(500, str(e))

    @app.get("/search-logs/session/{session_id}")
    async def get_session_logs(session_id: str):
        """Get logs for specific session."""
        try:
            logs = search_logger.get_session_logs(session_id)
            if not logs:
                raise HTTPException(404, f"Session '{session_id}' not found")
            
            return {
                "session_id": session_id,
                "total_queries": len(logs),
                "queries": logs
            }
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to get session logs: {e}")
            raise HTTPException(500, str(e))

    @app.get("/search-logs/report/{session_id}")
    async def get_session_report(session_id: str):
        """Generate analytics report for session."""
        try:
            report = search_logger.generate_session_report(session_id)
            if "error" in report:
                raise HTTPException(404, report["error"])
            
            return report
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to generate report: {e}")
            raise HTTPException(500, str(e))

    @app.get("/search-logs/export")
    async def export_all_sessions():
        """Export all session reports to JSON."""
        try:
            output_path = search_logger.export_all_sessions_report()
            return {
                "success": True,
                "file_path": output_path,
                "message": f"Report exported to {output_path}"
            }
        except Exception as e:
            logger.error(f"Failed to export: {e}")
            raise HTTPException(500, str(e))

    @app.get("/search-logs/stats")
    async def get_search_logs_stats():
        """Get overall search logs statistics."""
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
                    "avg": round(sum(all_search_times) / len(all_search_times), 2) if all_search_times else 0
                },
                "scores": {
                    "min": round(min(all_scores), 4) if all_scores else 0,
                    "max": round(max(all_scores), 4) if all_scores else 0,
                    "avg": round(sum(all_scores) / len(all_scores), 4) if all_scores else 0
                }
            }
        except Exception as e:
            logger.error(f"Failed to get stats: {e}")
            raise HTTPException(500, str(e))


# Run server
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )