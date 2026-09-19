"""
Tests for Canonical Strategy Definitions and JSON Schema Validity.
Fulfills Section 24 of the Master Prompt.
"""
import json
import os
from pathlib import Path
import pytest

from src.strategies.canonical.models import (
    CanonicalStrategyDefinition,
    StrategyFamily,
    InstrumentClass,
)
from src.strategies.canonical.catalog import get_all_canonical_strategies


def test_catalog_contains_all_core_families():
    catalog = get_all_canonical_strategies()
    assert len(catalog) >= 30, f"Expected at least 30 canonical strategies, got {len(catalog)}"

    families_present = {s.family for s in catalog.values()}
    required_families = {
        StrategyFamily.PRICE_ACTION.value,
        StrategyFamily.TREND_FOLLOWING.value,
        StrategyFamily.MOMENTUM.value,
        StrategyFamily.MEAN_REVERSION.value,
        StrategyFamily.OPTIONS_SPREAD.value,
        StrategyFamily.OPTIONS_VOLATILITY.value,
        StrategyFamily.PCR_OI.value,
        StrategyFamily.EXPIRY.value,
        StrategyFamily.OVERNIGHT.value,
    }
    missing = required_families - families_present
    assert not missing, f"Missing strategy families: {missing}"


def test_json_definitions_roundtrip():
    json_dir = Path("config/canonical_strategies")
    assert json_dir.exists(), "config/canonical_strategies directory must exist"

    json_files = list(json_dir.glob("*.json"))
    assert len(json_files) >= 30, f"Expected at least 30 JSON files, got {len(json_files)}"

    for fpath in json_files:
        with open(fpath, "r", encoding="utf-8") as f:
            raw_text = f.read()
        strategy = CanonicalStrategyDefinition.from_json(raw_text)
        assert strategy.name == fpath.stem
        assert strategy.family in [e.value for e in StrategyFamily]
        assert strategy.instrument_class in [e.value for e in InstrumentClass]
        assert strategy.economic_mechanism, f"{strategy.name} must have documented economic mechanism"
        assert strategy.source, f"{strategy.name} must cite source/literature"
        assert strategy.entry_rules, f"{strategy.name} must have explicit entry rules"
        assert strategy.stop_rules, f"{strategy.name} must have explicit stop rules"
        assert strategy.exit_rules, f"{strategy.name} must have explicit exit rules"
        assert "minimum_account" in strategy.capital_requirement
        assert "cost_model" in strategy.execution_assumptions
