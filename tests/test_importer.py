import pytest

from app.errors import ConflictError, ValidationError
from app.services.importer import (
    import_csv,
    infer_column_type,
    sanitize_column_name,
)


class TestSanitizeColumnName:
    def test_spaces_to_underscores(self) -> None:
        assert sanitize_column_name("first name") == "first_name"

    def test_special_chars_stripped(self) -> None:
        assert sanitize_column_name("price ($)") == "price"

    def test_leading_digits_stripped(self) -> None:
        assert sanitize_column_name("123abc") == "abc"

    def test_uppercase_to_lowercase(self) -> None:
        assert sanitize_column_name("FirstName") == "firstname"

    def test_empty_raises(self) -> None:
        with pytest.raises(ValidationError):
            sanitize_column_name("")

    def test_only_special_chars_raises(self) -> None:
        with pytest.raises(ValidationError):
            sanitize_column_name("$$$")

    def test_unicode_sanitized(self) -> None:
        assert sanitize_column_name("café") == "caf"

    def test_multiple_underscores_collapsed(self) -> None:
        assert sanitize_column_name("a  b") == "a_b"


class TestInferColumnType:
    def test_all_ints(self) -> None:
        assert infer_column_type(["1", "2", "3"]) == "INTEGER"

    def test_mix_int_float(self) -> None:
        assert infer_column_type(["1", "2.5", "3"]) == "REAL"

    def test_any_text(self) -> None:
        assert infer_column_type(["1", "hello", "3"]) == "TEXT"

    def test_empty_list(self) -> None:
        assert infer_column_type([]) == "TEXT"

    def test_all_empty_strings(self) -> None:
        assert infer_column_type(["", "", ""]) == "TEXT"


class TestImportCsv:
    async def test_creates_table(self, db, sample_csv) -> None:  # noqa: ANN001
        meta = await import_csv(db, "people", sample_csv)
        assert meta["name"] == "people"
        assert meta["row_count"] == 5
        assert "name" in meta["columns"]
        assert "age" in meta["columns"]
        assert "score" in meta["columns"]

    async def test_correct_column_types(self, db, sample_csv) -> None:  # noqa: ANN001
        meta = await import_csv(db, "typed", sample_csv)
        assert meta["columns"]["name"] == "TEXT"
        assert meta["columns"]["age"] == "INTEGER"
        assert meta["columns"]["score"] == "REAL"

    async def test_duplicate_name_raises_conflict(self, db, sample_csv) -> None:  # noqa: ANN001
        await import_csv(db, "dup", sample_csv)
        with pytest.raises(ConflictError):
            await import_csv(db, "dup", sample_csv)

    async def test_overwrite_replaces_data(self, db, sample_csv) -> None:  # noqa: ANN001
        await import_csv(db, "overwrite", sample_csv)
        new_csv = b"x,y\n1,2\n3,4"
        meta = await import_csv(db, "overwrite", new_csv, overwrite=True)
        assert meta["row_count"] == 2
        assert meta["columns"] == {"x": "INTEGER", "y": "INTEGER"}

    async def test_invalid_name_raises(self, db, sample_csv) -> None:  # noqa: ANN001
        with pytest.raises(ValidationError):
            await import_csv(db, "123bad", sample_csv)

    async def test_reserved_name_raises(self, db, sample_csv) -> None:  # noqa: ANN001
        with pytest.raises(ValidationError):
            await import_csv(db, "_collections_meta", sample_csv)

    async def test_empty_csv_raises(self, db) -> None:  # noqa: ANN001
        with pytest.raises(ValidationError):
            await import_csv(db, "empty", b"")

    async def test_duplicate_columns_raises(self, db) -> None:  # noqa: ANN001
        csv_data = b"name,name\nAlice,Bob"
        with pytest.raises(ValidationError, match="Duplicate"):
            await import_csv(db, "dupcol", csv_data)
