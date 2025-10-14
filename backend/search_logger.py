"""
Модуль для логування результатів чат-пошуку товарів.
Зберігає детальну інформацію про score товарів для аналізу якості підбору.
"""

import os
import json
import datetime
from typing import List, Dict, Any, Optional
from pathlib import Path


class SearchLogger:
    """
    Логер для запису результатів пошуку в структуровані файли.
    Організовує логи по сесіях для зручного аналізу.
    """
    
    def __init__(self, logs_dir: str = "search_logs"):
        """
        Ініціалізація логера.
        
        Args:
            logs_dir: Директорія для збереження логів
        """
        self.logs_dir = Path(logs_dir)
        self.logs_dir.mkdir(exist_ok=True)
        self.log_file = self.logs_dir / "search_queries.json"
        self.readable_file = self.logs_dir / "search_queries_readable.txt"
        
    def _load_logs(self) -> List[Dict[str, Any]]:
        """Завантажує всі існуючі логи з файлу."""
        if not self.log_file.exists():
            return []
        
        try:
            with open(self.log_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, Exception):
            return []
    
    def _save_logs(self, logs: List[Dict[str, Any]]):
        """Зберігає логи у файл з форматуванням."""
        with open(self.log_file, "w", encoding="utf-8") as f:
            json.dump(logs, f, ensure_ascii=False, indent=2)
        
        # Створюємо readable версію з роздільниками між сесіями
        self._create_readable_file(logs)
    
    def _create_readable_file(self, logs: List[Dict[str, Any]]):
        """Створює текстовий файл з гарним форматуванням та роздільниками між сесіями."""
        if not logs:
            return
        
        # Групуємо логи по сесіях
        sessions = {}
        for log in logs:
            session_id = log.get("session_id", "unknown")
            if session_id not in sessions:
                sessions[session_id] = []
            sessions[session_id].append(log)
        
        with open(self.readable_file, "w", encoding="utf-8") as f:
            f.write("=" * 100 + "\n")
            f.write(f"{'ЛОГИ ПОШУКОВИХ ЗАПИТІВ':^100}\n")
            f.write(f"{'Згенеровано: ' + datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'):^100}\n")
            f.write("=" * 100 + "\n\n")
            
            for session_idx, (session_id, session_logs) in enumerate(sorted(sessions.items()), 1):
                if session_idx > 1:
                    f.write("\n" + "-" * 100 + "\n")
                    f.write(f"{'НОВА СЕСІЯ':^100}\n")
                    f.write("-" * 100 + "\n\n")
                
                f.write(f"📱 СЕСІЯ: {session_id}\n")
                f.write(f"📊 Кількість запитів в сесії: {len(session_logs)}\n")
                f.write(f"🕐 Перший запит: {session_logs[0]['timestamp']}\n")
                f.write(f"🕐 Останній запит: {session_logs[-1]['timestamp']}\n")
                f.write("\n")
                
                for query_idx, log in enumerate(session_logs, 1):
                    f.write(f"  {'─' * 96}\n")
                    f.write(f"  Запит #{query_idx}\n")
                    f.write(f"  {'─' * 96}\n")
                    f.write(f"  🕐 Час:        {log['timestamp']}\n")
                    f.write(f"  🔍 Запит:      {log['query']}\n")
                    f.write(f"  🎯 Тип:        {log['intent']}\n")
                    
                    stats = log['search_stats']
                    f.write(f"\n  📊 СТАТИСТИКА:\n")
                    f.write(f"     • Знайдено товарів:    {stats['total_found']}\n")
                    f.write(f"     • Після фільтрації:    {stats['after_filtering']} ({stats['filtering_rate']*100:.1f}%)\n")
                    f.write(f"     • Max score:           {stats['max_score']}\n")
                    f.write(f"     • Поріг фільтрації:    {stats['threshold_final']}\n")
                    f.write(f"     • Час пошуку:          {stats['search_time_ms']:.0f} мс\n")
                    
                    if log.get('subqueries'):
                        f.write(f"\n  🔎 ПІДЗАПИТИ ({len(log['subqueries'])}):\n")
                        for i, subq in enumerate(log['subqueries'][:5], 1):
                            f.write(f"     {i}. {subq}\n")
                    
                    if log.get('top_products'):
                        f.write(f"\n  🏆 ТОП-10 ТОВАРІВ:\n")
                        for i, prod in enumerate(log['top_products'][:10], 1):
                            recommended = "⭐" if prod.get('recommended') else "  "
                            f.write(f"     {recommended} {i:2d}. [{prod['score']:.4f}] {prod['name']}\n")
                    
                    if log.get('additional_info', {}).get('categories'):
                        cats = log['additional_info']['categories']
                        f.write(f"\n  📁 КАТЕГОРІЇ ({len(cats)}): {', '.join(cats[:5])}\n")
                    
                    f.write("\n")
    
    def log_search_query(
        self,
        session_id: str,
        query: str,
        subqueries: List[str],
        total_products_found: int,
        products_after_filtering: int,
        max_score: float,
        threshold: float,
        adaptive_min: float,
        dynamic_threshold: float,
        top_products: List[Dict[str, Any]],
        search_time_ms: float,
        intent: str = "product_search",
        additional_info: Optional[Dict[str, Any]] = None
    ):
        """
        Логує один запит пошуку з усіма деталями.
        
        Args:
            session_id: Ідентифікатор сесії
            query: Оригінальний запит користувача
            subqueries: Згенеровані підзапити
            total_products_found: Загальна кількість знайдених товарів
            products_after_filtering: Кількість після фільтрації
            max_score: Максимальний score серед товарів
            threshold: Фінальний поріг фільтрації
            adaptive_min: Адаптивний мінімальний поріг
            dynamic_threshold: Динамічний поріг
            top_products: Топ товарів з їх scores (ID, назва, score)
            search_time_ms: Час виконання пошуку в мілісекундах
            intent: Тип запиту (product_search, clarification, invalid)
            additional_info: Додаткова інформація (категорії, рекомендації тощо)
        """
        timestamp = datetime.datetime.now().isoformat()
        
        log_entry = {
            "timestamp": timestamp,
            "session_id": session_id,
            "query": query,
            "intent": intent,
            "subqueries": subqueries,
            "search_stats": {
                "total_found": total_products_found,
                "after_filtering": products_after_filtering,
                "filtering_rate": round(products_after_filtering / total_products_found, 3) if total_products_found > 0 else 0,
                "max_score": round(max_score, 4),
                "threshold_final": round(threshold, 4),
                "threshold_adaptive_min": round(adaptive_min, 4),
                "threshold_dynamic": round(dynamic_threshold, 4),
                "search_time_ms": round(search_time_ms, 2)
            },
            "top_products": top_products,
            "additional_info": additional_info or {}
        }
        
        # Завантажуємо існуючі логи, додаємо новий і зберігаємо
        logs = self._load_logs()
        logs.append(log_entry)
        self._save_logs(logs)
    
    def get_session_logs(self, session_id: str) -> List[Dict[str, Any]]:
        """
        Читає всі логи для конкретної сесії.
        
        Args:
            session_id: Ідентифікатор сесії
            
        Returns:
            Список всіх запитів в сесії
        """
        all_logs = self._load_logs()
        return [log for log in all_logs if log.get("session_id") == session_id]
    
    def get_all_sessions(self) -> List[str]:
        """
        Повертає список всіх ідентифікаторів сесій.
        
        Returns:
            Список session_id
        """
        all_logs = self._load_logs()
        sessions = list(set(log.get("session_id") for log in all_logs if log.get("session_id")))
        return sorted(sessions)
    
    def generate_session_report(self, session_id: str) -> Dict[str, Any]:
        """
        Генерує звіт по сесії з аналітикою.
        
        Args:
            session_id: Ідентифікатор сесії
            
        Returns:
            Словник з аналітикою по сесії
        """
        logs = self.get_session_logs(session_id)
        
        if not logs:
            return {"error": "Session not found"}
        
        total_queries = len(logs)
        avg_search_time = sum(log["search_stats"]["search_time_ms"] for log in logs) / total_queries
        avg_products_found = sum(log["search_stats"]["total_found"] for log in logs) / total_queries
        avg_products_filtered = sum(log["search_stats"]["after_filtering"] for log in logs) / total_queries
        avg_filtering_rate = sum(log["search_stats"]["filtering_rate"] for log in logs) / total_queries
        
        # Аналіз score-ів
        all_scores = []
        for log in logs:
            all_scores.extend([p["score"] for p in log["top_products"]])
        
        avg_max_score = sum(log["search_stats"]["max_score"] for log in logs) / total_queries
        
        report = {
            "session_id": session_id,
            "total_queries": total_queries,
            "first_query_time": logs[0]["timestamp"],
            "last_query_time": logs[-1]["timestamp"],
            "average_stats": {
                "search_time_ms": round(avg_search_time, 2),
                "products_found": round(avg_products_found, 1),
                "products_after_filtering": round(avg_products_filtered, 1),
                "filtering_rate": round(avg_filtering_rate, 3),
                "max_score": round(avg_max_score, 4)
            },
            "score_distribution": {
                "min": round(min(all_scores), 4) if all_scores else 0,
                "max": round(max(all_scores), 4) if all_scores else 0,
                "avg": round(sum(all_scores) / len(all_scores), 4) if all_scores else 0
            },
            "queries": [
                {
                    "query": log["query"],
                    "timestamp": log["timestamp"],
                    "found": log["search_stats"]["total_found"],
                    "filtered": log["search_stats"]["after_filtering"],
                    "max_score": log["search_stats"]["max_score"]
                }
                for log in logs
            ]
        }
        
        return report
    
    def export_all_sessions_report(self, output_file: str = "all_sessions_report.json"):
        """
        Експортує звіт по всіх сесіях в один файл.
        
        Args:
            output_file: Ім'я файлу для збереження звіту
        """
        all_sessions = self.get_all_sessions()
        
        reports = []
        for session_id in all_sessions:
            report = self.generate_session_report(session_id)
            reports.append(report)
        
        output_path = self.logs_dir / output_file
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump({
                "generated_at": datetime.datetime.now().isoformat(),
                "total_sessions": len(reports),
                "sessions": reports
            }, f, ensure_ascii=False, indent=2)
        
        return str(output_path)

