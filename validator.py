"""
GCHI Dominance Engine — Validator Module
GC Home Improvement LLC | v8.4
Author: Manus AI

This module contains the GCHIValidator class, which is the core logic engine
for validating JobTread CSV proposals against the official GCHI v8.4 rules.
It reads three source-of-truth files and performs comprehensive validation.
"""

import io
import os
import re
import pandas as pd
from dataclasses import dataclass, field
from typing import Optional


# ─────────────────────────────────────────────────────────────────────────────
# Data Models
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ValidationError:
    """Represents a single validation error found in a proposal row."""
    row: int
    column: str
    value: str
    message: str
    severity: str = "error"  # "error" | "warning"


@dataclass
class ValidationResult:
    """The complete result of a validation run."""
    is_valid: bool
    total_rows: int
    errors: list[ValidationError] = field(default_factory=list)
    warnings: list[ValidationError] = field(default_factory=list)
    summary: dict = field(default_factory=dict)

    @property
    def error_count(self) -> int:
        return len(self.errors)

    @property
    def warning_count(self) -> int:
        return len(self.warnings)


# ─────────────────────────────────────────────────────────────────────────────
# Required CSV Columns
# ─────────────────────────────────────────────────────────────────────────────

REQUIRED_COLUMNS = [
    "Cost Group Name",
    "Cost Item Name",
    "Description",
    "Quantity",
    "Unit",
    "Unit Cost",
    "Unit Price",
    "Cost Type",
    "Taxable",
]

# Taxable rules per Cost Type (source of truth: jobtread_rules.md v8.4)
TAXABLE_RULES = {
    "Labor": False,
    "Materials": True,
    "Subcontractor": True,
    "Equipment / Rental": False,
    "Permits / Fees": False,
    "Allowance": True,
    "Other": False,
}


# ─────────────────────────────────────────────────────────────────────────────
# GCHIValidator Class
# ─────────────────────────────────────────────────────────────────────────────

