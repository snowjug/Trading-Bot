"""
Export Canonical Strategy Definitions to JSON format.
Fulfills Section 24 (STRATEGY DEFINITION FORMAT) of the Master Prompt.
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.strategies.canonical.catalog import get_all_canonical_strategies


def main():
    out_dir = Path("config/canonical_strategies")
    out_dir.mkdir(parents=True, exist_ok=True)

    catalog = get_all_canonical_strategies()
    print(f"Exporting {len(catalog)} canonical strategy definitions to {out_dir}...")

    for name, strategy in catalog.items():
        file_path = out_dir / f"{name}.json"
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(strategy.to_json())
        print(f"  -> {file_path.name}")

    print("Export complete.")


if __name__ == "__main__":
    main()
