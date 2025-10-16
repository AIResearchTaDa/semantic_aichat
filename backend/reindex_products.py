#!/usr/bin/env python3
"""
Reindex products with proper description_vector including ALL important fields.

The description_vector will now include:
1. title_ua + title_ru (MOST IMPORTANT - product names)
2. description_ua + description_ru (detailed information)
3. sku + good_code (product codes for exact matching)

This ensures semantic search works for product names, not just descriptions!
"""

import asyncio
import json
import time
import logging
import sys
from typing import List, Optional, Dict, Any
import httpx
from elasticsearch import AsyncElasticsearch
from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Logging to both console and file
log_file = "/app/indexing.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("reindex")
load_dotenv()

# Settings
class Settings(BaseSettings):
    elastic_url: str = Field(default="http://localhost:9200", env="ELASTIC_URL")
    elastic_user: str = Field(default="elastic", env="ELASTIC_USER")
    elastic_password: str = Field(default="elastic", env="ELASTIC_PASSWORD")
    embedding_api_url: str = Field(default="http://10.2.0.171:9001/api/embeddings", env="EMBEDDING_API_URL")
    ollama_model_name: str = Field(default="dengcao/Qwen3-Embedding-8B:Q8_0", env="OLLAMA_MODEL_NAME")
    index_name: str = Field(default="products_qwen3_8b", env="INDEX_NAME")
    vector_dimension: int = Field(default=4096, env="VECTOR_DIMENSION")
    request_timeout: int = Field(default=30, env="REQUEST_TIMEOUT")
    batch_size: int = Field(default=20, env="BATCH_SIZE")
    products_file: str = Field(default="/app/products.json", env="PRODUCTS_FILE")
    
    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
        extra="ignore"
    )

settings = Settings()


def combine_product_text_for_embedding(product: Dict[str, Any]) -> str:
    """
    Combine ALL important text fields for semantic search.
    
    Priority:
    1. TITLES (most important - users search by names!)
    2. DESCRIPTIONS (detailed product info)
    3. CODES (SKU, good_code for exact matches)
    """
    parts = []
    
    # 1. TITLES - HIGHEST PRIORITY
    title_ua = (product.get("title_ua") or "").strip()
    title_ru = (product.get("title_ru") or "").strip()
    
    if title_ua:
        parts.append(f"Назва: {title_ua}")
    if title_ru and title_ru != title_ua:
        parts.append(f"Название: {title_ru}")
    
    # 2. DESCRIPTIONS
    desc_ua = (product.get("description_ua") or "").strip()
    desc_ru = (product.get("description_ru") or "").strip()
    
    if desc_ua:
        # Limit description length to avoid token limits
        parts.append(desc_ua[:500])
    if desc_ru and desc_ru != desc_ua:
        parts.append(desc_ru[:500])
    
    # 3. PRODUCT CODES (for exact matching)
    sku = (product.get("sku") or "").strip()
    good_code = (product.get("good_code") or "").strip()
    
    if sku:
        parts.append(f"Артикул: {sku}")
    if good_code:
        parts.append(f"Код: {good_code}")
    
    # Combine with clear separation
    combined = " | ".join(parts)
    
    # Ensure we don't exceed reasonable length (~2000 chars)
    if len(combined) > 2000:
        combined = combined[:2000]
    
    return combined


async def generate_embedding(http_client: httpx.AsyncClient, text: str, retry: int = 0) -> Optional[List[float]]:
    """Generate embedding with retry logic"""
    if not text or not text.strip():
        return None
    
    try:
        payload = {
            "model": settings.ollama_model_name,
            "prompt": text.strip()
        }
        
        response = await http_client.post(
            settings.embedding_api_url,
            json=payload,
            timeout=settings.request_timeout
        )
        response.raise_for_status()
        
        data = response.json()
        embedding = data.get("embedding")
        
        if isinstance(embedding, list) and len(embedding) == settings.vector_dimension:
            return embedding
        else:
            logger.warning(f"Invalid embedding dimension: expected {settings.vector_dimension}, got {len(embedding) if embedding else 0}")
            return None
            
    except Exception as e:
        if retry < 2:
            logger.warning(f"Embedding error (retry {retry+1}/3): {e}")
            await asyncio.sleep(1)
            return await generate_embedding(http_client, text, retry + 1)
        else:
            logger.error(f"Embedding failed after 3 retries: {e}")
            return None


async def load_products() -> List[Dict[str, Any]]:
    """Load products from JSON file"""
    logger.info(f"Loading products from {settings.products_file}...")
    
    products = []
    try:
        with open(settings.products_file, 'r', encoding='utf-8') as f:
            # Skip header lines
            for line_num, line in enumerate(f, 1):
                if line_num <= 5:  # Skip first 5 lines (header)
                    continue
                
                line = line.strip()
                if not line or line == ']':
                    continue
                
                # Remove trailing comma if present
                if line.endswith(','):
                    line = line[:-1]
                
                try:
                    product = json.loads(line)
                    if product.get("uuid"):
                        products.append(product)
                except json.JSONDecodeError as e:
                    logger.warning(f"Failed to parse line {line_num}: {e}")
                    continue
        
        logger.info(f"✓ Loaded {len(products)} products")
        return products
        
    except Exception as e:
        logger.error(f"Failed to load products: {e}")
        return []


