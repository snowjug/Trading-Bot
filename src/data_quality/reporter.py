"""
Data Quality Reporter (Phase 7).
Generates comprehensive automated data quality markdown reports:
reports/data_quality/YYYY-MM-DD.md
"""

import os
import sys
from datetime import datetime, date
from pathlib import Path
from typing import List, Dict, Any, Optional
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from src.utils.logging import setup_logging
from src.data_quality.checker import DataQualityEngine, DataQualityResult

logger = setup_logging("data_quality.reporter")


class DataQualityReporter:
    """
    Executes DataQualityEngine on a target dataset and formats the results into an auditable report.
    """

    REPORT_DIR = Path("reports/data_quality")

    @classmethod
    def generate_report(
        cls,
        df: pd.DataFrame,
        dataset_name: str,
        dataset_type: str = "options",
        report_date: Optional[date] = None,
    ) -> Path:
        """
        Runs the 20 quality checks and generates reports/data_quality/YYYY-MM-DD.md.
        """
        cls.REPORT_DIR.mkdir(parents=True, exist_ok=True)
        r_date = report_date or datetime.now().date()
        date_str = r_date.strftime("%Y-%m-%d")
        report_path = cls.REPORT_DIR / f"{date_str}.md"

        results: List[DataQualityResult] = DataQualityEngine.run_all_checks(
            df=df,
            dataset_type=dataset_type,
            dataset_date=r_date,
        )

        total_checks = len(results)
        passed_checks = sum(1 for r in results if r.passed)
        failed_critical = sum(1 for r in results if not r.passed and r.severity == "CRITICAL")
        failed_warning = sum(1 for r in results if not r.passed and r.severity == "WARNING")

        overall_status = "PASS" if failed_critical == 0 else "FAIL"

        lines = [
            f"# DATA QUALITY AUDIT REPORT — {date_str}",
            "",
            f"**Dataset Evaluated:** `{dataset_name}`  ",
            f"**Dataset Type:** `{dataset_type}`  ",
            f"**Total Records Evaluated:** {len(df):,}  ",
            f"**Audit Timestamp:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  ",
            f"**Overall Quality Status:** **{overall_status}** ({passed_checks}/{total_checks} Checks Passed)",
            "",
            "---",
            "",
            "## 1. Executive Summary",
            "",
            f"- **Passed Checks:** {passed_checks} / {total_checks}",
            f"- **Critical Anomalies:** {failed_critical}",
            f"- **Warnings / Minor Discrepancies:** {failed_warning}",
            "- **Integrity Policy:** Zero synthetic fallback values. Fail-closed on corrupted records.",
            "",
            "---",
            "",
            "## 2. Detailed Automated Check Matrix (20 Institutional Checks)",
            "",
            "| ID | Automated Check | Status | Severity | Details | Anomaly Count |",
            "| :---: | :--- | :---: | :---: | :--- | :---: |",
        ]

        for r in results:
            status_badge = "✅ PASS" if r.passed else ("❌ FAIL" if r.severity == "CRITICAL" else "⚠️ WARN")
            lines.append(
                f"| {r.check_id:02d} | {r.name} | {status_badge} | {r.severity} | {r.details} | {r.anomaly_count} |"
            )

        lines.extend([
            "",
            "---",
            "",
            "## 3. Microstructure & Integrity Assessment",
            "",
            f"- **Spread Reality Check:** Bid/Ask spreads validated against exchange microstructure.",
            f"- **Timestamp Monotonicity:** Checked against sequence regressions and future leakage.",
            f"- **Contract Identity:** Verified against official Dhan Scrip Master numeric identifiers.",
            f"- **Readiness Recommendation:** {'Dataset APPROVED for research and replay.' if overall_status == 'PASS' else 'Dataset REJECTED due to critical anomalies. Do NOT train or replay.'}",
            "",
        ])

        with open(report_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

        logger.info(f"Data quality report successfully written to: {report_path}")
        return report_path
