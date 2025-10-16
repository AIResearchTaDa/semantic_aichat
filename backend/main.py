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
from elasticsearch import AsyncElasticsearch
from dotenv import load_dotenv
from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from tenacity import (
    retry, stop_after_attempt, wait_exponential,
    retry_if_exception_type
)

# Імпорт модуля для логування пошуку
from search_logger import SearchLogger

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
    gpt_analyze_timeout_seconds: float = Field(default=10.0, env="GPT_ANALYZE_TIMEOUT_SECONDS")

    # Tokens
    gpt_max_tokens_analyze: int = Field(default=1500, env="GPT_MAX_TOKENS_ANALYZE")
    gpt_max_tokens_reco: int = Field(default=2000, env="GPT_MAX_TOKENS_RECO")
    gpt_reco_timeout_seconds: float = Field(default=30.0, env="GPT_RECO_TIMEOUT_SECONDS")  # Окремий timeout для рекомендацій

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
    embedding_max_concurrent: int = Field(default=2, env="EMBEDDING_MAX_CONCURRENT")  # Макс паралельних embedding запитів
    
    # Chat search relevance settings
    chat_search_score_threshold_ratio: float = Field(default=0.4, env="CHAT_SEARCH_SCORE_THRESHOLD_RATIO")  # Мінімальний відсоток від max_score
    chat_search_min_score_absolute: float = Field(default=0.3, env="CHAT_SEARCH_MIN_SCORE_ABSOLUTE")  # Абсолютний мінімум
    chat_search_subquery_weight_decay: float = Field(default=0.85, env="CHAT_SEARCH_SUBQUERY_WEIGHT_DECAY")  # Зменшення ваги для наступних підзапитів
    chat_search_max_k_per_subquery: int = Field(default=20, env="CHAT_SEARCH_MAX_K_PER_SUBQUERY")  # Максимум товарів на підзапит

    # TA-DA external API proxy
    ta_da_api_base_url: str = Field(default="https://api.ta-da.net.ua/v1.2/mobile", env="TA_DA_API_BASE_URL")
    ta_da_api_token: str = Field(default="", env="TA_DA_API_TOKEN")
    ta_da_default_shop_id: str = Field(default="8", env="TA_DA_DEFAULT_SHOP_ID")
    ta_da_default_language: str = Field(default="ua", env="TA_DA_DEFAULT_LANGUAGE")

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

# Ініціалізація логера для аналізу пошуку
search_logger = SearchLogger(logs_dir="search_logs")

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
            self._cleanup_expired_sync()
            if key in self.cache:
                self.cache.move_to_end(key)
            self.cache[key] = value
            self.timestamps[key] = now
            if len(self.cache) > self.capacity:
                oldest_key, _ = self.cache.popitem(last=False)
                self.timestamps.pop(oldest_key, None)

    def _cleanup_expired_sync(self) -> int:
        now = time.time()
        expired_keys = [k for k, t in self.timestamps.items() if now - t > self.ttl_seconds]
        for k in expired_keys:
            self.cache.pop(k, None)
            self.timestamps.pop(k, None)
        return len(expired_keys)

    async def cleanup_expired(self) -> int:
        async with self._lock:
            return self._cleanup_expired_sync()

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

def _build_human_reason(query: str, sr: "SearchResult") -> str:
    """Simplified reason builder without complex categorization."""
    q = (query or "").lower()
    parts: List[str] = ["Відповідає вашому запиту"]
    
    if any(t in q for t in ["хлоп", "мальч", "юнак", "паруб"]):
        parts.append("підходить для хлопчика")
    if any(t in q for t in ["дівч", "девоч", "girl"]):
        parts.append("підходить для дівчинки")
    if any(t in q for t in ["дит", "ребен", "дитяч", "kid", "child"]):
        parts.append("дитяча категорія")
    
    return ", ".join(parts)

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
    keywords: List[str]
    timestamp: float
    results_count: int

class ChatSearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=500)
    search_history: List[SearchHistoryItem] = Field(default_factory=list)
    session_id: str
    k: int = Field(default=50, ge=1, le=200)
    dialog_context: Optional[Dict[str, Any]] = None
    selected_category: Optional[str] = Field(default=None, description="Selected category code or name")

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
    bucket: Optional[str] = Field(default=None, description="must_have | good_to_have | budget")

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

# Category schema - розширена версія на основі асортименту TA-DA
CATEGORY_SCHEMA: Dict[str, Dict[str, Any]] = {
    # ОДЯГ (Clothes)
    "clothes_tshirts": {"label": "Футболки", "keywords": ["футболк", "t-shirt", "tee", "майк"]},
    "clothes_shirts": {"label": "Сорочки", "keywords": ["сороч", "рубаш"]},
    "clothes_pants": {"label": "Штани", "keywords": ["штан", "брюк", "джинс", "джинси"]},
    "clothes_shorts": {"label": "Шорти", "keywords": ["шорт"]},
    "clothes_dresses": {"label": "Сукні", "keywords": ["сукн", "платт"]},
    "clothes_skirts": {"label": "Спідниці", "keywords": ["спідниц", "юбк"]},
    "clothes_sweaters": {"label": "Светри/Худі", "keywords": ["светр", "кофт", "толстовк", "худі"]},
    "clothes_outerwear": {"label": "Куртки/Пальта", "keywords": ["куртк", "пальт", "жилет"]},
    "clothes_underwear": {"label": "Білизна/Шкарпетки", "keywords": ["білизн", "нижн", "труси", "шкарп", "носк", "колгот"]},
    "clothes_sleepwear": {"label": "Піжами/Домашній одяг", "keywords": ["піжам", "домаш", "халат"]},
    "clothes_accessories": {"label": "Аксесуари для одягу", "keywords": ["шапк", "шарф", "рукавиц", "перчат", "ремін", "пояс", "краватк"]},
    "clothes_shoes": {"label": "Взуття", "keywords": ["взутт", "обув", "тапочк", "черевик", "босоніжк", "кросівк"]},
    
    # ІГРАШКИ ТА ІГРИ (Toys & Games)
    "toys_water": {"label": "Для плавання та води", "keywords": ["круг надув", "нарукавник", "жилет надув", "басейн", "водний", "плаван", "матрац надув"]},
    "toys_general": {"label": "Іграшки", "keywords": ["іграш", "игруш", "ляльк", "кукл", "конструктор", "машинк", "м'яч", "мяч", "плюш", "пістолет"]},
    "toys_educational": {"label": "Розвиваючі іграшки", "keywords": ["розвива", "навчал", "розумн", "логічн", "паззл дитяч"]},
    "games_board": {"label": "Настільні ігри", "keywords": ["настільн", "настольн", "пазл", "лото", "доміно", "монопол", "мозаїк"]},
    "toys_outdoor": {"label": "Для активного відпочинку", "keywords": ["скейтборд", "самокат", "велосипед", "м'яч спорт", "ракетк", "бадмінтон"]},
    
    # КУХНЯ ТА ПОСУД (Kitchen & Tableware)
    "house_kitchen_cookware": {"label": "Кухонний посуд", "keywords": ["кастр", "сковор", "каструл", "казан", "сотейн", "жаровн"]},
    "house_kitchen_tableware": {"label": "Посуд для сервірування", "keywords": ["таріл", "тарел", "чашк", "келих", "склянк", "стакан", "блюд", "салатниц"]},
    "house_kitchen_cutlery": {"label": "Столові прибори", "keywords": ["вилк", "ложк", "ніж столов", "прибор"]},
    "house_kitchen_tools": {"label": "Кухонні аксесуари", "keywords": ["дошк", "ніж кухон", "терк", "відкривач", "консервн", "лопатк", "шумівк", "дуршлаг"]},
    "house_kitchen_storage": {"label": "Ємності для зберігання", "keywords": ["контейнер", "ємкіст", "банк", "пляшк", "термос", "ланч"]},
    "house_kitchen_textiles": {"label": "Кухонний текстиль", "keywords": ["рушник кухон", "прихватк", "фартух", "серветк"]},
    
    # ПРИБИРАННЯ ТА ГОСПОДАРСЬКІ ТОВАРИ (Cleaning & Household)
    "house_cleaning_tools": {"label": "Інвентар для прибирання", "keywords": ["швабр", "щітк", "віник", "совок", "відро", "ганчір", "губк"]},
    "house_cleaning_chemicals": {"label": "Побутова хімія", "keywords": ["чист", "миюч", "порошок", "гель для миття", "засіб", "спрей", "відбілювач", "кондиціонер для білизни"]},
    "house_cleaning_bathroom": {"label": "Для ванної кімнати", "keywords": ["туалет", "ванн", "душ", "йоржик", "тримач", "дозатор", "килимок ванн"]},
    "house_laundry": {"label": "Для прання", "keywords": ["прання", "сушарк", "прищіпк", "мотузк", "прасувал", "гладильн"]},
    
    # КОСМЕТИКА ТА ГІГІЄНА (Cosmetics & Hygiene)
    "cosmetics_skincare": {"label": "Догляд за шкірою", "keywords": ["крем", "лосьон", "тонік", "маск косметич", "скраб", "пілінг", "сироватк"]},
    "cosmetics_suncare": {"label": "Сонцезахисні засоби", "keywords": ["сонцезахисн", "spf", "захист від сонця", "крем для засмаг"]},
    "cosmetics_body": {"label": "Догляд за тілом", "keywords": ["гель для душ", "мило", "шампун", "бальзам для волосся", "дезодоран", "антиперспірант"]},
    "cosmetics_oral": {"label": "Гігієна порожнини рота", "keywords": ["зубн паст", "щітк зубн", "нитк зубн", "ополіскувач"]},
    "cosmetics_firstaid": {"label": "Аптечка", "keywords": ["пантен", "бинт", "пластир", "вата", "перекис", "зелен", "йод"]},
    
    # КАНЦЕЛЯРІЯ (Stationery)
    "stationery_notebooks": {"label": "Зошити та блокноти", "keywords": ["зошит", "тетрад", "блокнот", "щоденник", "записн"]},
    "stationery_paper": {"label": "Папір", "keywords": ["папір", "бумаг", "аркуш", "картон", "кольоров папір"]},
    "stationery_writing": {"label": "Ручки та олівці", "keywords": ["ручк", "олівц", "карандаш", "маркер", "фломастер", "текстовиділювач"]},
    "stationery_cases": {"label": "Пенали та папки", "keywords": ["пенал", "папк", "файл", "скоросзшивач", "портфель"]},
    "stationery_art": {"label": "Товари для творчості", "keywords": ["фарб", "акварел", "пензл", "пластилін", "клей", "ножиці", "циркуль", "лінійк"]},
    "stationery_office": {"label": "Офісні товари", "keywords": ["степлер", "скобк", "кнопк", "скріпк", "стікер", "клейк стрічк", "коректор"]},
    
    # ТОВАРИ ДЛЯ ДОМУ (Home & Living)
    "home_decor": {"label": "Декор та прикраси", "keywords": ["свічк", "рамк", "ваз", "статуетк", "декор", "прикрас"]},
    "home_textiles": {"label": "Домашній текстиль", "keywords": ["постільн", "простирадл", "подушк", "ковдр", "плед", "покривал"]},
    "home_storage": {"label": "Організація та зберігання", "keywords": ["коробк", "корзин", "органайзер", "полиц", "вішалк", "підставк"]},
    "home_lighting": {"label": "Освітлення", "keywords": ["лампочк", "ліхтар", "світильник", "торшер", "бра", "світлодіод"]},
    "home_electronics": {"label": "Побутова електроніка", "keywords": ["вентилятор", "обігрівач", "годинник", "будильник", "ваги", "термометр"]},
    "home_garden": {"label": "Для саду та городу", "keywords": ["горщик", "лійк", "садов", "городн", "інструмент садов", "насінн", "добрив"]},
    
    # СЕЗОННІ ТОВАРИ (Seasonal)
    "seasonal_summer": {"label": "Літні товари", "keywords": ["пляжн", "купальник", "окуляри сонцезахисн", "вентилятор", "кондиціонер"]},
    "seasonal_winter": {"label": "Зимові товари", "keywords": ["санк", "лопат для снігу", "антиожеледн", "обігрівач"]},
    "seasonal_holiday": {"label": "Святкові товари", "keywords": ["гірлянд", "ялинк", "іграшк ялинк", "мішур", "серпантин", "повітр кульк"]},
    "seasonal_bbq": {"label": "Для пікніка та барбекю", "keywords": ["мангал", "шампур", "решітк", "посуд однораз", "термосумк", "покривал для пікнік"]},
    
    # ЗАХИСТ ВІД КОМАХ (Insect Protection)
    "home_insects": {"label": "Від комах", "keywords": ["комар", "мух", "таракан", "аерозол", "репелент", "фумігатор", "сітк москітн", "стрічк клейк від", "спірал від комар", "пастк"]},
    
    # АВТОТОВАРИ (Auto)
    "auto_accessories": {"label": "Автотовари", "keywords": ["автомобіл", "машин авто", "килим авто", "освіжувач авто", "тримач авто", "чохл авто"]},
    
    # ПЕТ ТОВАРИ (Pet)
    "pet_supplies": {"label": "Для тварин", "keywords": ["собак", "кіш", "корм", "мисочк", "іграшк для тварин", "нашийник", "поводок"]},
}

def _assign_category_code(sr: "SearchResult") -> Optional[str]:
    text = " ".join(filter(None, [sr.title_ua, sr.title_ru, sr.description_ua, sr.description_ru])).lower()
    best_code, best_hits = None, 0
    for code, data in CATEGORY_SCHEMA.items():
        hits = sum(1 for kw in data["keywords"] if kw in text)
        if hits > best_hits:
            best_code, best_hits = code, hits
    return best_code

