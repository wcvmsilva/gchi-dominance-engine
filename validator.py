"""
GCHI Dominance Engine — Validator Module
GC Home Improvement LLC | v8.4.1
Author: Manus AI

This module contains the GCHIValidator class, which is the core logic engine
for validating JobTread CSV proposals against the official GCHI v8.4 rules.
It reads three source-of-truth files and performs comprehensive validation.

v8.4.1 — Column-name auto-mapping to support both:
  - JobTread native export format  (Cost Group, Cost Item, ...)
  - GCHI internal format           (Cost Group Name, Cost Item Name, ...)
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
# Column Mapping — JobTread <-> GCHI Internal
# ─────────────────────────────────────────────────────────────────────────────

# Map of alternative names -> canonical name (case-insensitive matching)
COLUMN_ALIASES = {
    # GCHI internal / ChatGPT format uses these longer names:
    "cost group name":  "Cost Group",
    "cost item name":   "Cost Item",
    # Underscore variants:
    "cost_group":       "Cost Group",
    "cost_item":        "Cost Item",
    "cost_group_name":  "Cost Group",
    "cost_item_name":   "Cost Item",
    "unit_cost":        "Unit Cost",
    "unit_price":       "Unit Price",
    "cost_type":        "Cost Type",
}

# Required columns (must be present after normalization)
REQUIRED_COLUMNS = [
    "Cost Group",
    "Cost Item",
    "Description",
    "Quantity",
    "Unit",
    "Unit Cost",
    "Cost Type",
    "Taxable",
]

# Optional columns (validated if present, but not required)
OPTIONAL_COLUMNS = [
    "Unit Price",
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
        self._valid_cost_groups: set[str] = set()    # Parent cost codes
        self._valid_cost_items: set[str] = set()      # Child cost codes
        self._valid_cost_codes: set[str] = set()      # All cost codes (parent + child)
        self._valid_cost_types: set[str] = set()
        self._valid_units: set[str] = set()
        self._cost_codes_df: Optional[pd.DataFrame] = None
        self._cost_types_df: Optional[pd.DataFrame] = None
        self._units_df: Optional[pd.DataFrame] = None
        self._parent_child_map: dict[str, list[str]] = {}  # parent -> [children]
        self._child_parent_map: dict[str, str] = {}         # child -> parent
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
            all_names = self._cost_codes_df["Name"].dropna().str.strip().tolist()
            self._valid_cost_codes = set(all_names)

            # Separate parents and children, build relationship maps
            for _, row in self._cost_codes_df.iterrows():
                name = str(row.get("Name", "")).strip()
                parent_name = str(row.get("Parent Name", "")).strip()
                if not name:
                    continue
                if not parent_name or parent_name == "nan":
                    # This is a parent cost code (Cost Group)
                    self._valid_cost_groups.add(name)
                    if name not in self._parent_child_map:
                        self._parent_child_map[name] = []
                else:
                    # This is a child cost code (Cost Item)
                    self._valid_cost_items.add(name)
                    self._child_parent_map[name] = parent_name
                    if parent_name not in self._parent_child_map:
                        self._parent_child_map[parent_name] = []
                    self._parent_child_map[parent_name].append(name)
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
            self._cost_types_df.columns = (
                self._cost_types_df.columns.str.strip().str.lstrip("\ufeff").str.strip('"')
            )
            self._valid_cost_types = set(
                self._cost_types_df["Name"].dropna().str.strip().tolist()
            )
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
    def valid_cost_groups(self) -> set[str]:
        return self._valid_cost_groups

    @property
    def valid_cost_items(self) -> set[str]:
        return self._valid_cost_items

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
            "cost_groups": len(self._valid_cost_groups),
            "cost_items": len(self._valid_cost_items),
            "cost_types": len(self._valid_cost_types),
            "units": len(self._valid_units),
        }

    # ── Column Normalization ─────────────────────────────────────────────────

    @staticmethod
    def normalize_columns(df: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
        """
        Normalize column names to canonical GCHI format.

        Handles multiple naming conventions:
        - JobTread native: 'Cost Group', 'Cost Item'
        - GCHI internal:   'Cost Group Name', 'Cost Item Name'
        - Underscore:      'cost_group', 'cost_item'

        Returns:
            Tuple of (normalized DataFrame, list of column mappings applied).
        """
        mappings_applied = []
        new_columns = {}

        for col in df.columns:
            col_stripped = col.strip()
            col_lower = col_stripped.lower()

            # Check if it's already a canonical name
            canonical_names_lower = {c.lower(): c for c in REQUIRED_COLUMNS + OPTIONAL_COLUMNS}
            if col_lower in canonical_names_lower:
                canonical = canonical_names_lower[col_lower]
                if col_stripped != canonical:
                    new_columns[col] = canonical
                    mappings_applied.append(f"'{col_stripped}' -> '{canonical}'")
            elif col_lower in COLUMN_ALIASES:
                target = COLUMN_ALIASES[col_lower]
                new_columns[col] = target
                mappings_applied.append(f"'{col_stripped}' -> '{target}'")
            # else: keep the column as-is (extra columns are allowed)

        if new_columns:
            df = df.rename(columns=new_columns)

        return df, mappings_applied

    # ── CSV Preprocessing ────────────────────────────────────────────────────

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
        try:
            text = raw_bytes.decode('utf-8-sig').strip()
        except UnicodeDecodeError:
            text = raw_bytes.decode('latin-1').strip()

        lines = text.splitlines()
        if not lines:
            raise ValueError("The uploaded file is empty.")

        # Detect wrapped-quote format: each line is "col1,col2,..."
        sample = lines[0].strip()
        if sample.startswith('"') and sample.endswith('"') and ',' in sample[1:-1]:
            inner = sample[1:-1]
            if not inner.startswith('"'):
                lines = [
                    line.strip()[1:-1] if (line.strip().startswith('"') and line.strip().endswith('"'))
                    else line.strip()
                    for line in lines
                ]
                text = '\n'.join(lines)

        try:
            df = pd.read_csv(io.StringIO(text), dtype=str)
            df.columns = df.columns.str.strip()
            df = df.map(lambda x: x.strip() if isinstance(x, str) else x)
            df = df.dropna(how='all').reset_index(drop=True)
            return df
        except Exception as e:
            raise ValueError(f"Could not parse CSV file: {e}")

    # ── Core Validation Method ────────────────────────────────────────────────

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

        # ── Step 0: Normalize column names ───────────────────────────────────
        df, mappings = self.normalize_columns(df)

        # ── Step 1: Check required columns ───────────────────────────────────
        missing_cols = [c for c in REQUIRED_COLUMNS if c not in df.columns]
        if missing_cols:
            found_cols = list(df.columns)
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
                            f"Found columns: {', '.join(found_cols)}. "
                            f"Expected columns: {', '.join(REQUIRED_COLUMNS)}. "
                            f"The engine accepts both JobTread format (Cost Group, Cost Item) "
                            f"and GCHI format (Cost Group Name, Cost Item Name)."
                        ),
                        severity="error",
                    )
                ],
                summary={
                    "missing_columns": missing_cols,
                    "found_columns": found_cols,
                    "column_mappings": mappings,
                },
            )

        # Track optional columns presence
        has_unit_price = "Unit Price" in df.columns

        # ── Step 2: Row-by-row validation ─────────────────────────────────────
        for idx, row in df.iterrows():
            row_num = idx + 2  # +2 because idx is 0-based and row 1 is the header

            # ── 2a. Cost Group (Parent Cost Code) ────────────────────────────
            cost_group = str(row.get("Cost Group", "")).strip()
            if not cost_group:
                errors.append(ValidationError(
                    row=row_num,
                    column="Cost Group",
                    value="(empty)",
                    message="Cost Group cannot be empty.",
                ))
            elif cost_group not in self._valid_cost_codes:
                lower_map = {c.lower(): c for c in self._valid_cost_codes}
                suggestion = lower_map.get(cost_group.lower())
                hint = f" Did you mean '{suggestion}'?" if suggestion else ""

                is_numeric_code = bool(re.match(r'^\d{2,4}[-]?\d{0,4}$', cost_group))
                if is_numeric_code:
                    hint = (
                        " Note: The 'Cost Group' field requires the descriptive NAME "
                        "(e.g. 'General Conditions'), not the numeric code (e.g. '0100'). "
                        "Use the GCHI v8.4 Cost Code library to find the correct name."
                    )

                if not hint:
                    close_matches = [
                        cc for cc in self._valid_cost_groups
                        if cost_group.lower() in cc.lower() or cc.lower() in cost_group.lower()
                    ]
                    if close_matches:
                        hint = f" Similar Cost Groups found: {', '.join(close_matches[:3])}"

                errors.append(ValidationError(
                    row=row_num,
                    column="Cost Group",
                    value=cost_group,
                    message=f"'{cost_group}' is not a valid Cost Code in the GCHI v8.4 library.{hint}",
                ))

            # ── 2b. Cost Item ────────────────────────────────────────────────
            cost_item = str(row.get("Cost Item", "")).strip()
            if not cost_item:
                errors.append(ValidationError(
                    row=row_num,
                    column="Cost Item",
                    value="(empty)",
                    message="Cost Item cannot be empty.",
                ))
            elif cost_item not in self._valid_cost_codes:
                lower_map = {c.lower(): c for c in self._valid_cost_codes}
                suggestion = lower_map.get(cost_item.lower())
                hint = f" Did you mean '{suggestion}'?" if suggestion else ""

                if not hint:
                    close_matches = [
                        cc for cc in self._valid_cost_items
                        if cost_item.lower() in cc.lower() or cc.lower() in cost_item.lower()
                    ]
                    if close_matches:
                        hint = f" Similar Cost Items found: {', '.join(close_matches[:3])}"

                errors.append(ValidationError(
                    row=row_num,
                    column="Cost Item",
                    value=cost_item,
                    message=f"'{cost_item}' is not a valid Cost Code in the GCHI v8.4 library.{hint}",
                ))

            # ── 2c. Cost Group <-> Cost Item relationship check (warning) ────
            if (cost_group in self._valid_cost_groups and
                    cost_item in self._valid_cost_items):
                expected_parent = self._child_parent_map.get(cost_item)
                if expected_parent and expected_parent != cost_group:
                    warnings.append(ValidationError(
                        row=row_num,
                        column="Cost Group / Cost Item",
                        value=f"{cost_group} / {cost_item}",
                        message=(
                            f"Cost Item '{cost_item}' belongs to Cost Group "
                            f"'{expected_parent}', but was placed under '{cost_group}'. "
                            f"Verify the correct parent-child relationship."
                        ),
                        severity="warning",
                    ))

            # ── 2d. Cost Type ────────────────────────────────────────────────
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

            # ── 2e. Unit ─────────────────────────────────────────────────────
            unit = str(row.get("Unit", "")).strip()
            if not unit:
                errors.append(ValidationError(
                    row=row_num,
                    column="Unit",
                    value="(empty)",
                    message="Unit cannot be empty.",
                ))
            elif unit not in self._valid_units:
                lower_map = {u.lower(): u for u in self._valid_units}
                suggestion = lower_map.get(unit.lower())
                hint = f" Did you mean '{suggestion}'?" if suggestion else ""
                errors.append(ValidationError(
                    row=row_num,
                    column="Unit",
                    value=unit,
                    message=(
                        f"'{unit}' is not a valid Unit. "
                        f"Allowed values: {', '.join(sorted(self._valid_units))}.{hint}"
                    ),
                ))

            # ── 2f. Taxable consistency check (warning) ──────────────────────
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

            # ── 2g. Numeric field validation ─────────────────────────────────
            numeric_cols = ["Quantity", "Unit Cost"]
            if has_unit_price:
                numeric_cols.append("Unit Price")

            for num_col in numeric_cols:
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

            # ── 2h. Description should not be empty (warning) ────────────────
            description = str(row.get("Description", "")).strip()
            if not description:
                warnings.append(ValidationError(
                    row=row_num,
                    column="Description",
                    value="(empty)",
                    message="Description is empty. Consider adding a detailed description for clarity.",
                    severity="warning",
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
            "column_mappings": mappings,
            "has_unit_price": has_unit_price,
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
