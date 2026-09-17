from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any, Sequence

import pandas as pd

from ..config import RulesConfig, load_rules
from ..models import (
    DataQualityIssue,
    DataQualitySeverity,
    ExcelImportResult,
    FieldMapping,
    ImportStatus,
)


def suggest_field_mapping(columns: Sequence[str], target_fields: Sequence[str], *, rules: RulesConfig | None = None) -> dict[str, str]:
    cfg = rules or load_rules()
    normalized = {str(column).strip().lower(): str(column) for column in columns}
    mapping: dict[str, str] = {}
    for target in target_fields:
        aliases = [target, *cfg.excel_import.aliases.get(target, [])]
        for alias in aliases:
            source = normalized.get(str(alias).strip().lower())
            if source is not None:
                mapping[target] = source
                break
    return mapping


def import_excel(
    path: str | Path,
    *,
    sheet_name: str,
    mappings: Sequence[FieldMapping],
    data_version: str,
    rules: RulesConfig | None = None,
) -> ExcelImportResult:
    cfg = rules or load_rules()
    file_path = Path(path)
    if file_path.suffix.lower() not in cfg.excel_import.allowed_extensions:
        raise ValueError(f"unsupported Excel extension {file_path.suffix}")
    frame = pd.read_excel(file_path, sheet_name=sheet_name)
    if len(frame) > cfg.excel_import.maximum_rows:
        raise ValueError("Excel row count exceeds configured limit")
    issues: list[DataQualityIssue] = []
    mapped_fields = {mapping.target_field: mapping.source_column for mapping in mappings if mapping.source_column in frame.columns}
    missing = [mapping.target_field for mapping in mappings if mapping.required and mapping.source_column not in frame.columns]
    for field in missing:
        issues.append(DataQualityIssue(
            code="MISSING_REQUIRED_FIELD", severity=DataQualitySeverity.BLOCKING,
            message=f"Excel映射缺少必填字段 {field}", table=sheet_name,
            field=field, blocking=True, impact="导入被阻断",
        ))
    rows: list[dict[str, Any]] = []
    if not missing:
        for row_number, (_, source_row) in enumerate(frame.iterrows(), start=2):
            output: dict[str, Any] = {}
            for mapping in mappings:
                if mapping.source_column not in frame.columns:
                    continue
                value = source_row[mapping.source_column]
                if pd.isna(value):
                    value = None
                try:
                    if value is not None and mapping.data_type == "float":
                        value = float(value)
                    elif value is not None and mapping.data_type == "int":
                        value = int(value)
                    elif value is not None and mapping.data_type == "date":
                        value = pd.to_datetime(value).date()
                    elif value is not None:
                        value = str(value).strip()
                except (TypeError, ValueError, OverflowError):
                    issues.append(DataQualityIssue(
                        code="INVALID_FIELD_TYPE", severity=DataQualitySeverity.BLOCKING,
                        message=f"字段 {mapping.target_field} 无法转换为 {mapping.data_type}",
                        table=sheet_name, row_index=row_number, field=mapping.target_field,
                        value=str(value), blocking=True, impact="该行不能导入",
                    ))
                output[mapping.target_field] = value
            rows.append(output)
    blocked = bool(missing) or any(issue.blocking for issue in issues)
    return ExcelImportResult(
        file_name=file_path.name, sheet_name=sheet_name,
        status=ImportStatus.BLOCKED if blocked else ImportStatus.IMPORTED,
        row_count=len(frame), mapped_fields=mapped_fields,
        unmapped_required_fields=missing, rows=[] if blocked else rows,
        issues=issues, data_version=data_version,
    )
