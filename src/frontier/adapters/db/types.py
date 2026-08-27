"""PostgreSQL `ltree` — ARCH ADR-14. SQLAlchemy has no built-in type for it."""

from __future__ import annotations

from typing import Any

from sqlalchemy import String
from sqlalchemy.types import TypeDecorator, UserDefinedType

from frontier.domain.hex.coordinates import HexAddr


class LTree(UserDefinedType[str]):
    cache_ok = True

    def get_col_spec(self, **_: Any) -> str:
        return "ltree"

    def bind_processor(self, dialect: Any) -> Any:
        return lambda value: value

    def result_processor(self, dialect: Any, coltype: Any) -> Any:
        return lambda value: value


class AddressPath(TypeDecorator[HexAddr]):
    """Stores a HexAddr as an ltree path and returns it as a domain value."""

    impl = LTree
    cache_ok = True

    def load_dialect_impl(self, dialect: Any) -> Any:
        if dialect.name == "postgresql":
            return dialect.type_descriptor(LTree())
        return dialect.type_descriptor(String(255))

    def process_bind_param(self, value: HexAddr | None, dialect: Any) -> str | None:
        return None if value is None else value.ltree()

    def process_result_value(self, value: str | None, dialect: Any) -> HexAddr | None:
        return None if value is None else HexAddr.parse(value)