def _allowed_category_codes_for_query(query: str) -> Optional[Set[str]]:
    q = (query or "").lower()
    clothes_tokens = [
        "одяг", "одеж", "футболк", "сороч", "штан", "брюк", "шорт", "сукн", "платт",
        "спідниц", "юбк", "кофт", "светр", "толстовк", "худі", "куртк", "пальт",
        "жилет", "білизн", "нижн", "труси", "піжам", "комбінез"
    ]
    shoes_tokens = ["взут", "обув", "капц", "чобіт", "черевик", "шльопанц", "кросівк", "туфл", "сандал", "тапочк"]
    accessories_tokens = ["шкарп", "носк", "колгот", "панчох", "шапк", "шарф", "рукавиц", "перчат"]
    toys_tokens = ["іграш", "игруш", "ляльк", "кукл", "конструктор", "м'яч", "мяч", "плюш", "водний пістолет", "нарукавник", "басейн"]
    house_tokens = ["посуд", "кастр", "сковор", "таріл", "чашк", "келих", "кухон", "ганчір", "швабр", "спрей", "миюч"]
    fishing_tokens = ["рибал", "рыбал", "вудил", "удочк", "спінінг", "спиннинг", "леска", "волосінь", "гачок", "крючок", "наживк", "приманк", "катушк", "рибальськ"]
    garden_tokens = ["насінн", "семен", "сад", "город", "рослин", "растен", "квіт", "цвет", "розсад"]
    stationery_tokens = ["зошит", "тетрад", "ручк", "олівц", "карандаш", "пенал", "канцел", "фломастер", "маркер", "фарб", "краск", "папір", "бумаг", "альбом", "щоденник"]
    cosmetics_tokens = ["зубн", "паст", "шампун", "мило", "гель", "крем", "косметик", "догляд", "гігієн"]
    pets_tokens = ["котів", "кішок", "собак", "тварин", "корм для", "намисто для", "іграшка для кота", "миска для"]

    is_clothes = any(t in q for t in clothes_tokens)
    is_shoes = any(t in q for t in shoes_tokens)
    is_accessories = any(t in q for t in accessories_tokens)
    is_toys = any(t in q for t in toys_tokens)
    is_house = any(t in q for t in house_tokens)
    is_fishing = any(t in q for t in fishing_tokens)
    is_garden = any(t in q for t in garden_tokens)
    is_stationery = any(t in q for t in stationery_tokens)
    is_cosmetics = any(t in q for t in cosmetics_tokens)
    is_pets = any(t in q for t in pets_tokens)

    # Риболовля
    if is_fishing:
        return {"fishing"}
    
    # Садівництво
    if is_garden:
        return {"garden"}
    
    # Канцелярія
    if is_stationery:
        return {"stationery"}
    
    # Косметика
    if is_cosmetics:
        return {"cosmetics"}
    
    # Товари для тварин
    if is_pets:
        return {"pets"}

    # Одяг (без взуття та аксесуарів)
    if is_clothes and not is_shoes and not is_toys and not is_house:
        return {code for code in CATEGORY_SCHEMA.keys() if code.startswith("clothes_") and code != "clothes_shoes" and code != "clothes_accessories"}
    
    # Взуття окремо
    if is_shoes and not is_toys and not is_house:
        return {code for code in CATEGORY_SCHEMA.keys() if code == "clothes_shoes" or code.startswith("shoes_")}
    
    # Аксесуари (шкарпетки, колготи, шапки)
    if is_accessories and not is_shoes and not is_toys and not is_house:
        return {code for code in CATEGORY_SCHEMA.keys() if code == "clothes_accessories" or code.startswith("accessories_") or "sock" in code or "tights" in code}
    
    # Іграшки
    if is_toys and not is_clothes and not is_shoes:
        return {code for code in CATEGORY_SCHEMA.keys() if code.startswith("toys_") or code.startswith("games_")}
    
    # Господарські товари
    if is_house and not (is_clothes or is_toys or is_shoes):
        return {code for code in CATEGORY_SCHEMA.keys() if code.startswith("house_")}
    
    return None

def _aggregate_categories(products: List["SearchResult"]) -> Tuple[Dict[str, List[SearchResult]], List[Tuple[str, int]]]:
    buckets: Dict[str, List[SearchResult]] = {}
    for p in products:
        code = _assign_category_code(p)
        if not code:
            continue
        buckets.setdefault(code, []).append(p)
    counts = sorted(((c, len(v)) for c, v in buckets.items()), key=lambda x: x[1], reverse=True)
    return buckets, counts

# Utilities
def _validate_query_basic(query: str) -> Tuple[bool, Optional[str]]:
    """
    Базова валідація запиту.
    Returns: (is_valid, error_message)
    """
    if not query or not query.strip():
        return False, "Запит не може бути порожнім"
    
    query = query.strip()
    
    # Перевірка довжини
    if len(query) < 2:
        return False, "Запит занадто короткий. Напишіть хоча б 2 символи."
    
    if len(query) > 500:
        return False, "Запит занадто довгий. Максимум 500 символів."
    
    # Перевірка на тільки цифри або спецсимволи
    if re.match(r'^[\d\s\W]+$', query) and not re.search(r'[a-zA-Zа-яА-ЯіїєґІЇЄҐ]', query):
        return False, "Будь ласка, напишіть текстовий запит."
    
    # Перевірка на спам (повторювані символи)
    if re.search(r'(.)\1{7,}', query):  # 8+ однакових символів підряд
        return False, "Будь ласка, напишіть коректний запит."
    
    return True, None


# Повний список категорій магазину TA-DA! (використовується для каталогу)
FULL_CATALOG_CATEGORIES = [
    "Одяг (футболки, штани, піжами, сукні)",
    "Взуття (капці, шльопанці, чоботи)",
    "Колготи та шкарпетки",
    "Посуд (тарілки, чашки, каструлі, сковорідки)",
    "Кухонне приладдя",
    "Господарські товари (миючі засоби, губки, серветки)",
    "Косметика та гігієна",
    "Дитячі іграшки",
    "Канцелярія (зошити, ручки, олівці)",
    "Текстиль (рушники, постільна білизна)",
    "Декор для дому",
    "Рибальські товари",
    "Насіння для садівництва",
    "Товари для тварин"
]



def _extract_json_safely(text: str) -> Dict[str, Any]:
    """Extracts JSON from model response, ignoring code blocks and other symbols."""
    if not text:
        return {}
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

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

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        logger.warning(f"Failed to extract JSON from text: {text[:500]}...")
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
        """Compatibility with different embedding APIs."""
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
                    timeout=settings.request_timeout
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
                if isinstance(emb, list) and (settings.vector_dimension <= 0 or len(emb) == settings.vector_dimension):
                    return emb
                if emb is not None and isinstance(emb, list):
                    logger.warning("Embedding dimension mismatch; accepting as is.")
                    return emb
            except Exception as e:
                last_exc = e
                logger.warning(f"Embedding payload variant failed: {e}")
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
            logger.info("Embedding cache hit")
            return cached
        try:
            t0 = time.time()
            emb = await asyncio.wait_for(self._call_ollama_api(text), timeout=15.0)  # Збільшено до 15s
            if emb:
                await self.cache.put(key, emb)
                logger.info(f"Embedding generated in {time.time()-t0:.2f}s")
                return emb
        except asyncio.TimeoutError:
            logger.warning(f"⏱️ Embedding timeout після 15s для: '{text[:50]}...'")
        except Exception as e:
            logger.error(f"Embedding generation error: {e}")
        return None

    async def generate_embeddings_parallel(self, texts: List[str], max_concurrent: int = 2) -> List[Optional[List[float]]]:
        """
        Parallel embedding generation with concurrency limit.
        
        Args:
            texts: List of texts to generate embeddings for
            max_concurrent: Maximum number of concurrent embedding requests (default: 2)
                           Обмежуємо до 2 щоб не перевантажувати повільний embedding API
        """
        if not texts:
            return []
        
        # Семафор для обмеження кількості одночасних запитів
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
                logger.debug(f"✅ Embedding OK for '{texts[i][:60]}...' (dim={len(emb)})")
                result.append(emb)
                success_count += 1
        
        logger.info(f"📊 Parallel embedding (max {max_concurrent} concurrent): {success_count}/{len(texts)} successful")
        
        return result

class ElasticsearchService:
    def __init__(self, es_client: AsyncElasticsearch):
        self.es_client = es_client

    async def semantic_search(self, query_vector: List[float], k: int = 10) -> List[Dict]:
        """
        Semantic search using vector field configured in settings.
        
        Currently indexed vector field:
        - description_vector: embeddings from description text
        
        NOTE: The description_vector field contains embeddings of product descriptions.
        This means semantic search works best for conceptual queries about product features,
        while BM25 is better for exact product names and codes.
        Together in hybrid search, they complement each other.
        """
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
                logger.warning(f"No results from {settings.vector_field_name}, trying description_vector fallback")
                search_params["knn"]["field"] = "description_vector"
                res = await self.es_client.search(**search_params)
                hits = res.get("hits", {}).get("hits", [])
            
            return hits
        except Exception as e:
            logger.error(f"Semantic search error with {settings.vector_field_name}: {e}")
            # Try fallback to description_vector
            if settings.vector_field_name != "description_vector":
                try:
                    logger.info("Attempting fallback to description_vector")
                    search_params = {
                        "index": settings.index_name,
                        "size": k,
                        "knn": {
                            "field": "description_vector",
                            "query_vector": query_vector,
                            "k": k,
                            "num_candidates": min(settings.knn_num_candidates, max(100, k * 20))
                        }
                    }
                    res = await self.es_client.search(**search_params)
                    return res.get("hits", {}).get("hits", [])
                except Exception as fallback_error:
                    logger.error(f"Semantic search fallback also failed: {fallback_error}")
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
                logger.info(f"'{subquery}': found {len(result)} products")
            else:
                logger.warning(f"Search error for '{subquery}': {result}")
                output[subquery] = []
        
        logger.info(f"Parallel search: {len(output)}/{len(query_vectors)} successful")
        
        return output

    async def bm25_search(self, query_text: str, k: int = 10) -> List[Dict]:
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

    async def dsl_search(self, dsl: Dict[str, Any], k: int = 50) -> List[Dict]:
        try:
            dsl_local = dict(dsl or {})
            size = dsl_local.pop("size", k)
            res = await self.es_client.search(index=settings.index_name, size=size, **dsl_local)
            return res.get("hits", {}).get("hits", [])
        except Exception as e:
            logger.error(f"DSL search error: {e}")
            return []

    async def hybrid_search(
        self, 
        query_vector: Optional[List[float]], 
        query_text_semantic: str,
        query_text_bm25: str,
        k: int = 10
    ) -> List[Dict]:
        """
        Hybrid search combining semantic (vector) and lexical (BM25) search.
        
        This provides the best of both worlds:
        - Semantic search: finds conceptually similar products (synonyms, related items)
        - BM25 search: finds exact keyword matches (product names, codes)
        
        The results are merged using weighted combination (configurable via HYBRID_ALPHA).
        
        Args:
            query_vector: Embedding vector for semantic search
            query_text_semantic: Text query for semantic context (currently unused)
            query_text_bm25: Text query for BM25 lexical search
            k: Number of results to return
            
        Returns:
            List of merged search results, sorted by combined score
        """
        try:
            if not query_vector:
                logger.error("hybrid_search: no embedding vector provided")
                raise ValueError("Query vector is required for hybrid search")
            
            # Run both searches in parallel for better performance
            # Get 2x candidates to improve merge quality
            candidates = max(k * 2, 50)
            
            sem_task = asyncio.create_task(self.semantic_search(query_vector, candidates))
            bm_task = asyncio.create_task(self.bm25_search(query_text_bm25, candidates))
            
            sem, bm = await asyncio.gather(sem_task, bm_task)
            
            logger.info(f"Hybrid search: semantic={len(sem)}, BM25={len(bm)} candidates")
            
            # Merge and return top k results
            return self._merge(sem, bm, k)
            
        except Exception as e:
            logger.error(f"Hybrid search error: {e}")
            raise

    def _merge(self, sem: List[Dict], bm: List[Dict], k: int) -> List[Dict]:
        if settings.hybrid_fusion.lower() == "rrf":
            return self._rrf_merge(sem, bm, k)
        return self._weighted_merge(sem, bm, k)

    def _weighted_merge(self, sem: List[Dict], bm: List[Dict], k: int) -> List[Dict]:
        """
        Weighted merge of semantic and BM25 results.
        
        Alpha (HYBRID_ALPHA) controls the balance:
        - 0.7 = 70% semantic + 30% BM25 (good for conceptual search)
        - 0.5 = 50% semantic + 50% BM25 (balanced)
        - 0.3 = 30% semantic + 70% BM25 (good for exact matches)
        
        Scores are normalized by max score in each result set before combining.
        """
        alpha = settings.hybrid_alpha
        beta = 1.0 - alpha
        
        # Normalize scores
        sem_scores = [h.get("_score", 0.0) for h in sem]
        bm_scores = [h.get("_score", 0.0) for h in bm]
        max_sem = max(sem_scores) if sem_scores else 1.0
        max_bm = max(bm_scores) if bm_scores else 1.0
        
        combined: Dict[str, float] = {}
        pool: Dict[str, Dict] = {}
        
        # Add semantic results
        for h in sem:
            _id = h["_id"]
            pool[_id] = h
            normalized_score = h.get("_score", 0.0) / max_sem
            combined[_id] = combined.get(_id, 0.0) + alpha * normalized_score
        
        # Add BM25 results
        for h in bm:
            _id = h["_id"]
            pool[_id] = pool.get(_id) or h
            normalized_score = h.get("_score", 0.0) / max_bm
            combined[_id] = combined.get(_id, 0.0) + beta * normalized_score
        
        # Sort by combined score
        ordered = sorted(combined.items(), key=lambda x: x[1], reverse=True)
        
        out = []
        for _id, sc in ordered[:k]:
            hit = pool[_id]
            hit["_score"] = sc
            out.append(hit)
        
        logger.info(f"Hybrid merge: {len(sem)} semantic + {len(bm)} BM25 → {len(out)} results (α={alpha:.2f})")
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
        logger.info(f"Hybrid merge(RRF c={c}) -> {len(out)}")
        return out

    async def get_index_stats(self) -> Dict[str, Any]:
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

