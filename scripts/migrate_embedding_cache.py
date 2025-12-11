#!/usr/bin/env python3
"""
Migration script: JSON embedding cache -> SQLite blob storage.

Migrates both:
- data/embeddings_cache.json -> data/embeddings_cache.db
- data/classification_embeddings_cache.json -> data/classification_embeddings_cache.db

Usage:
    python scripts/migrate_embedding_cache.py
"""
import json
import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.ai.embeddings.sqlite_cache import SQLiteEmbeddingCache


def get_file_size_mb(path: str) -> float:
    """Get file size in MB."""
    if os.path.exists(path):
        return os.path.getsize(path) / (1024 * 1024)
    return 0.0


def migrate_cache(json_path: str, db_path: str) -> dict:
    """
    Migrate a single JSON cache file to SQLite.
    
    Returns:
        dict with migration statistics
    """
    stats = {
        "json_path": json_path,
        "db_path": db_path,
        "entries": 0,
        "json_size_mb": 0.0,
        "db_size_mb": 0.0,
        "reduction_percent": 0.0,
        "success": False,
        "error": None
    }
    
    if not os.path.exists(json_path):
        stats["error"] = f"JSON file not found: {json_path}"
        return stats
    
    stats["json_size_mb"] = get_file_size_mb(json_path)
    
    try:
        # Load JSON cache
        print(f"  Loading {json_path}...")
        with open(json_path, 'r', encoding='utf-8') as f:
            cache_data = json.load(f)
        
        entries = len(cache_data)
        stats["entries"] = entries
        print(f"  Found {entries} entries")
        
        if entries == 0:
            stats["success"] = True
            return stats
        
        # Remove existing DB if present (fresh migration)
        if os.path.exists(db_path):
            os.remove(db_path)
            print(f"  Removed existing {db_path}")
        
        # Create SQLite cache and migrate entries
        print(f"  Migrating to {db_path}...")
        sqlite_cache = SQLiteEmbeddingCache(db_path)
        
        for i, (key, embedding) in enumerate(cache_data.items()):
            sqlite_cache.set(key, embedding)
            if (i + 1) % 1000 == 0:
                print(f"    Migrated {i + 1}/{entries} entries...")
        
        sqlite_cache.save()
        sqlite_cache.close()
        
        stats["db_size_mb"] = get_file_size_mb(db_path)
        
        if stats["json_size_mb"] > 0:
            reduction = (1 - stats["db_size_mb"] / stats["json_size_mb"]) * 100
            stats["reduction_percent"] = round(reduction, 1)
        
        stats["success"] = True
        
    except Exception as e:
        stats["error"] = str(e)
    
    return stats


def main():
    print("=" * 60)
    print("Embedding Cache Migration: JSON -> SQLite Blob")
    print("=" * 60)
    
    # Define cache files to migrate
    caches = [
        ("data/embeddings_cache.json", "data/embeddings_cache.db"),
        ("data/classification_embeddings_cache.json", "data/classification_embeddings_cache.db"),
    ]
    
    all_stats = []
    
    for json_path, db_path in caches:
        print(f"\n[Migrating] {json_path}")
        stats = migrate_cache(json_path, db_path)
        all_stats.append(stats)
        
        if stats["success"]:
            print(f"  ✓ Success: {stats['entries']} entries")
            print(f"    JSON: {stats['json_size_mb']:.2f} MB -> SQLite: {stats['db_size_mb']:.2f} MB")
            print(f"    Size reduction: {stats['reduction_percent']:.1f}%")
        else:
            print(f"  ✗ Failed: {stats['error']}")
    
    # Summary
    print("\n" + "=" * 60)
    print("Migration Summary")
    print("=" * 60)
    
    total_json_mb = sum(s["json_size_mb"] for s in all_stats)
    total_db_mb = sum(s["db_size_mb"] for s in all_stats)
    total_entries = sum(s["entries"] for s in all_stats)
    successful = sum(1 for s in all_stats if s["success"])
    
    print(f"Caches migrated: {successful}/{len(all_stats)}")
    print(f"Total entries: {total_entries}")
    print(f"Total size: {total_json_mb:.2f} MB -> {total_db_mb:.2f} MB")
    
    if total_json_mb > 0:
        overall_reduction = (1 - total_db_mb / total_json_mb) * 100
        print(f"Overall reduction: {overall_reduction:.1f}%")
    
    print("\nNote: JSON files are preserved. Delete them manually after verification.")
    print("=" * 60)


if __name__ == "__main__":
    main()