class GCHIValidator:
    """
    Core validation engine for GCHI JobTread CSV proposals.

    Loads three source-of-truth files on initialization and exposes a
    single `validate(df)` method that returns a `ValidationResult`.
    """

    def __init__(self, data_dir: str = "data"):
        """
        Initialize the validator by loading all source-of-truth data files.

        Args:
            data_dir: Path to the directory containing the three reference CSVs.

        Raises:
            FileNotFoundError: If any of the required data files are missing.
            ValueError: If any data file cannot be parsed correctly.
        """
        self.data_dir = data_dir
        self._valid_cost_codes: set[str] = set()
        self._valid_cost_types: set[str] = set()
        self._valid_units: set[str] = set()
        self._cost_codes_df: Optional[pd.DataFrame] = None
        self._cost_types_df: Optional[pd.DataFrame] = None
        self._units_df: Optional[pd.DataFrame] = None
        self._load_reference_data()

    def _load_reference_data(self) -> None:
        """Load and parse all three source-of-truth CSV files."""
        # ── Cost Codes ────────────────────────────────────────────────────────
        cost_codes_path = os.path.join(self.data_dir, "GCHI_CostCodes_Complete.csv")
        if not os.path.exists(cost_codes_path):
            raise FileNotFoundError(
                f"Cost Codes file not found: {cost_codes_path}\n"
                "Please ensure 'GCHI_CostCodes_Complete.csv' is in the data/ directory."
            )
        try:
            self._cost_codes_df = pd.read_csv(cost_codes_path, dtype=str)
            # The "Name" column contains both parent and child cost code names
            self._valid_cost_codes = set(
                self._cost_codes_df["Name"].dropna().str.strip().tolist()
            )
        except Exception as e:
            raise ValueError(f"Failed to parse Cost Codes file: {e}")

        # ── Cost Types ────────────────────────────────────────────────────────
        cost_types_path = os.path.join(self.data_dir, "cost-types-2026-03-09-2.csv")
        if not os.path.exists(cost_types_path):
            raise FileNotFoundError(
                f"Cost Types file not found: {cost_types_path}\n"
                "Please ensure 'cost-types-2026-03-09-2.csv' is in the data/ directory."
            )
        try:
            self._cost_types_df = pd.read_csv(cost_types_path, dtype=str)
            # Strip BOM and whitespace from column names
            self._cost_types_df.columns = (
                self._cost_types_df.columns.str.strip().str.lstrip("\ufeff").str.strip('"')
            )
            self._valid_cost_types = set(
                self._cost_types_df["Name"].dropna().str.strip().tolist()
            )
            # Add the 3 new cost types that were added in the session (not yet in the
            # original JobTread export file, but are valid per jobtread_rules.md v8.4)
            self._valid_cost_types.update(
                {"Equipment / Rental", "Permits / Fees", "Allowance"}
            )
        except Exception as e:
            raise ValueError(f"Failed to parse Cost Types file: {e}")

        # ── Units ─────────────────────────────────────────────────────────────
        units_path = os.path.join(self.data_dir, "units-2026-03-09-2.csv")
        if not os.path.exists(units_path):
            raise FileNotFoundError(
                f"Units file not found: {units_path}\n"
                "Please ensure 'units-2026-03-09-2.csv' is in the data/ directory."
            )
        try:
            self._units_df = pd.read_csv(units_path, dtype=str)
            self._units_df.columns = (
                self._units_df.columns.str.strip().str.lstrip("\ufeff").str.strip('"')
            )
            self._valid_units = set(
                self._units_df["Name"].dropna().str.strip().tolist()
            )
            # Add the 8 new units added in the session (not yet in the original export)
            self._valid_units.update(
                {"Bags", "Board Feet", "Boxes", "Bundles", "Pieces", "Rolls", "Sets", "Sheets"}
            )
        except Exception as e:
            raise ValueError(f"Failed to parse Units file: {e}")

    # ── Public Properties ─────────────────────────────────────────────────────

    @property
    def valid_cost_codes(self) -> set[str]:
        return self._valid_cost_codes

    @property
    def valid_cost_types(self) -> set[str]:
        return self._valid_cost_types

    @property
    def valid_units(self) -> set[str]:
        return self._valid_units

    @property
    def reference_counts(self) -> dict:
        return {
            "cost_codes": len(self._valid_cost_codes),
            "cost_types": len(self._valid_cost_types),
            "units": len(self._valid_units),
        }

    # ── Core Validation Method ────────────────────────────────────────────────

    @staticmethod
    def preprocess_csv(raw_bytes: bytes) -> pd.DataFrame:
        """
        Pre-process a raw CSV upload, handling common formatting issues:
        - BOM (UTF-8 with BOM, common from Excel/Windows)
        - Rows wrapped in outer double-quotes (common from ChatGPT exports)
        - Trailing whitespace and empty rows

        Args:
            raw_bytes: The raw bytes of the uploaded CSV file.

        Returns:
            A cleaned pandas DataFrame ready for validation.

        Raises:
            ValueError: If the file cannot be parsed as a valid CSV.
        """
        # Decode with BOM handling
        try:
            text = raw_bytes.decode('utf-8-sig').strip()
        except UnicodeDecodeError:
            text = raw_bytes.decode('latin-1').strip()

        lines = text.splitlines()
        if not lines:
            raise ValueError("The uploaded file is empty.")

        # Detect wrapped-quote format: each line is "col1,col2,..."
        # This happens when ChatGPT or some editors wrap entire rows in quotes
        sample = lines[0].strip()
        if sample.startswith('"') and sample.endswith('"') and ',' in sample[1:-1]:
            # Strip outer quotes from every line
            lines = [
                line.strip()[1:-1] if (line.strip().startswith('"') and line.strip().endswith('"'))
                else line.strip()
                for line in lines
            ]
            text = '\n'.join(lines)

        try:
            df = pd.read_csv(io.StringIO(text), dtype=str)
            # Strip whitespace from all string values
            df = df.map(lambda x: x.strip() if isinstance(x, str) else x)
            # Drop fully empty rows
            df = df.dropna(how='all').reset_index(drop=True)
            return df
        except Exception as e:
            raise ValueError(f"Could not parse CSV file: {e}")

    def validate(self, df: pd.DataFrame) -> ValidationResult:
        """
        Validate a proposal DataFrame against all GCHI v8.4 rules.

        Args:
            df: A pandas DataFrame loaded from the user's uploaded CSV.

        Returns:
            A ValidationResult object with all errors, warnings, and summary.
        """
        errors: list[ValidationError] = []
        warnings: list[ValidationError] = []

        # ── Step 1: Check required columns ───────────────────────────────────
        missing_cols = [c for c in REQUIRED_COLUMNS if c not in df.columns]
        if missing_cols:
            # Return early — we can't validate without the required columns
            return ValidationResult(
                is_valid=False,
                total_rows=len(df),
                errors=[
                    ValidationError(
                        row=0,
                        column="[STRUCTURE]",
                        value="",
                        message=(
                            f"Missing required column(s): {', '.join(missing_cols)}. "
                            f"Expected columns: {', '.join(REQUIRED_COLUMNS)}"
                        ),
                        severity="error",
                    )
                ],
                summary={"missing_columns": missing_cols},
            )

        # ── Step 2: Row-by-row validation ─────────────────────────────────────
        for idx, row in df.iterrows():
            row_num = idx + 2  # +2 because idx is 0-based and row 1 is the header

            # ── 2a. Cost Group Name ───────────────────────────────────────────
            cost_group = str(row.get("Cost Group Name", "")).strip()
            if not cost_group:
                errors.append(ValidationError(
                    row=row_num,
                    column="Cost Group Name",
                    value="(empty)",
                    message="Cost Group Name cannot be empty.",
                ))
            elif cost_group not in self._valid_cost_codes:
                # Try case-insensitive match to give a helpful suggestion
                lower_map = {c.lower(): c for c in self._valid_cost_codes}
                suggestion = lower_map.get(cost_group.lower())
                hint = f" Did you mean '{suggestion}'?" if suggestion else ""

                # Detect numeric code pattern (e.g. '01-001', '0101', '99-999')
                is_numeric_code = bool(re.match(r'^\d{2,4}[-]?\d{0,4}$', cost_group))
                if is_numeric_code:
                    hint = (
                        " Note: The 'Cost Group Name' field requires the descriptive NAME "
                        "(e.g. 'Building Permits'), not the numeric code (e.g. '0101'). "
                        "Use the GCHI v8.4 Cost Code library to find the correct name."
                    )

                errors.append(ValidationError(
                    row=row_num,
                    column="Cost Group Name",
                    value=cost_group,
                    message=f"'{cost_group}' is not a valid Cost Code in the GCHI v8.4 library.{hint}",
                ))

            # ── 2b. Cost Type ─────────────────────────────────────────────────
            cost_type = str(row.get("Cost Type", "")).strip()
            if not cost_type:
                errors.append(ValidationError(
                    row=row_num,
                    column="Cost Type",
                    value="(empty)",
                    message="Cost Type cannot be empty.",
                ))
            elif cost_type not in self._valid_cost_types:
                errors.append(ValidationError(
                    row=row_num,
                    column="Cost Type",
                    value=cost_type,
                    message=(
                        f"'{cost_type}' is not a valid Cost Type. "
                        f"Allowed values: {', '.join(sorted(self._valid_cost_types))}"
                    ),
                ))

            # ── 2c. Unit ──────────────────────────────────────────────────────
            unit = str(row.get("Unit", "")).strip()
            if not unit:
                errors.append(ValidationError(
                    row=row_num,
                    column="Unit",
                    value="(empty)",
                    message="Unit cannot be empty.",
                ))
            elif unit not in self._valid_units:
                errors.append(ValidationError(
                    row=row_num,
                    column="Unit",
                    value=unit,
                    message=(
                        f"'{unit}' is not a valid Unit. "
                        f"Allowed values: {', '.join(sorted(self._valid_units))}"
                    ),
                ))

            # ── 2d. Taxable consistency check (warning) ───────────────────────
            taxable_raw = str(row.get("Taxable", "")).strip().lower()
            taxable_bool = taxable_raw in ("true", "1", "yes")
            if cost_type in TAXABLE_RULES:
                expected_taxable = TAXABLE_RULES[cost_type]
                if taxable_bool != expected_taxable:
                    warnings.append(ValidationError(
                        row=row_num,
                        column="Taxable",
                        value=taxable_raw,
                        message=(
                            f"Taxable mismatch for Cost Type '{cost_type}'. "
                            f"Expected: {'true' if expected_taxable else 'false'}, "
                            f"Found: {taxable_raw}. "
                            "Review GCHI v8.4 taxable rules."
                        ),
                        severity="warning",
                    ))

            # ── 2e. Numeric field validation ──────────────────────────────────
            for num_col in ("Quantity", "Unit Cost", "Unit Price"):
                val = str(row.get(num_col, "")).strip()
                if val:
                    try:
                        num = float(val)
                        if num < 0:
                            warnings.append(ValidationError(
                                row=row_num,
                                column=num_col,
                                value=val,
                                message=f"'{num_col}' is negative ({val}). Verify this is intentional.",
                                severity="warning",
                            ))
                    except ValueError:
                        errors.append(ValidationError(
                            row=row_num,
                            column=num_col,
                            value=val,
                            message=f"'{num_col}' must be a number, got: '{val}'",
                        ))

            # ── 2f. Cost Item Name must not be empty ──────────────────────────
            item_name = str(row.get("Cost Item Name", "")).strip()
            if not item_name:
                errors.append(ValidationError(
                    row=row_num,
                    column="Cost Item Name",
                    value="(empty)",
                    message="Cost Item Name cannot be empty.",
                ))

        # ── Step 3: Build summary ─────────────────────────────────────────────
        error_cols = {}
        for e in errors:
            error_cols[e.column] = error_cols.get(e.column, 0) + 1

        summary = {
            "total_rows": len(df),
            "total_errors": len(errors),
            "total_warnings": len(warnings),
            "errors_by_column": error_cols,
        }

        return ValidationResult(
            is_valid=len(errors) == 0,
            total_rows=len(df),
            errors=errors,
            warnings=warnings,
            summary=summary,
        )

    def get_errors_dataframe(self, result: ValidationResult) -> pd.DataFrame:
        """Convert validation errors to a display-ready DataFrame."""
        if not result.errors and not result.warnings:
            return pd.DataFrame()

        all_issues = result.errors + result.warnings
        return pd.DataFrame([
            {
                "Row": issue.row,
                "Column": issue.column,
                "Value Found": issue.value,
                "Issue": issue.message,
                "Severity": issue.severity.upper(),
            }
            for issue in sorted(all_issues, key=lambda x: (x.row, x.column))
        ])
