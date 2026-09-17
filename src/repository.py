from __future__ import annotations
import csv
from functools import lru_cache
from pathlib import Path
from typing import Any
DATA_DIR=Path(__file__).resolve().parents[1]/"data"
def _convert(value:str)->Any:
    if value=="":return ""
    for caster in (int,float):
        try:return caster(value)
        except ValueError:pass
    return value
@lru_cache(maxsize=None)
def load_table(name:str)->list[dict[str,Any]]:
    with (DATA_DIR/f"{name}.csv").open("r",encoding="utf-8-sig",newline="") as f:
        return [{k:_convert(v) for k,v in row.items()} for row in csv.DictReader(f)]
def table_index(name:str,key:str)->dict[str,dict[str,Any]]:
    return {str(row[key]):row for row in load_table(name)}