async def reindex_products():
    """Main reindexing function"""
    start_time = time.time()
    
    logger.info("="*80)
    logger.info("REINDEXING PRODUCTS WITH IMPROVED description_vector")
    logger.info("="*80)
    logger.info(f"Index: {settings.index_name}")
    logger.info(f"Embedding API: {settings.embedding_api_url}")
    logger.info(f"Model: {settings.ollama_model_name}")
    logger.info(f"Vector dimension: {settings.vector_dimension}")
    logger.info(f"Batch size: {settings.batch_size}")
    logger.info("="*80)
    
    # Initialize clients
    es = AsyncElasticsearch(
        [settings.elastic_url],
        basic_auth=(settings.elastic_user, settings.elastic_password)
    )
    http_client = httpx.AsyncClient(timeout=60.0)
    
    try:
        # Check index exists
        if not await es.indices.exists(index=settings.index_name):
            logger.error(f"Index {settings.index_name} does not exist!")
            return
        
        logger.info(f"✓ Index {settings.index_name} exists")
        
        # Load products
        products = await load_products()
        if not products:
            logger.error("No products loaded, aborting")
            return
        
        total_products = len(products)
        logger.info(f"Total products to reindex: {total_products}")
        logger.info("")
        
        # Process in batches
        processed = 0
        skipped = 0
        errors = 0
        batch_num = 0
        
        for i in range(0, total_products, settings.batch_size):
            batch_num += 1
            batch = products[i:i + settings.batch_size]
            batch_start = time.time()
            
            logger.info(f"=== Batch {batch_num}/{(total_products + settings.batch_size - 1) // settings.batch_size} ({len(batch)} products) ===")
            
            bulk_operations = []
            
            for product in batch:
                product_id = product.get("uuid")
                if not product_id:
                    skipped += 1
                    continue
                
                # Combine text from ALL important fields
                combined_text = combine_product_text_for_embedding(product)
                
                if not combined_text:
                    logger.warning(f"Product {product_id}: no text to index")
                    skipped += 1
                    continue
                
                # Show what we're indexing (first 3 products + every 100th)
                if processed < 3 or processed % 100 == 0:
                    logger.info(f"Product {product_id}:")
                    logger.info(f"  title_ua: {(product.get('title_ua') or 'N/A')[:60]}")
                    logger.info(f"  title_ru: {(product.get('title_ru') or 'N/A')[:60]}")
                    logger.info(f"  sku: {product.get('sku') or 'N/A'}")
                    logger.info(f"  good_code: {product.get('good_code') or 'N/A'}")
                    logger.info(f"  Combined text length: {len(combined_text)} chars")
                
                # Generate embedding
                embedding = await generate_embedding(http_client, combined_text)
                
                if embedding:
                    # Prepare bulk update
                    bulk_operations.append({
                        "update": {
                            "_index": settings.index_name,
                            "_id": product_id
                        }
                    })
                    bulk_operations.append({
                        "doc": {
                            "description_vector": embedding
                        }
                    })
                    processed += 1
                else:
                    errors += 1
                    logger.warning(f"Failed to generate embedding for {product_id}")
            
            # Execute bulk update
            if bulk_operations:
                try:
                    response = await es.bulk(operations=bulk_operations, refresh=False)
                    
                    # Check for errors in bulk response
                    if response.get("errors"):
                        error_count = sum(1 for item in response.get("items", []) 
                                        if item.get("update", {}).get("error"))
                        logger.warning(f"Bulk update had {error_count} errors")
                        errors += error_count
                    
                    batch_time = time.time() - batch_start
                    logger.info(f"✓ Batch {batch_num} completed in {batch_time:.2f}s")
                    logger.info(f"Progress: {processed}/{total_products} ({processed/total_products*100:.1f}%)")
                    
                    # Show estimated time remaining
                    avg_time_per_product = (time.time() - start_time) / processed if processed > 0 else 0
                    remaining_products = total_products - processed
                    eta_seconds = avg_time_per_product * remaining_products
                    logger.info(f"ETA: {eta_seconds/60:.1f} minutes remaining")
                    
                except Exception as e:
                    logger.error(f"Bulk update error in batch {batch_num}: {e}")
                    errors += len(bulk_operations) // 2
            
            logger.info("")
        
        # Refresh index
        logger.info("Refreshing index...")
        await es.indices.refresh(index=settings.index_name)
        
        total_time = time.time() - start_time
        
        # Summary
        logger.info("")
        logger.info("="*80)
        logger.info("REINDEXING COMPLETED")
        logger.info("="*80)
        logger.info(f"Total time: {total_time:.2f}s ({total_time/60:.1f} minutes)")
        logger.info(f"Successfully processed: {processed}")
        logger.info(f"Skipped (no text): {skipped}")
        logger.info(f"Errors: {errors}")
        logger.info(f"Total: {total_products}")
        logger.info(f"Speed: {processed/total_time:.1f} products/sec")
        logger.info("="*80)
        
        if processed > 0:
            logger.info("")
            logger.info("✓ REINDEXING SUCCESSFUL!")
            logger.info("")
            logger.info("NOW description_vector includes:")
            logger.info("  ✓ title_ua + title_ru (product names)")
            logger.info("  ✓ description_ua + description_ru (descriptions)")
            logger.info("  ✓ sku + good_code (product codes)")
            logger.info("")
            logger.info("Semantic search will now work much better!")
        else:
            logger.error("✗ NO PRODUCTS WERE PROCESSED!")
        
    except Exception as e:
        logger.error(f"Fatal error during reindexing: {e}", exc_info=True)
    
    finally:
        await es.close()
        await http_client.aclose()


if __name__ == "__main__":
    asyncio.run(reindex_products())