CONTEXTUAL_SYNONYMS = {
    "одяг": ["куртка", "штани", "світер", "футболка", "сукня", "джинси"],
    "хлопчик": ["дитячий", "для хлопця"],
    "дівчинка": ["дитячий", "для дівчини"],
    "дитина": ["дитячий"],
    "шурупи": ["кріплення", "будівництво", "гвинти", "саморізи"],
    "меблі": ["ліжко", "тумба", "комод", "шафа", "стіл", "стілець"],
    "кухня": ["посуд", "сковорідка", "каструля", "тарілки", "чашки"],
    "прибирання": ["побутова хімія", "ганчірка", "миючий засіб", "швабра"]
}

# Детальна схема категорій для GPT (на базі реального асортименту 38,420 товарів)
CATEGORY_SCHEMA = {
    "accessories": {
        "label": "Аксесуари",
        "keywords": ["шкарпетки", "колготи", "гольфи", "панчохи", "сліди", "шапка", "шарф", "рукавиці", "ремінь", "сумка", "гаманець", "рюкзак", "парасолька", "окуляри", "заколка", "резинка для волосся"]
    },
    "toys": {
        "label": "Іграшки",
        "keywords": ["іграшка", "лялька", "машинка", "конструктор", "пазл", "м'яка іграшка", "автомат", "пістолет", "трактор", "динозавр"]
    },
    "clothing": {
        "label": "Одяг",
        "keywords": ["футболка", "штани", "шорти", "сукня", "костюм", "кофта", "світшот", "халат", "піжама", "жилет", "куртка", "худі", "лонгслів", "джинси", "водолазка"]
    },
    "stationery": {
        "label": "Канцелярія",
        "keywords": ["зошит", "блокнот", "олівець", "ручка", "маркер", "фарби", "пензлик", "акварель", "стругачка", "папка", "пенал", "щоденник", "папір", "клей"]
    },
    "household": {
        "label": "Господарські товари",
        "keywords": ["відро", "миска", "таз", "губка", "щітка", "швабра", "ганчірка", "мило", "засіб", "прання", "миття", "чищення", "серветка"]
    },
    "tableware": {
        "label": "Кухонний посуд",
        "keywords": ["каструля", "сковорода", "ложка", "виделка", "ніж", "тарілка", "чашка", "стакан", "келих", "блюдо", "салатник", "форма для випікання"]
    },
    "garden": {
        "label": "Для саду і городу",
        "keywords": ["насіння", "добриво", "грунт", "горщок", "лопата", "граблі", "інсектицид", "фунгіцид", "шланг", "субстрат"]
    },
    "cosmetics": {
        "label": "Косметика і гігієна",
        "keywords": ["шампунь", "бальзам", "крем", "гель для душу", "зубна паста", "зубна щітка", "дезодорант", "фарба для волосся", "туш", "помада"]
    },
    "footwear": {
        "label": "Взуття",
        "keywords": ["чоботи", "черевики", "кросівки", "кеди", "тапки", "тапочки", "шльопанці", "капці", "туфлі", "босоніжки"]
    },
    "electrical": {
        "label": "Електротовари",
        "keywords": ["лампа", "ліхтар", "подовжувач", "розетка", "вимикач", "батарейка", "зарядний", "кабель", "навушники"]
    },
    "festive": {
        "label": "Святкові товари",
        "keywords": ["свічка", "листівка", "коробка подарункова", "валентинка", "гірлянда", "кулька", "значок", "магніт", "одноразовий посуд"]
    },
    "containers": {
        "label": "Контейнери і зберігання",
        "keywords": ["контейнер", "органайзер", "коробка", "ємність", "лоток"]
    },
    "food": {
        "label": "Продукти харчування",
        "keywords": ["печиво", "цукерки", "шоколад", "чіпси", "напій", "кава", "морозиво", "пончик", "тістечко", "хліб", "соус"]
    },
    "textiles": {
        "label": "Домашній текстиль",
        "keywords": ["ковдра", "подушка", "рушник", "скатертина", "серветка", "килим", "штора", "постільна білизна"]
    },
    "pets": {
        "label": "Товари для тварин",
        "keywords": ["корм", "ласощі", "нашийник", "повідець", "лежак", "годівниця", "протипаразитний", "для котів", "для собак"]
    },
    "fishing": {
        "label": "Риболовля",
        "keywords": ["вудилище", "леса", "гачок", "котушка", "воблер", "приманка", "поплавець", "прикормка", "бойл"]
    },
    "creativity": {
        "label": "Творчість і хобі",
        "keywords": ["розмальовка", "картина за номерами", "алмазна мозаїка", "фоаміран", "фетр", "набір для творчості", "барельєф"]
    },
    "sports": {
        "label": "Спорт і фітнес",
        "keywords": ["м'яч", "еспандер", "гантелі", "скакалка", "тренажер", "велосипед", "самокат", "боксерський"]
    },
    "auto": {
        "label": "Автотовари",
        "keywords": ["ароматизатор автомобільний", "щітка склоочисника", "тримач", "трос", "автохімія"]
    }
}

