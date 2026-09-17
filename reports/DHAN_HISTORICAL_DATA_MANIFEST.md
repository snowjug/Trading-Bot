# DHAN HISTORICAL DATA INGESTION MANIFEST

**Generated at:** 2026-09-17 10:08:41  
**Source API:** Official DhanHQ Data API (`api.dhan.co/v2`)  
**Data Storage Format:** Partitioned Apache Parquet (Snappy / ZSTD compressed)  
**Integrity Verification:** Strict Fail-Closed (Zero Synthetic Fallback Values)

---

## 1. Storage & Dataset Summary

| Metric | Measured Value |
| :--- | :--- |
| **Total Parquet Files** | 117 |
| **Total Rows Indexed** | 297,677 |
| **Total Disk Size (MB)** | 119.40 MB |
| **Storage Engine** | PyArrow + DuckDB Native Parquet |
| **Integrity Audit** | SHA-256 Checksums Logged per File |

---

## 2. Ingested Datasets Breakdown

| Category | File Count | Size on Disk (Bytes) |
| :--- | :---: | :---: |
| `features` | 48 | 116,594,085 |
| `normalized` | 1 | 4,943 |
| `processed` | 52 | 7,770,294 |
| `raw` | 16 | 831,311 |

---

## 3. Data Integrity & Verification
- **Official Security IDs**: Resolved dynamically via Dhan Scrip Master.
- **Microstructure**: Real 5-level Bid/Ask market depth captured without synthetic approximations.
- **Historical Options**: Authentic continuous expired options candles with IV, OI, and underlying Spot.
- **Missing Data Policy**: `DATA_UNAVAILABLE` recorded for any API drops. Zero price fabrication.
