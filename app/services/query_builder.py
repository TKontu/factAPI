import re
from dataclasses import dataclass, field


@dataclass
class QueryResult:
    select_sql: str
    count_sql: str
    parameters: list[object]
    count_parameters: list[object]
    errors: list[str] = field(default_factory=list)


META_PARAMS = {"_sort", "_limit", "_offset", "_fields", "_q", "_search"}

OPERATORS: dict[str, str] = {
    "gt": ">",
    "lt": "<",
    "gte": ">=",
    "lte": "<=",
    "like": "LIKE",
    "in": "IN",
}

_JSON_PATH_RE = re.compile(r"^[a-zA-Z0-9_.]+$")


def _is_valid_column(name: str, columns: dict[str, str]) -> bool:
    return name == "_id" or name in columns


def _build_search_clause(
    term: str, columns: dict[str, str]
) -> tuple[str, list[object]]:
    or_parts: list[str] = []
    params: list[object] = []
    for col_name, col_type in columns.items():
        escaped = _escape_ident(col_name)
        if col_type.upper() in ("TEXT", "JSON"):
            or_parts.append(f"{escaped} LIKE ?")
        else:
            or_parts.append(f"CAST({escaped} AS TEXT) LIKE ?")
        params.append(f"%{term}%")
    return f"({' OR '.join(or_parts)})", params


def _escape_ident(name: str) -> str:
    return f"[{name}]"


def _resolve_column(
    name: str, columns: dict[str, str], errors: list[str], context: str = "filter"
) -> str | None:
    if _is_valid_column(name, columns):
        return _escape_ident(name)

    if "." in name:
        base, json_path = name.split(".", 1)
        if not _is_valid_column(base, columns):
            errors.append(f"Unknown {context} column: {name}")
            return None
        col_type = columns.get(base, "")
        if col_type.upper() != "JSON":
            errors.append(f"Column '{base}' is not a JSON column")
            return None
        if not _JSON_PATH_RE.match(json_path):
            errors.append(f"Invalid JSON path: {json_path}")
            return None
        return f"json_extract({_escape_ident(base)}, '$.{json_path}')"

    errors.append(f"Unknown {context} column: {name}")
    return None


def build_query(
    table: str,
    columns: dict[str, str],
    params: dict[str, str],
    default_limit: int = 100,
    max_limit: int = 1000,
) -> QueryResult:
    errors: list[str] = []
    where_clauses: list[str] = []
    where_params: list[object] = []

    # Separate meta params from filter params
    meta: dict[str, str] = {}
    filters: dict[str, str] = {}
    for key, value in params.items():
        if key in META_PARAMS:
            meta[key] = value
        else:
            filters[key] = value

    # _fields → SELECT clause
    if "_fields" in meta:
        field_names = [f.strip() for f in meta["_fields"].split(",")]
        select_parts: list[str] = []
        for f in field_names:
            if _is_valid_column(f, columns):
                select_parts.append(_escape_ident(f))
            elif "." in f:
                base, json_path = f.split(".", 1)
                if not _is_valid_column(base, columns):
                    errors.append(f"Unknown field: {f}")
                elif columns.get(base, "").upper() != "JSON":
                    errors.append(f"Column '{base}' is not a JSON column")
                elif not _JSON_PATH_RE.match(json_path):
                    errors.append(f"Invalid JSON path: {json_path}")
                else:
                    select_parts.append(
                        f"json_extract({_escape_ident(base)}, '$.{json_path}') AS \"{f}\""
                    )
            else:
                errors.append(f"Unknown field: {f}")
        select_cols = ", ".join(select_parts) if select_parts else "*"
    else:
        all_cols = ["_id", *columns.keys()]
        select_cols = ", ".join(_escape_ident(c) for c in all_cols)

    # Filter params
    for key, value in filters.items():
        parts = key.rsplit("__", 1)
        col_name = parts[0]
        op_name = parts[1] if len(parts) == 2 else None

        col_expr = _resolve_column(col_name, columns, errors)
        if col_expr is None:
            continue

        is_json = col_expr.startswith("json_extract(")
        param_placeholder = (
            "CAST(? AS NUMERIC)"
            if is_json and op_name in ("gt", "lt", "gte", "lte")
            else "?"
        )

        if op_name is None:
            where_clauses.append(f"{col_expr} = ?")
            where_params.append(value)
        elif op_name == "in":
            values = [v.strip() for v in value.split(",")]
            placeholders = ", ".join("?" for _ in values)
            where_clauses.append(f"{col_expr} IN ({placeholders})")
            where_params.extend(values)
        elif op_name in OPERATORS:
            where_clauses.append(f"{col_expr} {OPERATORS[op_name]} {param_placeholder}")
            where_params.append(value)
        else:
            errors.append(f"Unknown operator: {op_name}")

    # _q → full-text search on TEXT and JSON columns
    if "_q" in meta:
        term = meta["_q"]
        text_cols = [
            name for name, dtype in columns.items() if dtype.upper() in ("TEXT", "JSON")
        ]
        if text_cols:
            or_clauses = [f"{_escape_ident(c)} LIKE ?" for c in text_cols]
            where_clauses.append(f"({' OR '.join(or_clauses)})")
            where_params.extend(f"%{term}%" for _ in text_cols)

    # _search → universal search across ALL columns
    if "_search" in meta:
        terms = meta["_search"].split()
        for term in terms:
            clause, search_params = _build_search_clause(term, columns)
            where_clauses.append(clause)
            where_params.extend(search_params)

    # WHERE clause
    where_sql = f" WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

    # _sort → ORDER BY
    order_sql = ""
    if "_sort" in meta:
        sort_field = meta["_sort"]
        if sort_field.startswith("-"):
            direction = "DESC"
            sort_col = sort_field[1:]
        else:
            direction = "ASC"
            sort_col = sort_field
        sort_expr = _resolve_column(sort_col, columns, errors, context="sort")
        if sort_expr is not None:
            order_sql = f" ORDER BY {sort_expr} {direction}"

    # _limit and _offset
    try:
        limit = int(meta.get("_limit", str(default_limit)))
    except (ValueError, TypeError):
        limit = default_limit
    limit = max(1, min(limit, max_limit))

    try:
        offset = int(meta.get("_offset", "0"))
    except (ValueError, TypeError):
        offset = 0
    offset = max(0, offset)

    # Build final SQL
    select_sql = f"SELECT {select_cols} FROM {_escape_ident(table)}{where_sql}{order_sql} LIMIT ? OFFSET ?"
    count_sql = f"SELECT COUNT(*) AS total FROM {_escape_ident(table)}{where_sql}"

    count_parameters = list(where_params)
    parameters = list(where_params) + [limit, offset]

    return QueryResult(
        select_sql=select_sql,
        count_sql=count_sql,
        parameters=parameters,
        count_parameters=count_parameters,
        errors=errors,
    )