# GPT Service
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
        """
        🎯 УНІВЕРСАЛЬНИЙ GPT АСИСТЕНТ - замінює всі окремі функції.
        
        Обробляє всі типи запитів:
        - Привітання/прощання
        - Нерелевантні запити
        - Уточнюючі питання
        - Пошук товарів
        
        Returns: {
            "action": str,  # "greeting", "invalid", "clarification", "product_search"
            "confidence": float,
            "assistant_message": str,  # Повідомлення користувачу
            "semantic_subqueries": List[str],  # Підзапити для пошуку (якщо product_search)
            "categories": Optional[List[str]],  # Категорії для уточнення (якщо clarification)
            "needs_user_input": bool  # Чи потрібен подальший input від користувача
        }
        """
        if not settings.enable_gpt_chat:
            logger.error("❌ GPT вимкнено (ENABLE_GPT_CHAT=False)")
            raise ValueError("GPT chat assistant is disabled. Please enable ENABLE_GPT_CHAT.")
        
        if not settings.openai_api_key:
            logger.error("❌ OpenAI API key не налаштований")
            raise ValueError("OpenAI API key is not configured. Please set OPENAI_API_KEY.")
        
        # Формуємо контекст історії
        context = ""
        if search_history:
            recent_history = search_history[-3:]
            context_lines = [f"- Користувач шукав: '{it.query}'" for it in recent_history]
            context = "**Історія попередніх пошуків:**\n" + "\n".join(context_lines)
        
        # Перевіряємо чи було вже уточнення
        already_clarified = dialog_context and dialog_context.get("clarification_asked", False)
        clarification_note = ""
        if already_clarified:
            suggested_cats = dialog_context.get("categories_suggested", [])
            clarification_note = f"""
⚠️⚠️⚠️ **КРИТИЧНО ВАЖЛИВО** ⚠️⚠️⚠️

Користувач ВЖЕ ОТРИМАВ уточнююче питання про категорії: {suggested_cats}

Тепер користувач ВІДПОВІДАЄ на це питання!

❌ НЕ ПИТАЙ БІЛЬШЕ УТОЧНЕНЬ!
✅ ОБОВ'ЯЗКОВО action: "product_search"
✅ Використай відповідь користувача для створення semantic_subqueries

Приклади:
- Питали "Які товари для дому?" → Відповідь "покажи усі" → шукай ["товари для дому", "домашні товари", "для дому"]
- Питали "Які іграшки?" → Відповідь "будь-які" → шукай ["іграшки", "іграшки для дітей", "дитячі іграшки"]
- Питали "Який одяг?" → Відповідь "футболки" → шукай ["футболки", "футболка чоловіча", "футболка жіноча"]

**action ПОВИНЕН БУТИ: "product_search"**
"""
            logger.info(f"⚠️ Користувач вже отримував clarification! Категорії: {suggested_cats}")
        
        # 🆕 Формуємо список категорій з CATEGORY_SCHEMA
        categories_list = "\n".join([f"- {cat['label']}" for cat in CATEGORY_SCHEMA.values()])
        
        prompt = f"""Ти – AI асистент інтернет-магазину TA-DA! (https://ta-da.ua/) — великого універмагу з 38 000+ товарів для дому та сім'ї.

🏪 **АСОРТИМЕНТ МАГАЗИНУ TA-DA! (на базі реальної бази 38,420 товарів):**

**Основні категорії та ТОП бренди:**
- 🧦 **Аксесуари** (10.9% асортименту - найбільша категорія!): шкарпетки, колготи, гольфи, шапки, сумки, рюкзаки, парасольки, заколки
  *Бренди*: Mio Senso, Житомир, Gooddi, TA-DA!
- 🧸 **Іграшки** (7.4%): ляльки, машинки, конструктори, пазли, м'які іграшки
  *Бренди*: **Danko toys** (№1 бренд, 771 товар!), Strateg, Bamsic, TY
- 👕 **Одяг** (6.8%): футболки, штани, піжами, спортивні костюми, халати, джинси
  *Бренди*: Samo, Beki, Garant, FAZO-R
- 📚 **Канцелярія** (4.9%): зошити, ручки, олівці, блокноти, папки, фарби
  *Бренди*: Axent, Buromax, Zibi
- 🏠 **Господарські товари** (4.9%): засоби для прибирання, губки, серветки, відра, швабри
  *Бренди*: **TA-DA!** (власний бренд, 532 товари!), Domestos, Sarma, Flexy
- 🍽️ **Кухонний посуд** (4.7%): тарілки, чашки, каструлі, сковорідки, ложки, виделки
  *Бренди*: **Stenson** (353 товари), Luminarc, S&T, Bormioli, Glass Ideas
- 🌱 **Для саду і городу** (3.8%): **насіння** (1232 товари!), добрива, горщики, інструменти
  *Бренди*: Велес, Насіння України, Кращий урожай
- 🧴 **Косметика і гігієна** (3.7%): шампуні, креми, зубні пасти, гелі для душу
  *Бренди*: Colgate, Palmolive, Eveline
- 👞 **Взуття** (3.0%): чоботи, шльопанці, капці, кеди
  *Бренди*: **Gipanis** (272 товари), gemelli, Galera, Fogo, Chobotti
- 💡 **Електротовари** (3.0%): лампи, ліхтарі, батарейки, кабелі, навушники, розетки
  *Бренди*: Lumano, LED товари
- 🎉 **Святкові товари** (2.3%): свічки, листівки, подарункові коробки, прикраси
- 📦 **Контейнери** (2.1%): органайзери, ємності для зберігання
- 🍪 **Продукти** (1.8%): печиво, цукерки, чіпси, напої
- 🏡 **Домашній текстиль** (1.5%): ковдри, подушки, рушники
- 🐾 **Товари для тварин** (1.4%): корми для котів (130+), собак (25+), лежаки
- 🎣 **Риболовля** (1.4%): вудилища, леса, гачки, приманки
- 🎨 **Творчість і хобі** (1.4%): розмальовки, картини за номерами, алмазні мозаїки
- 🏋️ **Спорт і фітнес** (1.0%): м'ячі, еспандери, велосипеди, самокати
- 🚗 **Автотовари** (0.6%): ароматизатори, щітки склоочисників

**Детальні підкатегорії (для action: clarification):**
{categories_list}

💡 **КОНТЕКСТНІ СИТУАЦІЇ** (товари для життєвих потреб):
• Романтична вечеря → посуд (бокали, тарілки), свічки, декор, текстиль
• День народження → іграшки, посуд, декор, святкові товари
• Школа/навчання → канцелярія, рюкзаки, зошити, ручки
• Пікнік → посуд, текстиль, ігри, товари для відпочинку
• Прибирання → побутова хімія, губки, інвентар
• Новоселля → посуд, текстиль, організатори, декор
• Подарунок → іграшки, косметика, посуд, одяг

{context}{clarification_note}

**Запит користувача:** "{query}"

---

## 💬 РОЗУМІННЯ КОНТЕКСТУ (ДУЖЕ ВАЖЛИВО!)

**Якщо є історія пошуків - використовуй її для розуміння неповних запитів:**

📝 **Приклади контекстних запитів:**
- Історія: "червона футболка" → Новий запит: "а синя?" → Розумій: "синя футболка"
- Історія: "капці 41 розмір" → Новий запит: "а 42?" → Розумій: "капці 42 розмір"
- Історія: "корм для котів" → Новий запит: "а для собак?" → Розумій: "корм для собак"
- Історія: "посуд Luminarc" → Новий запит: "покажи інший бренд" → Розумій: "посуд інших брендів"

⚠️ **Правила:**
- Якщо запит містить тільки колір/розмір/варіант ("а синя?", "42 розмір?") → візьми товар з історії
- Якщо запит містить порівняння ("а інший?", "покажи ще") → продовжуй тему з історії  
- Якщо запит повний та зрозумілий сам по собі → історія не потрібна

---

## 🎯 ТВОЯ РОЛЬ - УНІВЕРСАЛЬНИЙ АСИСТЕНТ

Ти маєш **4 типи дій** які можеш виконати:

### 1️⃣ **ACTION: "greeting"** - Привітання/Прощання/Подяка
Використовуй коли:
- Просте привітання: "привіт", "hello", "добрий день", "вітаю"
- Прощання: "до побачення", "бувай", "goodbye"
- Подяка: "дякую", "спасибі", "thanks"
- Привітання + запит: "привіт, шукаю футболку" → це НЕ greeting, а product_search!

**Твоя відповідь:**
- Привітання: лаконічно привітай і запропонуй допомогу
- Прощання: коротко попрощайся
- Подяка: коротко подякуй

### 2️⃣ **ACTION: "invalid"** - Нерелевантний запит (ДУЖЕ РІДКО!)
Використовуй ТІЛЬКИ якщо запит ЯВНО не стосується товарів або магазину:
- ❌ "як приготувати борщ", "рецепт салату" (кулінарні рецепти)
- ❌ "погода сьогодні", "новини України" (інформаційні запити)
- ❌ "asdfgh", "123456" (випадковий текст)
- ❌ "розкажи жарт", "заспівай пісню" (розваги)

⚠️ **НЕ ВИКОРИСТОВУЙ invalid для:**
- ✅ "романтична вечеря" → product_search (посуд, свічки)
- ✅ "день народження" → product_search (іграшки, декор)
- ✅ "до школи" → product_search (канцелярія)

**Твоя відповідь:** Лаконічно поясни що не можеш допомогти з цим запитом, запропонуй шукати товари.

### 3️⃣ **ACTION: "clarification"** - Потрібне уточнення
Використовуй коли користувач задає ЗАГАЛЬНЕ ПИТАННЯ про асортимент:
- ✅ "що у вас є з одягу?" → запитай конкретну категорію (Футболки? Штани? Піжами?)
- ✅ "які іграшки є?" → покажи підкатегорії іграшок
- ✅ "який корм?" → уточни для якої тварини (котів, собак, риб?)
- ✅ "покажи каталог", "що є?", "які категорії?" → покажи ВСІІ основні категорії магазину

❌ **НЕ уточнюй якщо:**
- "футболки Beki" → це конкретний запит, шукай!
- "корм для котів" → це конкретно, шукай!
- "іграшки для дітей 5 років" → це досить конкретно, шукай!

**Твоя відповідь:**
- Задай коротке уточнююче питання (1-2 речення)
- Поверни 4-8 конкретних підкатегорій у полі "categories" (використовуй ТОЧНІ НАЗВИ з "Детальні підкатегорії" вище!)
- **ФОРМАТУВАННЯ**: Якщо категорій багато (6+), перелічуй їх З НОВИХ РЯДКІВ у повідомленні!

**Приклади відповідей:**

📌 Якщо запит про КОНКРЕТНУ категорію ("іграшки", "одяг"):
```
assistant_message: "Які іграшки вас цікавлять? Можу показати ляльки, машинки, конструктори або розвиваючі ігри."
categories: ["Іграшки", "Розвиваючі іграшки", "Настільні ігри", "М'які іграшки"]
```

📌 Якщо запит про ВЕСЬ КАТАЛОГ ("покажи каталог", "що у вас є", "які категорії"):
```
assistant_message: "У нас широкий асортимент товарів! Основні категорії:

🧦 Аксесуари (шкарпетки, колготи, сумки)
🧸 Іграшки (ляльки, конструктори, пазли)
👕 Одяг (футболки, штани, піжами)
📚 Канцелярія (зошити, ручки, папки)
🍽️ Кухонний посуд
🏠 Господарські товари
🌱 Для саду і городу
👞 Взуття

Що вас цікавить?"
categories: ["Аксесуари", "Іграшки", "Одяг", "Канцелярія", "Кухонний посуд", "Господарські товари", "Для саду і городу", "Взуття"]
```

### 4️⃣ **ACTION: "product_search"** - Пошук товарів (найчастіше!)
Використовуй коли користувач:
- Шукає конкретний товар: "червоні футболки", "капці 41"
- Згадує бренд: "Beki", "gemelli", "Luminarc"
- Називає категорію: "посуд", "іграшки", "одяг"
- Описує ситуацію де потрібні товари: "романтична вечеря", "до школи", "день народження"

**Твоя відповідь:**
- Напиши коротке повідомлення (1-2 речення) що зараз підбираєш товари
- **ГОЛОВНЕ:** створи 2-5 "semantic_subqueries" - різні варіанти пошукових запитів для знаходження найкращих товарів

**Приклади semantic_subqueries:**
- Запит "футболка чоловіча чорна" → ["футболка чоловіча чорна", "футболка Beki чорна", "футболка Garant чорна"]
- Запит "капці 41" → ["капці домашні 41 розмір", "капці gemelli 41", "тапочки чоловічі 41"]
- Запит "романтична вечеря" → ["бокали для вина", "свічки декоративні", "тарілки красиві", "серветки святкові"]
- Запит "день народження дитини" → ["іграшки для дітей", "святковий посуд", "декор для свята"]

**💬 Приклади з КОНТЕКСТОМ (використовуй історію!):**
- Історія: "червона футболка" + Запит: "а синя?" → ["футболка синя", "футболка Beki синя", "футболка чоловіча синя"]
- Історія: "капці 41" + Запит: "42 розмір" → ["капці 42 розмір", "капці домашні 42", "тапочки 42"]
- Історія: "корм для котів" + Запит: "для собак" → ["корм для собак", "собачий корм", "їжа для собак"]

**Правила для semantic_subqueries:**
1. ⭐ СПОЧАТКУ перевір історію - якщо запит неповний, доповни з історії!
2. Перший підзапит = найточніший варіант (з урахуванням контексту!)
3. Наступні = варіації з брендами, синонімами, розширеннями
4. Для ситуацій (вечеря, свято) - перелік конкретних товарів
5. 2-5 підзапитів (не більше!)

---

## 📋 ТВОЇ ПРИНЦИПИ РОБОТИ:

🎯 **Лаконічний**: Відповідай коротко, без зайвих слів. 1-3 речення максимум (окрім переліку категорій).

🔍 **Критичний**: Розумій коли запит НЕ про товари → action: "invalid"

⭐ **Найкращий варіант**: Намагайся дати тільки те що дійсно потрібно. Не показуй все підряд.

❓ **Задавай питання**: Якщо запит занадто загальний ("що є?", "які товари?") → action: "clarification"

💬 **По-дружньому**: Спілкуйся тепло але професійно. 

📝 **ФОРМАТУВАННЯ ВІДПОВІДЕЙ**:
- Для product_search і greeting: без емодзі, лаконічно
- Для clarification при переліку 6+ категорій: 
  ✅ ОБОВ'ЯЗКОВО кожна категорія З НОВОГО РЯДКА
  ✅ Використовуй емодзі категорій:
     🧦 Аксесуари | 🧸 Іграшки | 👕 Одяг | 📚 Канцелярія
     🍽️ Кухонний посуд | 🏠 Господарські товари | 🌱 Для саду і городу
     👞 Взуття | 💡 Електротовари | 🎉 Святкові товари
     📦 Контейнери | 🍪 Продукти | 🏡 Домашній текстиль
     🐾 Товари для тварин | 🎣 Риболовля | 🎨 Творчість і хобі
     🏋️ Спорт і фітнес | 🚗 Автотовари | 🧴 Косметика і гігієна
  ✅ Формат: "емодзі Назва (короткі приклади товарів)"
  
**ПРАВИЛЬНИЙ приклад для "покажи каталог":**
```
У нас широкий асортимент товарів! Основні категорії:

🧦 Аксесуари (шкарпетки, колготи, сумки, шапки)
🧸 Іграшки (ляльки, машинки, конструктори, пазли)
👕 Одяг (футболки, штани, піжами, костюми)
📚 Канцелярія (зошити, ручки, олівці, папки)
🍽️ Кухонний посуд (тарілки, чашки, каструлі)
🏠 Господарські товари (засоби для прибирання, губки)
🌱 Для саду і городу (насіння, добрива, інструменти)
👞 Взуття (чоботи, шльопанці, капці)

Що вас цікавить?
```

**НЕПРАВИЛЬНО** ❌: "Можу показати різні варіанти, такі як одяг, іграшки, косметика та інші."
**ПРАВИЛЬНО** ✅: Перелік категорій З НОВИХ РЯДКІВ з емодзі!

---

## 📤 ФОРМАТ ВІДПОВІДІ (JSON):

{{
  "action": "greeting" | "invalid" | "clarification" | "product_search",
  "confidence": 0.95,
  "assistant_message": "Твоє коротке повідомлення користувачу українською (1-3 речення)",
  "semantic_subqueries": ["підзапит 1", "підзапит 2", "підзапит 3"],  // ТІЛЬКИ для product_search
  "categories": ["Категорія 1", "Категорія 2"],  // ТІЛЬКИ для clarification
  "needs_user_input": true | false
}}

**Правила для полів:**
- `assistant_message`: завжди заповнений, українською мовою, лаконічно
- `semantic_subqueries`: ТІЛЬКИ для action="product_search", 2-5 підзапитів
- `categories`: ТІЛЬКИ для action="clarification", 4-8 конкретних підкатегорій
- `needs_user_input`: true для greeting/invalid/clarification, false для product_search

---

## ⚠️ ПРІОРИТЕТ ДІЙ (від найважливішого):

1. ⭐ **ПЕРШИЙ ПРІОРИТЕТ**: Якщо було уточнення раніше (dialog_context.clarification_asked=true)
   → **ЗАВЖДИ І БЕЗ ВИНЯТКІВ action: "product_search"**
   → НЕ можна action: "clarification" вдруге!
   → Навіть якщо відповідь загальна ("покажи усі", "будь-які") - шукай товари!

2. Якщо згадано бренд або конкретну категорію товарів → product_search

3. Якщо описана ситуація де потрібні товари → product_search

4. Якщо ЗАГАЛЬНЕ питання про асортимент і НЕ було clarification раніше → clarification

5. Якщо просте привітання без запиту → greeting

6. Якщо ЯВНО не про товари → invalid (дуже рідко!)

**Тепер проаналізуй запит користувача та дай відповідь у форматі JSON.**"""

        try:
            data = await asyncio.wait_for(
                self._chat({
                    "model": settings.gpt_model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": settings.gpt_temperature,
                    "response_format": {"type": "json_object"},
                    "max_tokens": settings.gpt_max_tokens_analyze
                }),
                timeout=float(settings.gpt_analyze_timeout_seconds)
            )
            
            content = data["choices"][0]["message"]["content"]
            result = _extract_json_safely(content)
            
            # Валідація відповіді
            if "action" not in result:
                logger.error(f"❌ GPT не повернув 'action': {result}")
                raise ValueError(f"GPT response invalid: missing 'action' field")
            
            # Встановлюємо defaults
            result.setdefault("confidence", 0.8)
            result.setdefault("assistant_message", "Шукаю для вас товари...")
            result.setdefault("semantic_subqueries", [])
            result.setdefault("categories", None)
            result.setdefault("needs_user_input", result["action"] in ["greeting", "invalid", "clarification"])
            
            logger.info(f"✅ Unified assistant: action={result['action']}, confidence={result['confidence']:.2f}")
            return result
            
        except asyncio.TimeoutError:
            logger.error("⏱️ Unified assistant timeout")
            raise TimeoutError(f"GPT request timeout after 15 seconds")
        except Exception as e:
            logger.error(f"❌ Unified assistant error: {e}", exc_info=True)
            raise
    
    async def analyze_products(self, products: List[SearchResult], query: str) -> Tuple[List[ProductRecommendation], Optional[str]]:
        """Returns recommendations. Never raises HTTPException - fallback to local on failure."""
        if not products:
            return [], "На жаль, не знайдено відповідних товарів за вашим запитом. Спробуйте уточнити пошук."

        if not settings.enable_gpt_chat or not settings.openai_api_key:
            return self._local_recommendations(products, query)

        items = [{
            "index": i + 1,
            "id": p.id,
            "title": p.title_ua or p.title_ru or "",
            "desc": (p.description_ua or p.description_ru or "")[:200]
        } for i, p in enumerate(products)]

        prompt = f"""
Ти експертний консультант інтернет-магазину TA-DA! (https://ta-da.ua/) — великого універмагу з 38 000+ товарів для дому та сім'ї.

📌 **КОНТЕКСТ МАГАЗИНУ TA-DA!:**
У нас є: одяг (Beki, Garant), взуття (gemelli, Gipanis), колготи (Conte, Siela, Giulia), посуд (Luminarc, Stenson), 
господарські товари (Domestos, Sarma), косметика (Colgate, Palmolive), дитячі іграшки (Danko toys, TY), 
канцелярія (Axent, Buromax), рибальські товари, насіння для садівництва, товари для тварин.

**Запит користувача:** "{query}"

Твоє завдання — проаналізувати знайдені товари та рекомендувати найкращі з них.

## 📦 Знайдені товари ({len(items)} кандидатів):
{json.dumps(items, ensure_ascii=False, indent=2)}

## 🎯 ПРАВИЛА РЕКОМЕНДАЦІЙ:

1. **Кількість**: Рекомендуй **5-10 найкращих товарів** (не 1-2!). Якщо запит дуже конкретний (наприклад "футболка Beki 48") — можна 3-5.

2. **relevance_score** (оцінка релевантності):
   - **0.9-1.0**: ІДЕАЛЬНО відповідає запиту (точна назва, бренд, характеристики)
     Приклад: запит "капці gemelli 41" → товар "Капці домашні gemelli чоловічі 41 Остін"
   
   - **0.7-0.89**: ДУЖЕ ДОБРЕ підходить (підходить за категорією + бренд або розмір)
     Приклад: запит "футболка чоловіча" → товар "Футболка чоловіча Beki 48 чорна"
   
   - **0.5-0.69**: ДОБРЕ підходить (підходить за категорією, але без точного бренду)
     Приклад: запит "шкарпетки" → товар "Шкарпетки Житомир жіночі сірі 37-41"
   
   - **0.3-0.49**: Підходить ЧАСТКОВО (схожа категорія або суміжний товар)
     Приклад: запит "прибирання" → товар "Губка кухонна Фрекен БОК"

3. **Пріоритет брендів**: Якщо користувач шукає конкретний бренд (Beki, gemelli, Luminarc, Conte, Domestos) — ставь такі товари вище.

4. **Різноманітність**: Намагайся підібрати різні варіанти (різні кольори, розміри, моделі), якщо запит загальний.

5. **bucket** (категорія рекомендації):
   - "must_have" — топ 3 найкращі товари
   - "good_to_have" — решта хороших варіантів (4-10 місце)

6. **reason** (пояснення): Напиши КОНКРЕТНЕ пояснення українською:
   - ✅ ДОБРЕ: "Ідеально підходить: футболка Beki чорна розмір 48, як ви шукали"
   - ✅ ДОБРЕ: "Класичні капці gemelli для дому, зручні та практичні"
   - ❌ ПОГАНО: "Підходить за запитом"
   - ❌ ПОГАНО: "Релевантний товар"

## 📋 Поверни JSON:
{{
  "recommendations": [
    {{
      "product_index": 1,
      "relevance_score": 0.95,
      "reason": "Конкретне пояснення чому саме цей товар підходить",
      "bucket": "must_have"
    }}
  ],
  "assistant_message": "Персоналізоване повідомлення користувачу українською (2-3 речення). Поясни що ти підібрав добірку товарів (5-10 варіантів) які підходять під їхній запит. Згадай ключові категорії або бренди з добірки."
}}

## ⚠️ ВАЖЛИВО:
- ОБОВ'ЯЗКОВО рекомендуй **мінімум 5 товарів**, якщо є хоч трохи релевантні!
- Включай товари з score >= 0.4 для різноманітності
- Всі пояснення пиши ТІЛЬКИ українською мовою
- Згадуй бренди у поясненнях (Beki, gemelli, Luminarc, Conte і т.д.)
- Будь конкретним у поясненнях — не пиши загальні фрази
"""
        try:
            data = await asyncio.wait_for(self._chat({
                "model": settings.gpt_model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": settings.gpt_temperature,
                "response_format": {"type": "json_object"},
                "max_tokens": settings.gpt_max_tokens_reco
            }), timeout=float(settings.gpt_reco_timeout_seconds))
            content = data["choices"][0]["message"]["content"]
            obj = _extract_json_safely(content)

            recs: List[ProductRecommendation] = []
            raw_recos = obj.get("recommendations", [])
            if not isinstance(raw_recos, list):
                raw_recos = []

            for r in raw_recos:
                if not isinstance(r, dict):
                    continue
                idx = int(r.get("product_index", 0)) - 1
                relevance_score = float(r.get("relevance_score", 0.0))
                # Приймаємо >= 0.4 (GPT рекомендує >= 0.5, але даємо трохи гнучкості)
                if relevance_score >= 0.4 and 0 <= idx < len(products):
                    prod = products[idx]
                    recs.append(ProductRecommendation(
                        product_id=prod.id,
                        relevance_score=relevance_score,
                        reason=r.get("reason", "Рекомендовано"),
                        title=prod.title_ua or prod.title_ru,
                        bucket=r.get("bucket")
                    ))

            recs.sort(key=lambda x: x.relevance_score, reverse=True)
            msg = obj.get("assistant_message") or "Я підібрав для вас відповідні варіанти."
            logger.info(f"🎯 GPT відмітив {len(recs)} релевантних товарів з {len(products)} кандидатів")
            if not recs:
                return self._local_recommendations(products, query)
            return recs, msg
        except Exception as e:
            logger.warning(f"⚠️ analyze_products: GPT збій ({e}). Локальні рекомендації.")
            return self._local_recommendations(products, query)

    def _local_recommendations(self, products: List[SearchResult], query: str) -> Tuple[List[ProductRecommendation], str]:
        q_tokens = [t for t in re.split(r"\W+", (query or "").lower()) if t]
        max_es = max((float(p.score) for p in products), default=1.0) or 1.0

        def score_for(p: SearchResult) -> float:
            base = float(p.score) / max_es
            text = " ".join(filter(None, [p.title_ua, p.title_ru, p.description_ua, p.description_ru])).lower()
            bonus = 0.0
            for t in q_tokens:
                if t and t in text:
                    bonus += 0.05
            return min(1.0, base + min(0.3, bonus))

        ranked = sorted(products, key=lambda x: score_for(x), reverse=True)
        top = ranked[: min(len(ranked), 20)]
        recs = [
            ProductRecommendation(
                product_id=p.id,
                relevance_score=score_for(p),
                reason=_build_human_reason(query, p),
                title=p.title_ua or p.title_ru,
                bucket=("must_have" if i < 3 else "good_to_have" if i < 10 else "budget")
            )
            for i, p in enumerate(top)
            if score_for(p) >= 0.3
        ]
        msg = "Я підібрав варіанти на основі відповідності вашому запиту."
        return recs, msg

    async def recommend_top_products(
        self, 
        products: List[SearchResult], 
        original_query: str,
        intent_description: str,
        subquery_mapping: Dict[str, str]
    ) -> Tuple[List[ProductRecommendation], str]:
        """Selects top-3 best products from candidates based on GPT analysis."""
        if not products:
            return [], "На жаль, не знайдено підходящих товарів."

        if not settings.enable_gpt_chat or not settings.openai_api_key:
            recs, msg = self._local_recommendations(products[:10], original_query)
            return recs[:3], msg

        items = []
        for i, p in enumerate(products[:20]):
            found_via = subquery_mapping.get(p.id, "general search")
            items.append({
                "index": i + 1,
                "id": p.id,
                "title": p.title_ua or p.title_ru or "",
                "desc": (p.description_ua or p.description_ru or "")[:150],
                "score": round(float(p.score), 2),
                "found_via": found_via
            })

        prompt = f"""Ти – персональний консультант магазину TA-DA! (https://ta-da.ua/) — великого універмагу з 38 000+ товарів для дому та сім'ї.

📌 **КОНТЕКСТ МАГАЗИНУ:**
Основні категорії: одяг (Beki, Garant), взуття (gemelli, Gipanis), колготи (Conte, Siela), посуд (Luminarc, Stenson), 
господарські товари (Domestos, Sarma), косметика (Colgate, Palmolive), іграшки (Danko toys, TY), канцелярія (Axent, Buromax).

**Запит користувача:** "{original_query}"
**Що хоче користувач:** {intent_description}

Я знайшов {len(items)} релевантних товарів. Твоє завдання — вибрати **ТІЛЬКИ 3 НАЙКРАЩІ** товари, які максимально підходять для потреби користувача.

## 📦 Знайдені товари (з контекстом пошуку):
{json.dumps(items, ensure_ascii=False, indent=2)}

## 🎯 Критерії вибору топ-3:

1. **РЕЛЕВАНТНІСТЬ** (найважливіше!):
   - Товар має ТОЧНО відповідати запиту користувача
   - Якщо користувач шукає конкретний бренд — обов'язково вибери його
   - Якщо запит про конкретну категорію (футболка, капці) — вибери найкращі варіанти з неї

2. **РІЗНОМАНІТНІСТЬ** (тільки якщо запит загальний):
   - Якщо запит загальний ("товари для дому") — вибирай з РІЗНИХ категорій
   - Якщо запит конкретний ("капці gemelli") — всі 3 можуть бути з однієї категорії, але різні моделі

3. **КОМПЛЕКСНІСТЬ** (для комплексних запитів):
   - Якщо запит про набір ("прибирання", "школа") — товари мають доповнювати один одного
   - Приклад: для "прибирання" вибери: миючий засіб + губки + серветки

4. **ПОПУЛЯРНІ БРЕНДИ** (пріоритет):
   - Якщо є товари відомих брендів (Beki, gemelli, Luminarc, Conte, Domestos) — віддавай їм перевагу

5. **Поле "found_via"** показує через який підзапит знайдено товар — це допоможе зрозуміти контекст

## 📋 Поверни JSON:
{{
  "top_3": [
    {{
      "product_index": 1,
      "relevance_score": 0.95,
      "reason": "Конкретне пояснення (1-2 речення): чому саме ЦЕЙ товар ідеально підходить, згадай бренд якщо є",
      "category": "Назва категорії товару"
    }},
    {{
      "product_index": 5,
      "relevance_score": 0.90,
      "reason": "Конкретне пояснення з брендом...",
      "category": "..."
    }},
    {{
      "product_index": 3,
      "relevance_score": 0.85,
      "reason": "Конкретне пояснення...",
      "category": "..."
    }}
  ],
  "assistant_message": "Персоналізоване повідомлення користувачу українською (2-3 речення): представ підібрані товари, поясни їх переваги та як вони вирішують потребу."
}}

## ⚠️ ВАЖЛИВО:
- Вибери **РІВНО 3 товари**
- **Reason** має бути КОНКРЕТНИМ з назвою бренду:
  ✅ ДОБРЕ: "Класичні капці gemelli для дому — зручні, м'які, ідеально підходять для щоденного носіння"
  ✅ ДОБРЕ: "Футболка Beki чорна — якісна бавовна, універсальний стиль, відмінно підходить для повсякденного вигляду"
  ❌ ПОГАНО: "Підходить за запитом"
  ❌ ПОГАНО: "Релевантний товар"
- Згадуй **бренди** у поясненнях (Beki, gemelli, Luminarc, Conte, Domestos і т.д.)
- ВСІ пояснення пиши ТІЛЬКИ українською мовою
- Якщо запит конкретний — всі 3 можуть бути з однієї категорії але різні варіанти
- Якщо запит загальний — краще вибирай з різних категорій
"""

        try:
            data = await asyncio.wait_for(self._chat({
                "model": settings.gpt_model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.3,
                "response_format": {"type": "json_object"},
                "max_tokens": settings.gpt_max_tokens_reco
            }), timeout=float(settings.gpt_reco_timeout_seconds))

            content = data["choices"][0]["message"]["content"]
            obj = _extract_json_safely(content) or {}

            top_3 = obj.get("top_3", [])
            if not isinstance(top_3, list) or len(top_3) == 0:
                logger.warning("⚠️ GPT не повернув топ-3 → локальний фолбек")
                recs, msg = self._local_recommendations(products[:10], original_query)
                return recs[:3], msg

            recs = []
            for item in top_3[:3]:
                if not isinstance(item, dict):
                    continue
                idx = int(item.get("product_index", 0)) - 1
                if 0 <= idx < len(products):
                    prod = products[idx]
                    recs.append(ProductRecommendation(
                        product_id=prod.id,
                        relevance_score=float(item.get("relevance_score", 0.8)),
                        reason=item.get("reason", "Відповідає вашому запиту"),
                        title=prod.title_ua or prod.title_ru,
                        bucket="must_have"
                    ))

            assistant_msg = obj.get("assistant_message", "Ось 3 найкращі варіанти для вас!")

            logger.info(f"🎯 GPT вибрав топ-{len(recs)} товарів з {len(products)} кандидатів")

            if not recs:
                recs, msg = self._local_recommendations(products[:10], original_query)
                return recs[:3], msg

            return recs, assistant_msg

        except Exception as e:
            logger.warning(f"⚠️ recommend_top_products: GPT помилка ({e}). Локальний фолбек.")
            recs, msg = self._local_recommendations(products[:10], original_query)
            return recs[:3], msg

    async def categorize_products(self, products: List[SearchResult], query: str, timeout_seconds: float = 15.0) -> Tuple[List[str], Dict[str, List[str]]]:
        """Product categorization. Never fails - has local fallback."""
        if not products:
            return [], {}

        if not settings.enable_gpt_chat or not settings.openai_api_key:
            return self._local_categorize(products, query)

        items = [{
            "id": p.id,
            "title": p.title_ua or p.title_ru or "",
            "desc": (p.description_ua or p.description_ru or "")[:200]
        } for p in products[:30]]

        # Створюємо список доступних категорій для GPT
        available_categories = list(CATEGORY_SCHEMA.values())
        category_list = [f"- {cat['label']}" for cat in available_categories]

        prompt = f"""
Ти - експерт з категоризації товарів для інтернет-магазину TA-DA! (https://ta-da.ua/) — великого універмагу з 38 000+ товарів.

📌 **КОНТЕКСТ МАГАЗИНУ TA-DA!:**
Основні напрямки: одяг (Beki, Garant), взуття (gemelli, Gipanis), колготи/шкарпетки (Conte, Siela, Giulia), 
посуд (Luminarc, Stenson), господарські товари (Domestos, Sarma), косметика (Colgate, Palmolive), 
іграшки (Danko toys, TY), канцелярія (Axent, Buromax), рибальські товари, насіння, товари для тварин.

Твоє завдання: розподілити знайдені товари по ІСНУЮЧИХ категоріях магазину.

## 📋 ДОСТУПНІ КАТЕГОРІЇ (використовуй ТІЛЬКИ ці назви):
{chr(10).join(category_list)}

## 🎯 ПРАВИЛА КАТЕГОРИЗАЦІЇ:

1. **ТОЧНІ НАЗВИ**: Використовуй ТОЧНІ назви категорій зі списку вище (копіюй як є, включаючи регістр!)

2. **КІЛЬКІСТЬ КАТЕГОРІЙ**: Вибери 2-6 найрелевантніших категорій для знайдених товарів

3. **МІНІМУМ ТОВАРІВ**: Кожна категорія має містити мінімум 2 товари (не створюй категорії з 1 товаром)

4. **ЛОГІЧНА КАТЕГОРИЗАЦІЯ**: Враховуй назву товару, опис та запит користувача

5. **ПРИКЛАДИ правильної категоризації:**
   - "Футболка чоловіча Beki" → категорія "Футболки/Майки"
   - "Капці домашні gemelli" → категорія "Взуття домашнє"
   - "Колготи жіночі Conte 40 den" → категорія "Колготи/Панчохи"
   - "Тарілка Luminarc 20 см" → категорія "Посуд для сервірування"
   - "Зошит Тетрада 48 аркушів" → категорія "Зошити"
   - "Зубна паста Colgate 75 мл" → категорія "Догляд за порожниною рота"
   - "Іграшка машинка" → категорія "Іграшки"
   - "Засіб Domestos 750 мл" → категорія "Миючі засоби"

6. **БРЕНДИ допомагають**: Якщо бачиш відомий бренд - це підказка:
   - Beki, Garant, FAZO-R → одяг
   - gemelli, Gipanis → взуття
   - Conte, Siela, Giulia → колготи/шкарпетки
   - Luminarc, Stenson → посуд
   - Domestos, Sarma → господарські товари
   - Colgate, Palmolive → косметика
   - Danko toys, TY → іграшки

## 📤 JSON формат відповіді:
{{
  "categories": ["Категорія 1", "Категорія 2", "Категорія 3"],
  "buckets": {{
    "Категорія 1": ["id1", "id2", "id3"],
    "Категорія 2": ["id4", "id5"],
    "Категорія 3": ["id6", "id7", "id8"]
  }}
}}

## 📦 Запит користувача: "{query}"

## 📦 Товари для категоризації:
{json.dumps(items, ensure_ascii=False, indent=2)}

## ⚠️ ВАЖЛИВО:
- Використовуй ТІЛЬКИ категорії зі списку вище
- Не вигадуй нові категорії
- Кожна категорія = мінімум 2 товари
- Копіюй назви категорій ТОЧНО (включаючи регістр, слеш, дефіси)
- Відповідь: тільки JSON без додаткових коментарів
"""
        try:
            data = await asyncio.wait_for(self._chat({
                "model": settings.gpt_model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.1,  # Знизили для більш точного дотримання інструкцій
                "response_format": {"type": "json_object"},
                "max_tokens": 2000
            }), timeout=timeout_seconds)

            content = data["choices"][0]["message"]["content"]
            obj = _extract_json_safely(content) or {}
            raw_labels = obj.get("categories") or []
            raw_buckets = obj.get("buckets") or {}

            labels: List[str] = [str(c).strip() for c in raw_labels if isinstance(c, str) and str(c).strip()]
            valid_ids = {p.id for p in products}
            buckets: Dict[str, List[str]] = {}
            label_set = set(labels)
            if isinstance(raw_buckets, dict):
                for label, ids in raw_buckets.items():
                    if not isinstance(label, str):
                        continue
                    l = label.strip()
                    if not l:
                        continue
                    arr = [pid for pid in (ids or []) if isinstance(pid, str) and pid in valid_ids]
                    if arr:
                        buckets[l] = arr
                        label_set.add(l)

            final_labels = [l for l in labels if l in label_set]
            for l in buckets.keys():
                if l not in final_labels:
                    final_labels.append(l)
            if not final_labels and not buckets:
                return self._local_categorize(products, query)
            return final_labels[:20], buckets
        except Exception as e:
            logger.warning(f"⚠️ categorize_products: GPT збій ({e}). Локальна категоризація.")
            return self._local_categorize(products, query)

    def _local_categorize(self, products: List[SearchResult], query: str) -> Tuple[List[str], Dict[str, List[str]]]:
        logger.info(f"🏷️ _local_categorize: processing {len(products)} products for query '{query}'")
        buckets, counts = _aggregate_categories(products)
        logger.info(f"🏷️ _local_categorize: found {len(buckets)} category buckets, counts: {counts}")
        
        # Фільтруємо категорії за allowed ДО вибору топ-6
        allowed = _allowed_category_codes_for_query(query)
        logger.info(f"🏷️ _local_categorize: allowed categories for query: {allowed}")
        
        if allowed:
            # Фільтруємо counts тільки за дозволеними категоріями
            counts = [(c, n) for (c, n) in counts if c in allowed and n >= 2]
            logger.info(f"🏷️ _local_categorize: after filtering by allowed: {counts}")
        else:
            # Якщо немає фільтра - просто вимагаємо мінімум 2 товари
            counts = [(c, n) for (c, n) in counts if n >= 2]
        
        if not counts:
            label = "Релевантні товари"
            logger.info(f"🏷️ _local_categorize: no categories with 2+ products, returning default label")
            return [label], {label: [p.id for p in products[: min(30, len(products))]]}
        
        # Беремо топ-6 категорій ПІСЛЯ фільтрації
        labels = [c for c, _ in counts[:6]]
        id_buckets = {code: [p.id for p in buckets.get(code, [])] for code in labels}
        
        # Конвертуємо коди в красиві назви
        pretty_labels: List[str] = []
        pretty_map: Dict[str, List[str]] = {}
        for code in labels:
            lbl = CATEGORY_SCHEMA.get(code, {}).get("label", code)
            pretty_labels.append(lbl)
            pretty_map[lbl] = id_buckets.get(code, [])
        logger.info(f"🏷️ _local_categorize: returning {len(pretty_labels)} categories: {pretty_labels}")
        return pretty_labels, pretty_map

