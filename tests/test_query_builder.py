from app.services.query_builder import build_query

COLUMNS = {
    "name": "TEXT",
    "age": "INTEGER",
    "score": "REAL",
    "country": "TEXT",
}


class TestDefaultQuery:
    def test_default_selects_all_columns_with_id(self) -> None:
        result = build_query("people", COLUMNS, {})
        assert "[_id]" in result.select_sql
        assert "[name]" in result.select_sql
        assert "[age]" in result.select_sql
        assert "[score]" in result.select_sql
        assert "[country]" in result.select_sql

    def test_default_limit_and_offset(self) -> None:
        result = build_query("people", COLUMNS, {})
        assert result.parameters[-2] == 100  # default limit
        assert result.parameters[-1] == 0  # default offset

    def test_count_query_has_no_limit(self) -> None:
        result = build_query("people", COLUMNS, {})
        assert "LIMIT" not in result.count_sql
        assert "OFFSET" not in result.count_sql

    def test_no_errors(self) -> None:
        result = build_query("people", COLUMNS, {})
        assert result.errors == []

    def test_count_parameters_empty_for_no_filters(self) -> None:
        result = build_query("people", COLUMNS, {})
        assert result.count_parameters == []


class TestFieldsSelection:
    def test_valid_fields_subset(self) -> None:
        result = build_query("people", COLUMNS, {"_fields": "name,age"})
        assert "[name]" in result.select_sql
        assert "[age]" in result.select_sql
        assert "[country]" not in result.select_sql

    def test_id_accepted_as_field(self) -> None:
        result = build_query("people", COLUMNS, {"_fields": "_id,name"})
        assert "[_id]" in result.select_sql
        assert result.errors == []

    def test_invalid_field_produces_error(self) -> None:
        result = build_query("people", COLUMNS, {"_fields": "name,nonexistent"})
        assert len(result.errors) == 1
        assert "nonexistent" in result.errors[0]


class TestExactMatchFilter:
    def test_single_exact_match(self) -> None:
        result = build_query("people", COLUMNS, {"country": "Japan"})
        assert "[country] = ?" in result.select_sql
        assert "Japan" in result.count_parameters

    def test_multiple_filters_and_together(self) -> None:
        result = build_query("people", COLUMNS, {"country": "Japan", "age": "30"})
        assert "AND" in result.select_sql
        assert len(result.count_parameters) == 2


class TestOperatorFilters:
    def test_gt(self) -> None:
        result = build_query("people", COLUMNS, {"age__gt": "30"})
        assert "[age] > ?" in result.select_sql
        assert "30" in result.count_parameters

    def test_lt(self) -> None:
        result = build_query("people", COLUMNS, {"age__lt": "30"})
        assert "[age] < ?" in result.select_sql

    def test_gte(self) -> None:
        result = build_query("people", COLUMNS, {"age__gte": "30"})
        assert "[age] >= ?" in result.select_sql

    def test_lte(self) -> None:
        result = build_query("people", COLUMNS, {"age__lte": "30"})
        assert "[age] <= ?" in result.select_sql

    def test_like(self) -> None:
        result = build_query("people", COLUMNS, {"name__like": "%Ali%"})
        assert "[name] LIKE ?" in result.select_sql

    def test_in_multiple_values(self) -> None:
        result = build_query("people", COLUMNS, {"country__in": "Japan,USA,UK"})
        assert "IN" in result.select_sql
        assert "?, ?, ?" in result.select_sql
        assert "Japan" in result.count_parameters
        assert "USA" in result.count_parameters
        assert "UK" in result.count_parameters

    def test_in_single_value(self) -> None:
        result = build_query("people", COLUMNS, {"country__in": "Japan"})
        assert "IN (?)" in result.select_sql

    def test_unknown_column_produces_error(self) -> None:
        result = build_query("people", COLUMNS, {"bogus": "value"})
        assert len(result.errors) == 1
        assert "bogus" in result.errors[0]

    def test_sql_injection_column_rejected(self) -> None:
        result = build_query("people", COLUMNS, {"name; DROP TABLE": "x"})
        assert len(result.errors) == 1


