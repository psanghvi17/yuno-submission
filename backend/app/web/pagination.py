from __future__ import annotations

from dataclasses import dataclass
from math import ceil
from typing import Any, TypeVar

T = TypeVar("T")

DEFAULT_PER_PAGE = 10
MAX_PER_PAGE = 100


@dataclass
class Pagination:
    items: list[Any]
    page: int
    per_page: int
    total: int

    @property
    def total_pages(self) -> int:
        if self.total <= 0:
            return 0
        return ceil(self.total / self.per_page)

    @property
    def has_prev(self) -> bool:
        return self.page > 1 and self.total_pages > 0

    @property
    def has_next(self) -> bool:
        return self.page < self.total_pages

    @property
    def start_index(self) -> int:
        if self.total <= 0:
            return 0
        return (self.page - 1) * self.per_page + 1

    @property
    def end_index(self) -> int:
        if self.total <= 0:
            return 0
        return min(self.page * self.per_page, self.total)

    @property
    def show_controls(self) -> bool:
        return self.total_pages > 1

    @property
    def page_numbers(self) -> list[int | None]:
        total_pages = self.total_pages
        window = 2
        if total_pages <= 1:
            return [1] if total_pages == 1 else []

        pages: set[int] = {1, total_pages}
        for number in range(self.page - window, self.page + window + 1):
            if 1 <= number <= total_pages:
                pages.add(number)

        ordered = sorted(pages)
        result: list[int | None] = []
        previous = 0
        for number in ordered:
            if previous and number - previous > 1:
                result.append(None)
            result.append(number)
            previous = number
        return result


def parse_page(value: str | int | None, *, default: int = 1) -> int:
    if value is None or value == "":
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(1, parsed)


def offset_limit(page: int, per_page: int = DEFAULT_PER_PAGE) -> tuple[int, int]:
    safe_page = max(1, page)
    safe_per_page = max(1, min(per_page, MAX_PER_PAGE))
    return (safe_page - 1) * safe_per_page, safe_per_page


def paginate_slice(items: list[T], *, page: int, per_page: int = DEFAULT_PER_PAGE) -> Pagination[T]:
    total = len(items)
    safe_page = max(1, page)
    safe_per_page = max(1, min(per_page, MAX_PER_PAGE))
    if total == 0:
        return Pagination(items=[], page=1, per_page=safe_per_page, total=0)

    total_pages = ceil(total / safe_per_page)
    if safe_page > total_pages:
        safe_page = total_pages

    start = (safe_page - 1) * safe_per_page
    end = start + safe_per_page
    return Pagination(
        items=items[start:end],
        page=safe_page,
        per_page=safe_per_page,
        total=total,
    )


def preserve_query(request, *, exclude: frozenset[str] | set[str]) -> str:
    from urllib.parse import urlencode

    pairs: list[tuple[str, str]] = []
    for key, value in request.query_params.multi_items():
        if key not in exclude:
            pairs.append((key, value))
    return urlencode(pairs)


def build_pagination(
    items: list[T],
    *,
    total: int,
    page: int,
    per_page: int = DEFAULT_PER_PAGE,
) -> Pagination[T]:
    safe_page = max(1, page)
    safe_per_page = max(1, min(per_page, MAX_PER_PAGE))
    total_pages = ceil(total / safe_per_page) if total > 0 else 0
    if total_pages and safe_page > total_pages:
        safe_page = total_pages
    return Pagination(
        items=items,
        page=safe_page,
        per_page=safe_per_page,
        total=total,
    )