# Search Context Manager
class SearchContextManager:
    def __init__(self):
        self.history: List[SearchHistoryItem] = []
        self.search_results: Dict[str, Dict[str, Any]] = {}

    def add_search(self, query: str, keywords: List[str], results_count: int) -> None:
        self.history.append(SearchHistoryItem(
            query=query, keywords=keywords, timestamp=time.time(), results_count=results_count
        ))
        if len(self.history) > settings.max_search_history:
            self.history = self.history[-settings.max_search_history:]

    def get_recent_history(self, limit: int = 5) -> List[SearchHistoryItem]:
        return self.history[-limit:]

    def clear_old_history(self) -> int:
        now = time.time()
        ttl = settings.search_history_ttl_days * 86400
        old_len = len(self.history)
        self.history = [h for h in self.history if now - h.timestamp < ttl]
        return old_len - len(self.history)
    
    def store_search_results(self, session_id: str, all_results: List[SearchResult], 
                           total_found: int, dialog_context: Dict[str, Any]) -> None:
        """Stores search results for later loading."""
        self.search_results[session_id] = {
            "all_results": [r.__dict__ for r in all_results],
            "total_found": total_found,
            "dialog_context": dialog_context,
            "timestamp": time.time()
        }
        # Periodic cleanup
        self.cleanup_old_results()
    
    def get_search_results(self, session_id: str, offset: int = 0, limit: int = 20) -> Dict[str, Any]:
        """Gets next batch of search results."""
        if session_id not in self.search_results:
            return {"products": [], "offset": 0, "has_more": False, "total_found": 0}
        
        stored = self.search_results[session_id]
        
        # Check for expiration
        if time.time() - stored["timestamp"] > settings.search_results_ttl_seconds:
            del self.search_results[session_id]
            return {"products": [], "offset": 0, "has_more": False, "total_found": 0}
        
        all_results = stored["all_results"]
        start_idx = offset
        end_idx = min(offset + limit, len(all_results))
        
        batch_results = all_results[start_idx:end_idx]
        has_more = end_idx < len(all_results)
        
        return {
            "products": batch_results,
            "offset": end_idx,
            "has_more": has_more,
            "total_found": stored["total_found"]
        }
    
    def clear_search_results(self, session_id: str) -> None:
        """Clears stored results for session."""
        if session_id in self.search_results:
            del self.search_results[session_id]
    
    def cleanup_old_results(self) -> int:
        """Cleans up expired search results."""
        now = time.time()
        ttl = settings.search_results_ttl_seconds
        old_sessions = [sid for sid, data in self.search_results.items() 
                       if now - data["timestamp"] > ttl]
        for sid in old_sessions:
            del self.search_results[sid]
        if old_sessions:
            logger.info(f"Cleaned up {len(old_sessions)} expired search sessions")
        return len(old_sessions)

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
    logger.info("Starting semantic search system")
    get_elasticsearch_client()
    get_http_client()
    get_embedding_cache()
    yield
    logger.info("Stopping service")
    if dependencies.http_client:
        await dependencies.http_client.aclose()
    if dependencies.es_client:
        await dependencies.es_client.close()