class TestSorting:
    def test_ascending(self) -> None:
        result = build_query("people", COLUMNS, {"_sort": "age"})
        assert "ORDER BY [age] ASC" in result.select_sql

    def test_descending(self) -> None:
        result = build_query("people", COLUMNS, {"_sort": "-age"})
        assert "ORDER BY [age] DESC" in result.select_sql

    def test_invalid_sort_column_produces_error(self) -> None:
        result = build_query("people", COLUMNS, {"_sort": "bogus"})
        assert len(result.errors) == 1
        assert "bogus" in result.errors[0]

    def test_id_accepted_for_sort(self) -> None:
        result = build_query("people", COLUMNS, {"_sort": "_id"})
        assert "ORDER BY [_id] ASC" in result.select_sql
        assert result.errors == []


class TestPagination:
    def test_custom_limit_and_offset(self) -> None:
        result = build_query("people", COLUMNS, {"_limit": "50", "_offset": "10"})
        assert result.parameters[-2] == 50
        assert result.parameters[-1] == 10

    def test_limit_clamped_to_max(self) -> None:
        result = build_query("people", COLUMNS, {"_limit": "9999"}, max_limit=1000)
        assert result.parameters[-2] == 1000

    def test_limit_clamped_to_one(self) -> None:
        result = build_query("people", COLUMNS, {"_limit": "0"})
        assert result.parameters[-2] == 1

    def test_negative_limit_clamped(self) -> None:
        result = build_query("people", COLUMNS, {"_limit": "-5"})
        assert result.parameters[-2] == 1

    def test_negative_offset_clamped(self) -> None:
        result = build_query("people", COLUMNS, {"_offset": "-5"})
        assert result.parameters[-1] == 0

    def test_non_numeric_limit_uses_default(self) -> None:
        result = build_query("people", COLUMNS, {"_limit": "abc"}, default_limit=50)
        assert result.parameters[-2] == 50

    def test_non_numeric_offset_uses_default(self) -> None:
        result = build_query("people", COLUMNS, {"_offset": "abc"})
        assert result.parameters[-1] == 0


class TestFullTextSearch:
    def test_q_generates_or_for_text_columns(self) -> None:
        result = build_query("people", COLUMNS, {"_q": "ali"})
        assert "[name] LIKE ?" in result.select_sql
        assert "[country] LIKE ?" in result.select_sql
        assert "OR" in result.select_sql
        # Should NOT include non-text columns
        assert "[age] LIKE" not in result.select_sql
        assert "[score] LIKE" not in result.select_sql
        assert "%ali%" in result.count_parameters

    def test_q_combined_with_filter(self) -> None:
        result = build_query("people", COLUMNS, {"_q": "ali", "age": "30"})
        assert "AND" in result.select_sql
        assert "OR" in result.select_sql


class TestCombinedQueries:
    def test_all_params_together(self) -> None:
        params = {
            "country": "Japan",
            "age__gt": "25",
            "_sort": "-score",
            "_limit": "10",
            "_offset": "5",
            "_fields": "name,score",
            "_q": "tok",
        }
        result = build_query("people", COLUMNS, params)
        assert result.errors == []
        assert "[name]" in result.select_sql
        assert "[score]" in result.select_sql
        assert "[country] = ?" in result.select_sql
        assert "[age] > ?" in result.select_sql
        assert "ORDER BY [score] DESC" in result.select_sql
        assert result.parameters[-2] == 10
        assert result.parameters[-1] == 5

    def test_count_params_match_where_params(self) -> None:
        params = {"country": "Japan", "age__gt": "25"}
        result = build_query("people", COLUMNS, params)
        # count_parameters should be where_params only
        assert result.count_parameters == result.parameters[:-2]
