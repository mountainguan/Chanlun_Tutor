# Data Caching Standards

This document defines the standards for data persistence and caching in the project. All modules must follow these guidelines to ensure data consistency, minimize API calls, and improve application performance.

## 1. Directory Structure

All cache files must be stored in the `data/` directory.

- **Root Directory**: `data/`
- **Subdirectories**:
  - `data/cache/`: (Recommended) General location for cache files.
  - `data/{module_name}/`: For modules generating many files (e.g., daily history batches).

### Recommended Hierarchy
```text
data/
├── cache/
│   ├── market_sentiment.json    # Structured cache
│   └── sector_list.json         # Static/Infrequent data
├── fund_radar/                  # Large dataset module
│   ├── history_2023.csv
│   └── history_2024.csv
└── meta.json                    # Global metadata (optional)
```

## 2. File Formats

### JSON (Preferred for Structured Data)
Use JSON for complex data structures, configuration, or small datasets.

**Schema Requirement**:
Top-level object MUST contain a `_meta` field for cache management.
```json
{
  "_meta": {
    "last_updated": "2024-03-20 10:30:00",
    "version": "1.0",
    "ttl_seconds": 3600
  },
  "data": {
    "key": "value"
  }
}
```

### CSV (Preferred for Time-Series/Tabular)
Use CSV for large tabular data (e.g., stock history, K-lines) to save space and improve parsing speed with Pandas.

- **Naming**: `snake_case.csv`
- **Header**: Must include a header row.
- **Date Format**: ISO 8601 (`YYYY-MM-DD` or `YYYY-MM-DD HH:MM:SS`).

## 3. Caching Logic

### Read-Through Pattern
Modules should implement a `get_data()` method that follows this flow:
1.  **Check Cache**: Load file and check `_meta.last_updated`.
2.  **Validate**: Is cache exists AND age < TTL?
3.  **Return Cached**: If valid, return data immediately.
4.  **Fetch & Update**: If invalid/missing, fetch from API.
5.  **Fallback**: If fetch fails, return expired cache (if available) and log a warning ("Stale Data").

### Time To Live (TTL)
Define TTL constants at the top of your class/module.
- **Real-time Data**: 60-300 seconds (e.g., Market Sentiment).
- **Daily Data**: 24 hours (e.g., End-of-day reports).
- **Static Data**: Permanent or Manual Refresh (e.g., Sector lists).

### Atomic Writes (Best Practice)
To prevent data corruption during write operations:
1.  Write data to a temporary file (e.g., `file.json.tmp`).
2.  Flush and sync to disk.
3.  Rename temporary file to target file (`os.replace`).

## 4. Implementation Example

```python
import json
import os
import time
from datetime import datetime

class DataManager:
    CACHE_FILE = 'data/cache/example_data.json'
    TTL = 3600  # 1 hour

    def get_data(self):
        # 1. Try Cache
        data = self._load_cache()
        if data:
            return data
            
        # 2. Fetch New
        try:
            new_data = self._fetch_from_api()
            self._save_cache(new_data)
            return new_data
        except Exception as e:
            # 3. Fallback
            print(f"Fetch failed: {e}")
            if os.path.exists(self.CACHE_FILE):
                return self._load_from_disk() # Return stale data
            raise

    def _load_cache(self):
        if not os.path.exists(self.CACHE_FILE):
            return None
            
        try:
            with open(self.CACHE_FILE, 'r') as f:
                content = json.load(f)
            
            last_updated = content.get('_meta', {}).get('last_updated', 0)
            if time.time() - last_updated < self.TTL:
                return content['data']
        except:
            return None # Corrupt cache
            
        return None # Expired

    def _save_cache(self, data):
        content = {
            "_meta": {
                "last_updated": time.time(),
                "ttl_seconds": self.TTL
            },
            "data": data
        }
        
        # Atomic Write
        tmp_file = self.CACHE_FILE + '.tmp'
        with open(tmp_file, 'w') as f:
            json.dump(content, f)
        os.replace(tmp_file, self.CACHE_FILE)
```