app = FastAPI(
    title="Semantic Search System (optimized)",
    description="Product search: GPT understands intent -> ES finds -> GPT explains choice. Optimized chat search logic.",
    version="1.6.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
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
    s = await es_service.get_index_stats()
    cache = get_embedding_cache()
    return HealthResponse(
        status="healthy",
        elasticsearch="connected",
        index=settings.index_name,
        documents_count=s.get("documents_count", 0),
        cache_size=len(cache),
        uptime_seconds=time.time() - app_start_time
    )

@app.get("/config")
async def get_frontend_config():
    try:
        return {
            "feature_chat_sse": True,  # Увімкнути SSE для чат-пошуку
        }
    except Exception as e:
        logger.warning(f"/config error: {e}")
        return {"feature_chat_sse": True}

@app.post("/search", response_model=SearchResponse)
async def search_products(
    request: SearchRequest,
    embedding_service: EmbeddingService = Depends(get_embedding_service),
    es_service: ElasticsearchService = Depends(get_elasticsearch_service)
):
    t0 = time.time()
    try:
        if not request.query.strip():
            raise HTTPException(status_code=400, detail="Query cannot be empty")

        mode = request.mode.lower().replace("semantic", "knn")
        q = request.query.strip()

        hits: List[Dict] = []
        candidates = max(request.k * 2, 100)

        if mode == "knn":
            v = await embedding_service.generate_embedding(q)
            if not v:
                logger.error("knn: Failed to generate embedding")
                raise HTTPException(
                    status_code=503,
                    detail="Embedding service unavailable. Please try again later."
                )
            hits = await es_service.semantic_search(v, candidates)
        elif mode == "bm25":
            hits = await es_service.bm25_search(q, candidates)
        elif mode == "hybrid":
            v = await embedding_service.generate_embedding(q)
            if not v:
                logger.error("hybrid: Failed to generate embedding")
                raise HTTPException(
                    status_code=503,
                    detail="Embedding service unavailable. Please try again later."
                )
            hits = await es_service.hybrid_search(v, q, q, candidates)
        else:
            raise HTTPException(status_code=400, detail=f"Unknown search mode: {request.mode}")

        min_score_threshold = settings.bm25_min_score if mode == "bm25" else request.min_score
        filtered_hits = [h for h in hits if float(h.get("_score", 0.0)) >= float(min_score_threshold)]
        results: List[SearchResult] = [SearchResult.from_hit(h) for h in filtered_hits[:request.k]]

        ms = (time.time() - t0) * 1000.0
        logger.info(f"/search '{q}' ({mode}) -> {len(results)} in {ms:.1f}ms")

        return SearchResponse(
            results=results,
            total_found=len(results),
            search_time_ms=ms,
            mode=request.mode
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"/search failed: {e}")
        ms = (time.time() - t0) * 1000.0
        return SearchResponse(results=[], total_found=0, search_time_ms=ms, mode=request.mode)

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
        uptime_seconds=time.time() - app_start_time
    )

@app.post("/api/ta-da/find.gcode")
async def ta_da_find_gcode(req: TadaFindRequest, http_client: httpx.AsyncClient = Depends(get_http_client)):
    """Server-side proxy to TA-DA API: hides token and unifies headers."""
    headers = {
        "Authorization": f"Bearer {settings.ta_da_api_token}" if settings.ta_da_api_token else "",
        "User-Language": (req.user_language or settings.ta_da_default_language),
        "Content-Type": "application/json"
    }
    payload = {"shop_id": req.shop_id or settings.ta_da_default_shop_id, "good_code": req.good_code}
    base = settings.ta_da_api_base_url.rstrip("/")
    url = f"{base}/find.gcode"
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
async def clear_cache(cache: TTLCache = Depends(get_embedding_cache)):
    try:
        await cache.clear()
        return {"message": "Cache cleared"}
    except Exception as e:
        logger.exception(f"/cache/clear failed: {e}")
        return JSONResponse(status_code=200, content={"message": "error suppressed", "error": str(e)})

@app.get("/cache/stats")
async def get_cache_stats(cache: TTLCache = Depends(get_embedding_cache)):
    try:
        expired = await cache.cleanup_expired()
        return {
            "size": len(cache),
            "capacity": cache.capacity,
            "ttl_seconds": cache.ttl_seconds,
            "expired_cleaned_now": expired
        }
    except Exception as e:
        logger.exception(f"/cache/stats failed: {e}")
        return {"size": len(cache), "capacity": cache.capacity, "ttl_seconds": cache.ttl_seconds, "error": str(e)}

@app.post("/chat/search", response_model=ChatSearchResponse)
async def chat_search(
    request: ChatSearchRequest,
    gpt_service: GPTService = Depends(get_gpt_service),
    embedding_service: EmbeddingService = Depends(get_embedding_service),
    es_service: ElasticsearchService = Depends(get_elasticsearch_service),
    context_manager: SearchContextManager = Depends(get_context_manager)
):
    """🎯 НОВИЙ СПРОЩЕНИЙ chat search з універсальним GPT асистентом."""
    t0 = time.time()
    try:
        query = request.query.strip()
        if not query:
            raise HTTPException(400, "Query cannot be empty")
        
        logger.info(f"💬 Chat search: '{query}'")
        
        # Базова валідація запиту (залишаємо для швидкості)
        is_valid, validation_error = _validate_query_basic(query)
        if not is_valid:
            logger.warning(f"⚠️ Базова валідація не пройдена: {validation_error}")
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
        
        # 🎯 НОВИЙ ПІДХІД: Один виклик unified_chat_assistant замість 3-4 різних функцій!
        assistant_response = await gpt_service.unified_chat_assistant(
            query=query,
            search_history=request.search_history or [],
            dialog_context=request.dialog_context
        )
        
        action = assistant_response["action"]
        logger.info(f"🤖 Assistant action: {action} (confidence: {assistant_response['confidence']:.2f})")
        
        # Обробка різних типів дій
        if action == "greeting":
            # Привітання/прощання/подяка
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
                needs_user_input=assistant_response["needs_user_input"]
            )
        
        elif action == "invalid":
            # Нерелевантний запит
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
                needs_user_input=assistant_response["needs_user_input"]
            )
        
        elif action == "clarification":
            # Потребує уточнення - показуємо категорії БЕЗ товарів
            ms = (time.time() - t0) * 1000.0
            categories = assistant_response.get("categories", [])
            
            # Створюємо action buttons з категоріями
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
                needs_user_input=assistant_response["needs_user_input"],
                actions=actions
            )
        
        # action == "product_search" - шукаємо товари
        # 🚀 ОПТИМІЗАЦІЯ: використовуємо semantic_subqueries з відповіді GPT (не треба робити ще один виклик!)
        semantic_subqueries = assistant_response.get("semantic_subqueries", [query])
        if not semantic_subqueries:
            semantic_subqueries = [query]
        
        logger.info(f"🔍 Semantic subqueries ({len(semantic_subqueries)}): {semantic_subqueries}")
        
        # Generate embeddings for subqueries (with concurrency limit)
        embeddings = await embedding_service.generate_embeddings_parallel(
            semantic_subqueries,
            max_concurrent=settings.embedding_max_concurrent
        )
        valid_queries = [(sq, emb) for sq, emb in zip(semantic_subqueries, embeddings) if emb is not None]
        
        if not valid_queries:
            # Не вдалося згенерувати жодного ембедінгу - повертаємо помилку
            logger.error(f"❌ Failed to generate embeddings for query: '{query}'")
            raise HTTPException(
                status_code=503,
                detail="Embedding service unavailable. Please try again later."
            )
        
        # Parallel semantic search - зменшуємо кількість на підзапит для кращої релевантності
        k_per_subquery = min(settings.chat_search_max_k_per_subquery, max(10, 50 // len(valid_queries)))
        logger.info(f"🔍 Пошук: {len(valid_queries)} підзапитів × {k_per_subquery} товарів")
        
        search_results = await es_service.multi_semantic_search(valid_queries, k_per_subquery)
        
        # Об'єднуємо результати зі зваженими скорами
        all_hits_dict = {}
        for idx, (subquery, hits) in enumerate(search_results.items()):
            # Перший підзапит найважливіший - даємо йому більшу вагу
            weight = 1.0 if idx == 0 else settings.chat_search_subquery_weight_decay ** idx
            
            for hit in hits:
                product_id = hit["_id"]
                base_score = float(hit.get("_score", 0.0))
                weighted_score = base_score * weight
                
                if product_id not in all_hits_dict:
                    all_hits_dict[product_id] = hit.copy()
                    all_hits_dict[product_id]["_score"] = weighted_score
                    all_hits_dict[product_id]["_subquery_match"] = subquery
                else:
                    # Якщо товар знайдений в кількох підзапитах - підсилюємо його скор
                    current_score = float(all_hits_dict[product_id].get("_score", 0.0))
                    all_hits_dict[product_id]["_score"] = max(current_score, weighted_score) + 0.1
        
        all_hits = sorted(all_hits_dict.values(), key=lambda x: float(x.get("_score", 0.0)), reverse=True)
        
        # Адаптивний threshold для кращої релевантності
        max_score = max([float(h.get("_score", 0.0)) for h in all_hits], default=0.0)
        dynamic_threshold = settings.chat_search_score_threshold_ratio * max_score if max_score > 0 else 0.0
        
        # Адаптивний мінімальний поріг залежно від кількості результатів
        if len(all_hits) < 10:
            # Якщо мало результатів - знижуємо поріг на 30%
            adaptive_min = settings.chat_search_min_score_absolute * 0.7
            logger.info(f"🔽 Мало результатів ({len(all_hits)}), знижую поріг до {adaptive_min:.2f}")
        elif len(all_hits) < 30:
            # Середня кількість - знижуємо на 15%
            adaptive_min = settings.chat_search_min_score_absolute * 0.85
            logger.info(f"📉 Середня кількість ({len(all_hits)}), адаптую поріг до {adaptive_min:.2f}")
        else:
            # Багато результатів - використовуємо стандартний поріг
            adaptive_min = settings.chat_search_min_score_absolute
        
        min_score_threshold = max(adaptive_min, dynamic_threshold) if max_score > 0 else 0.0
        
        logger.info(f"📊 Фільтрація: max_score={max_score:.2f}, dynamic={dynamic_threshold:.2f}, adaptive_min={adaptive_min:.2f}, final_threshold={min_score_threshold:.2f}")
        candidate_results = [SearchResult.from_hit(h) for h in all_hits if float(h.get("_score", 0.0)) >= min_score_threshold]
        logger.info(f"✅ Після адаптивної фільтрації: {len(candidate_results)} релевантних товарів з {len(all_hits)} знайдених")
        
        # Categorize products
        labels: List[str] = []
        id_buckets: Dict[str, List[str]] = {}
        try:
            labels, id_buckets = await gpt_service.categorize_products(candidate_results[:30], query, timeout_seconds=15.0)
            logger.info(f"🏷️ POST /chat/search: Categorization succeeded: {len(labels)} categories")
            logger.info(f"🏷️ POST /chat/search: Category labels: {labels}")
        except Exception as e:
            logger.error(f"❌ POST /chat/search: Categorization failed: {e}", exc_info=True)
            labels, id_buckets = [], {}
        
        # Get recommendations (зменшено до 20 для швидкості GPT)
        recommendations, assistant_message = await gpt_service.analyze_products(candidate_results[:20], query)
        
        # Final results
        sorted_candidates = sorted(candidate_results, key=lambda r: r.score, reverse=True)
        candidate_map = {r.id: r for r in sorted_candidates}
        reco_ids = [rec.product_id for rec in recommendations if rec.product_id in candidate_map]
        ordered_from_reco = [candidate_map[rid] for rid in reco_ids]
        remaining = [r for r in sorted_candidates if r.id not in set(reco_ids)]
        
        max_display = min(request.k, settings.max_chat_display_items)
        final_results = (ordered_from_reco + remaining)[:max_display]
        
        # Додаємо спеціальну категорію "Рекомендовано" з GPT товарами
        if reco_ids:
            id_buckets["⭐ Рекомендовано для вас"] = reco_ids  # ВСІ рекомендації GPT
            if "⭐ Рекомендовано для вас" not in labels:
                labels.insert(0, "⭐ Рекомендовано для вас")  # Додаємо на перше місце
        
        # Create category action buttons
        actions = None
        if labels:
            actions = []
            for label in labels[:10]:
                button = {
                    "type": "button",
                    "action": "select_category",
                    "value": label,
                    "label": label
                }
                # Позначаємо рекомендовану категорію як особливу
                if label == "⭐ Рекомендовано для вас":
                    button["special"] = "recommended"
                actions.append(button)
            logger.info(f"✅ POST /chat/search: Created {len(actions)} category action buttons")
        else:
            logger.warning(f"⚠️ POST /chat/search: No category labels found, actions will be None")
        
        # Store for lazy loading
        context_manager.store_search_results(
            session_id=request.session_id,
            all_results=ordered_from_reco + remaining,
            total_found=len(candidate_results),
            dialog_context=None
        )
        
        ms = (time.time() - t0) * 1000.0
        logger.info(f"Chat search completed: {len(final_results)} products, {ms:.1f}ms")
        
        # Створюємо QueryAnalysis з даних assistant_response
        keywords = [w for w in query.split() if len(w) > 2][:5]
        query_analysis = QueryAnalysis(
            original_query=query,
            expanded_query=query,
            keywords=keywords,
            context_used=bool(request.search_history),
            intent="product_search",
            semantic_subqueries=semantic_subqueries
        )
        
        context_manager.add_search(query=query, keywords=keywords, results_count=len(final_results))
        
        # Створюємо dialog_context з категоріями для фільтрації на клієнті
        dialog_ctx = {
            "original_query": query,
            "available_categories": labels,
            "category_buckets": id_buckets,
            "current_filter": None
        }
        
        # Логуємо результати пошуку для аналізу
        try:
            top_products_for_log = [
                {
                    "id": p.id,
                    "name": p.title_ua or p.title_ru or p.id,
                    "score": round(float(p.score), 4),
                    "recommended": p.id in set(reco_ids)
                }
                for p in final_results[:20]  # Топ-20 товарів
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
                top_products=top_products_for_log,
                search_time_ms=ms,
                intent="product_search",
                additional_info={
                    "categories": labels,
                    "recommendations_count": len(recommendations),
                    "total_display": len(final_results),
                    "k_per_subquery": k_per_subquery,
                    "assistant_confidence": assistant_response['confidence']
                }
            )
        except Exception as log_error:
            logger.warning(f"⚠️ Failed to log search query: {log_error}")
        
        return ChatSearchResponse(
            query_analysis=query_analysis,
            results=final_results,
            recommendations=recommendations,
            search_time_ms=ms,
            context_used=query_analysis.context_used,
            assistant_message=assistant_message or assistant_response["assistant_message"] or "Ось підібрані товари за вашим запитом.",
            dialog_state="final_results",
            dialog_context=dialog_ctx,
            needs_user_input=False,
            actions=actions,
            stage_timings_ms={"total": ms}
        )
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

@app.post("/chat/search/load-more")
async def load_more_products(
    request: LoadMoreRequest,
    context_manager: SearchContextManager = Depends(get_context_manager)
):
    """Load next batch of products without repeating search."""
    try:
        logger.info(f"Load more: session={request.session_id}, offset={request.offset}, limit={request.limit}")
        
        result = context_manager.get_search_results(
            session_id=request.session_id,
            offset=request.offset,
            limit=request.limit
        )
        
        if not result["products"]:
            logger.warning(f"No saved results for session {request.session_id}")
            return {
                "products": [],
                "offset": request.offset,
                "has_more": False,
                "total_found": 0,
                "error": "No saved search results"
            }
        
        logger.info(f"Load more: returned {len(result['products'])} products, has_more={result['has_more']}")
        
        return {
            "products": result["products"],
            "offset": result["offset"],
            "has_more": result["has_more"],
            "total_found": result["total_found"]
        }
        
    except Exception as e:
        logger.exception(f"/chat/search/load-more failed: {e}")
        return {
            "products": [],
            "offset": request.offset,
            "has_more": False,
            "total_found": 0,
            "error": str(e)
        }

@app.get("/api/image-proxy")
async def image_proxy(
    url: str,
    http_client: httpx.AsyncClient = Depends(get_http_client)
):
    """Proxy for product images with caching."""
    try:
        # Check that URL is actually from ta-da.net.ua
        if "ta-da.net.ua" not in url:
            raise HTTPException(400, "Invalid image URL")
        
        logger.info(f"Image proxy: {url}")
        
        response = await http_client.get(url, timeout=10.0)
        response.raise_for_status()
        
        return Response(
            content=response.content,
            media_type=response.headers.get("content-type", "image/png"),
            headers={
                "Cache-Control": "public, max-age=86400",  # Cache for 24 hours
                "Access-Control-Allow-Origin": "*"
            }
        )
    except Exception as e:
        logger.warning(f"Image proxy error for {url}: {e}")
        raise HTTPException(404, "Image not found")

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
    es_service: ElasticsearchService = Depends(get_elasticsearch_service)
):
    """SSE stream for chat search."""
    async def event_generator():
        def sse_event(event: str, data: Dict[str, Any]) -> str:
            return f"event: {event}\n" + "data: " + json.dumps(data, ensure_ascii=False) + "\n\n"

        t0 = time.time()
        try:
            query_stripped = query.strip()
            
            dialog_context: Optional[Dict[str, Any]] = None
            if dialog_context_b64:
                try:
                    import base64
                    decoded = base64.urlsafe_b64decode(dialog_context_b64.encode("utf-8")).decode("utf-8")
                    dialog_context = json.loads(decoded)
                except Exception:
                    dialog_context = None
            
            # Базова валідація запиту
            is_valid, validation_error = _validate_query_basic(query_stripped)
            if not is_valid:
                logger.warning(f"⚠️ SSE: Базова валідація не пройдена: {validation_error}")
                yield sse_event("assistant_start", {"length": len(validation_error)})
                for char in validation_error:
                    yield sse_event("assistant_delta", {"text": char})
                    await asyncio.sleep(0.02)
                yield sse_event("assistant_end", {})
                
                # Відправляємо порожній результат
                ms = (time.time() - t0) * 1000.0
                empty_qa = QueryAnalysis(
                    original_query=query_stripped,
                    expanded_query=query_stripped,
                    keywords=[],
                    context_used=False,
                    intent="invalid"
                )
                payload = ChatSearchResponse(
                    query_analysis=empty_qa,
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
            
            # 🎯 НОВИЙ ПІДХІД SSE: Один виклик unified_chat_assistant
            # Показуємо статус "Думаю..."
            thinking_message = "Думаю..."
            yield sse_event("status", {"message": thinking_message, "type": "thinking"})
            
            # Витягуємо search_history з окремого параметра search_history_b64
            search_history = []
            if search_history_b64:
                try:
                    import base64
                    history_json = base64.b64decode(search_history_b64).decode('utf-8')
                    history_items = json.loads(history_json)
                    logger.info(f"📜 SSE: Отримано history_items: {history_items}")
                    if isinstance(history_items, list):
                        # Перетворюємо з формату {query, timestamp} в SearchHistoryItem
                        for item in history_items:
                            if isinstance(item, dict) and "query" in item:
                                try:
                                    search_history.append(
                                        SearchHistoryItem(
                                            query=item.get("query", ""),
                                            timestamp=item.get("timestamp", "")
                                        )
                                    )
                                except Exception as e:
                                    logger.warning(f"⚠️ Не вдалось розпарсити history item {item}: {e}")
                        logger.info(f"📜 SSE: Завантажено історію: {len(search_history)} запитів")
                        if search_history:
                            logger.info(f"📜 SSE: Останні запити: {[h.query for h in search_history]}")
                except Exception as e:
                    logger.error(f"❌ SSE: Помилка при обробці search_history_b64: {e}", exc_info=True)
                    search_history = []
            
            # Викликаємо unified_chat_assistant БЕЗ fallback - хай падає якщо є помилка!
            logger.info(f"🔍 SSE: Викликаємо unified_chat_assistant з історією: {len(search_history)} запитів")
            assistant_response = await gpt_service.unified_chat_assistant(
                query=query_stripped,
                search_history=search_history,
                dialog_context=dialog_context
            )
            logger.info(f"✅ SSE: unified_chat_assistant відповів успішно")
            
            action = assistant_response["action"]
            response_text = assistant_response["assistant_message"]
            logger.info(f"🤖 SSE Assistant: {action} (confidence: {assistant_response['confidence']:.2f})")
            
            # Обробка greeting
            if action == "greeting":
                # Виводимо відповідь символ за символом
                yield sse_event("assistant_start", {"length": len(response_text)})
                for char in response_text:
                    yield sse_event("assistant_delta", {"text": char})
                    await asyncio.sleep(0.015)
                yield sse_event("assistant_end", {})
                
                # Відправляємо результат
                ms = (time.time() - t0) * 1000.0
                qa = QueryAnalysis(
                    original_query=query_stripped,
                    expanded_query=query_stripped,
                    keywords=[],
                    context_used=False,
                    intent="greeting"
                )
                payload = ChatSearchResponse(
                    query_analysis=qa,
                    results=[],
                    recommendations=[],
                    search_time_ms=ms,
                    context_used=False,
                    assistant_message=response_text,
                    dialog_state="greeting",
                    dialog_context=None,
                    needs_user_input=assistant_response["needs_user_input"]
                ).model_dump()
                yield sse_event("final", payload)
                return
            
            # Обробка invalid запитів
            if action == "invalid":
                logger.warning(f"⚠️ SSE: Invalid query: {query_stripped}")
                
                yield sse_event("assistant_start", {"length": len(response_text)})
                for char in response_text:
                    yield sse_event("assistant_delta", {"text": char})
                    await asyncio.sleep(0.02)
                yield sse_event("assistant_end", {})
                
                ms = (time.time() - t0) * 1000.0
                empty_qa = QueryAnalysis(
                    original_query=query_stripped,
                    expanded_query=query_stripped,
                    keywords=[],
                    context_used=False,
                    intent="invalid"
                )
                payload = ChatSearchResponse(
                    query_analysis=empty_qa,
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
            
            # Обробка clarification запитів (БЕЗ пошуку товарів)
            if action == "clarification":
                logger.info(f"💬 SSE: Clarification needed for: {query_stripped}")
                categories = assistant_response.get("categories", [])
                
                yield sse_event("assistant_start", {"length": len(response_text)})
                for char in response_text:
                    yield sse_event("assistant_delta", {"text": char})
                    await asyncio.sleep(0.02)
                yield sse_event("assistant_end", {})
                
                ms = (time.time() - t0) * 1000.0
                empty_qa = QueryAnalysis(
                    original_query=query_stripped,
                    expanded_query=query_stripped,
                    keywords=[],
                    context_used=False,
                    intent="clarification"
                )
                
                # Створюємо action buttons
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
                    query_analysis=empty_qa,
                    results=[],  # НЕ показуємо товари
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

            # action == "product_search" - продовжуємо звичайний пошук
            # 🚀 ОПТИМІЗАЦІЯ: використовуємо semantic_subqueries з відповіді GPT
            semantic_subqueries = assistant_response.get("semantic_subqueries", [query_stripped])
            if not semantic_subqueries:
                semantic_subqueries = [query_stripped]
            
            logger.info(f"🔍 SSE: {len(semantic_subqueries)} subqueries: {semantic_subqueries}")
            
            # Показуємо статус "Шукаю товари..."
            searching_message = "Шукаю товари..."
            yield sse_event("status", {"message": searching_message, "type": "searching"})
            
            # Створюємо QueryAnalysis
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

            # Генеруємо embeddings для всіх підзапитів паралельно (з обмеженням)
            t_embed_start = time.time()
            embeddings = await embedding_service.generate_embeddings_parallel(
                semantic_subqueries,
                max_concurrent=settings.embedding_max_concurrent
            )
            embedding_time = (time.time() - t_embed_start) * 1000.0
            
            valid_queries = [(sq, emb) for sq, emb in zip(semantic_subqueries, embeddings) if emb is not None]
            
            if not valid_queries:
                # Не вдалося згенерувати жодного ембедінгу - повертаємо помилку через SSE
                logger.error(f"❌ SSE: Failed to generate embeddings for query: '{query}'")
                yield sse_event("error", {
                    "error": "Embedding service unavailable",
                    "message": "Не вдалося згенерувати ембедінги. Спробуйте ще раз пізніше."
                })
                return
            
            logger.info(f"SSE: Generated {len(valid_queries)}/{len(qa.semantic_subqueries)} embeddings for parallel search")
            
            # Логуємо підзапити для діагностики
            for i, (sq, _) in enumerate(valid_queries):
                logger.info(f"🔍 SSE підзапит #{i+1}: '{sq}'")
            
            # Паралельний пошук по всіх підзапитах - адаптивна кількість
            k_per_subquery = min(settings.chat_search_max_k_per_subquery, max(10, 50 // len(valid_queries)))
            logger.info(f"🔍 SSE пошук: {len(valid_queries)} підзапитів × {k_per_subquery} товарів")
            
            search_results = await es_service.multi_semantic_search(valid_queries, k_per_subquery)
            
            # Об'єднуємо результати зі зваженими скорами
            all_hits_dict: Dict[str, Dict] = {}
            subquery_mapping: Dict[str, str] = {}
            
            for idx, (subquery, hits) in enumerate(search_results.items()):
                # Перший підзапит найважливіший - даємо йому більшу вагу
                weight = 1.0 if idx == 0 else settings.chat_search_subquery_weight_decay ** idx
                logger.info(f"📦 SSE підзапит '{subquery[:30]}...': знайдено {len(hits)} товарів, вага={weight:.2f}")
                
                for hit in hits:
                    product_id = hit["_id"]
                    base_score = float(hit.get("_score", 0.0))
                    weighted_score = base_score * weight
                    
                    if product_id not in all_hits_dict:
                        all_hits_dict[product_id] = hit.copy()
                        all_hits_dict[product_id]["_score"] = weighted_score
                        subquery_mapping[product_id] = subquery
                    else:
                        # Якщо товар знайдений в кількох підзапитах - підсилюємо його скор
                        current_score = float(all_hits_dict[product_id].get("_score", 0.0))
                        all_hits_dict[product_id]["_score"] = max(current_score, weighted_score) + 0.1
            
            all_hits = sorted(all_hits_dict.values(), key=lambda x: float(x.get("_score", 0.0)), reverse=True)
            logger.info(f"SSE: Merged {len(all_hits)} unique products from {len(search_results)} subqueries")
            
            # Адаптивний threshold для кращої релевантності (SSE)
            max_score = max([float(h.get("_score", 0.0)) for h in all_hits], default=0.0)
            dynamic_threshold = settings.chat_search_score_threshold_ratio * max_score if max_score > 0 else 0.0
            
            # Адаптивний мінімальний поріг залежно від кількості результатів
            if len(all_hits) < 10:
                # Якщо мало результатів - знижуємо поріг на 30%
                adaptive_min = settings.chat_search_min_score_absolute * 0.7
                logger.info(f"🔽 SSE: Мало результатів ({len(all_hits)}), знижую поріг до {adaptive_min:.2f}")
            elif len(all_hits) < 30:
                # Середня кількість - знижуємо на 15%
                adaptive_min = settings.chat_search_min_score_absolute * 0.85
                logger.info(f"📉 SSE: Середня кількість ({len(all_hits)}), адаптую поріг до {adaptive_min:.2f}")
            else:
                # Багато результатів - використовуємо стандартний поріг
                adaptive_min = settings.chat_search_min_score_absolute
            
            min_score_threshold = max(adaptive_min, dynamic_threshold) if max_score > 0 else 0.0
            
            logger.info(f"📊 SSE фільтрація: max_score={max_score:.2f}, dynamic={dynamic_threshold:.2f}, adaptive_min={adaptive_min:.2f}, final={min_score_threshold:.2f}")
            candidate_results = [SearchResult.from_hit(h) for h in all_hits if float(h.get("_score", 0.0)) >= min_score_threshold]
            
            logger.info(f"✅ SSE: Після адаптивної фільтрації {len(candidate_results)} товарів з {len(all_hits)} знайдених")
            yield sse_event("candidates", {"count": len(candidate_results)})

            labels: List[str] = []
            id_buckets: Dict[str, List[str]] = {}
            try:
                labels, id_buckets = await gpt_service.categorize_products(candidate_results[:30], query, timeout_seconds=15.0)
                logger.info(f"🏷️ Categorization succeeded: {len(labels)} categories, {len(id_buckets)} buckets")
                logger.info(f"🏷️ Category labels: {labels}")
            except Exception as e:
                logger.error(f"❌ Categorization failed: {e}", exc_info=True)
                labels, id_buckets = [], {}

            recommendations: List[ProductRecommendation] = []
            assistant_message: str = ""
            try:
                # Зменшено до 20 для швидкості GPT
                recommendations, assistant_message = await gpt_service.analyze_products(candidate_results[:20], query)
            except Exception:
                recommendations, assistant_message = [], "Ось підібрані товари за вашим запитом."
            
            # Додаємо спеціальну категорію "Рекомендовано" з GPT товарами
            reco_ids_list = [rec.product_id for rec in recommendations]
            if reco_ids_list:
                id_buckets["⭐ Рекомендовано для вас"] = reco_ids_list  # ВСІ рекомендації GPT
                if "⭐ Рекомендовано для вас" not in labels:
                    labels.insert(0, "⭐ Рекомендовано для вас")
            
            yield sse_event("categories", {"labels": labels})
            yield sse_event("recommendations", {
                "count": len(recommendations),
                "assistant_message": assistant_message
            })

            # Відправляємо текст асистента посимвольно для ефекту друку
            try:
                typed = assistant_message or "Я підібрав для вас добірку товарів."
                yield sse_event("assistant_start", {"length": len(typed)})
                
                # Відправляємо по 1 символу для плавної анімації
                for char in typed:
                    yield sse_event("assistant_delta", {"text": char})
                    await asyncio.sleep(0.02)  # 20мс між символами
                
                yield sse_event("assistant_end", {})
            except Exception:
                pass

            sorted_candidates = sorted(candidate_results, key=lambda r: float(getattr(r, 'score', 0.0)), reverse=True)
            candidate_map = {r.id: r for r in sorted_candidates}
            reco_ids_in_order: List[str] = [rec.product_id for rec in recommendations if rec.product_id in candidate_map] if recommendations else []
            ordered_from_reco: List[SearchResult] = [candidate_map[rid] for rid in reco_ids_in_order]
            remaining: List[SearchResult] = [r for r in sorted_candidates if r.id not in set(reco_ids_in_order)]
            max_display_items = min(k, settings.max_chat_display_items)
            final_results = (ordered_from_reco + remaining)[:max_display_items]

            actions = None
            if labels:
                actions = []
                for label in labels[:10]:
                    button = {
                        "type": "button",
                        "action": "select_category",
                        "value": label,
                        "label": label
                    }
                    # Позначаємо рекомендовану категорію як особливу
                    if label == "⭐ Рекомендовано для вас":
                        button["special"] = "recommended"
                    actions.append(button)
                logger.info(f"✅ Created {len(actions)} category action buttons")
            else:
                logger.warning(f"⚠️ No category labels found, actions will be None")

            ms = (time.time() - t0) * 1000.0
            
            # Створюємо dialog_context з категоріями для фільтрації на клієнті
            dialog_ctx = {
                "original_query": query,
                "available_categories": labels,
                "category_buckets": id_buckets,
                "current_filter": None
            }
            
            # Логуємо результати SSE пошуку для аналізу
            try:
                top_products_for_log = [
                    {
                        "id": p.id,
                        "name": p.title_ua or p.title_ru or p.id,
                        "score": round(float(p.score), 4),
                        "recommended": p.id in set(reco_ids_in_order)
                    }
                    for p in final_results[:20]  # Топ-20 товарів
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
                    top_products=top_products_for_log,
                    search_time_ms=ms,
                    intent="product_search",
                    additional_info={
                        "assistant_confidence": assistant_response['confidence'],
                        "categories": labels,
                        "recommendations_count": len(recommendations),
                        "total_display": len(final_results),
                        "k_per_subquery": k_per_subquery,
                        "method": "SSE"
                    }
                )
            except Exception as log_error:
                logger.warning(f"⚠️ SSE: Failed to log search query: {log_error}")
            
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
                stage_timings_ms={"total": ms, "embedding_generation": embedding_time}
            ).model_dump()
            yield sse_event("final", payload)
        except Exception as e:
            logger.error(f"SSE chat search error: {e}", exc_info=True)
            yield sse_event("error", {"message": f"Вибачте, виникла помилка: {str(e)}"})

    return StreamingResponse(event_generator(), media_type="text/event-stream")


# ========================================
# API для роботи з логами пошуку
# ========================================

@app.get("/search-logs/sessions")
async def get_search_log_sessions():
    """
    Повертає список всіх сесій з логами.
    """
    try:
        sessions = search_logger.get_all_sessions()
        return {
            "total": len(sessions),
            "sessions": sessions
        }
    except Exception as e:
        logger.error(f"Failed to get search log sessions: {e}")
        raise HTTPException(500, f"Failed to get sessions: {str(e)}")


@app.get("/search-logs/session/{session_id}")
async def get_session_logs(session_id: str):
    """
    Повертає всі логи для конкретної сесії.
    """
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
        raise HTTPException(500, f"Failed to get session logs: {str(e)}")


@app.get("/search-logs/report/{session_id}")
async def get_session_report(session_id: str):
    """
    Генерує аналітичний звіт по сесії.
    """
    try:
        report = search_logger.generate_session_report(session_id)
        if "error" in report:
            raise HTTPException(404, report["error"])
        
        return report
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to generate session report: {e}")
        raise HTTPException(500, f"Failed to generate report: {str(e)}")


@app.get("/search-logs/export")
async def export_all_sessions():
    """
    Експортує звіти по всіх сесіях в JSON файл.
    Повертає шлях до файлу.
    """
    try:
        output_path = search_logger.export_all_sessions_report()
        return {
            "success": True,
            "file_path": output_path,
            "message": f"Report exported to {output_path}"
        }
    except Exception as e:
        logger.error(f"Failed to export sessions: {e}")
        raise HTTPException(500, f"Failed to export: {str(e)}")


@app.get("/search-logs/stats")
async def get_search_logs_stats():
    """
    Повертає загальну статистику по всіх логах.
    """
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
        logger.error(f"Failed to get search logs stats: {e}")
        raise HTTPException(500, f"Failed to get stats: {str(e)}")


# RUN
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)