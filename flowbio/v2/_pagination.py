from __future__ import annotations

from collections.abc import Iterator, Sequence
from typing import TYPE_CHECKING, Callable, TypeVar, overload

if TYPE_CHECKING:
    from flowbio.v2._transport import HttpTransport

T = TypeVar("T")


class PageIterator(Sequence[T]):
    """A lazy, paginated sequence of items from the Flow API.

    Fetches pages on demand as you iterate or index into the sequence.
    The total count is available via ``len()`` without fetching all pages.

    Supports iteration, ``len()``, and indexing::

        projects = client.samples.get_owned_projects()

        # Iterate lazily — pages are fetched as needed
        for project in projects:
            print(project.name)

        # Get the total count (only fetches the first page)
        print(f"Total: {len(projects)}")

        # Convert to a list (fetches all pages)
        all_projects = list(projects)

    :param transport: The HTTP transport to use for requests.
    :param path: The API endpoint path.
    :param items_key: The key in the response JSON that contains the items.
    :param item_factory: A callable that converts a raw dict into the
        desired item type.
    :param page_size: The number of items to request per page. If not
        specified, the server's default page size is used.
    """

    def __init__(
        self,
        transport: HttpTransport,
        path: str,
        items_key: str,
        item_factory: Callable[[dict], T],
        page_size: int | None = None,
    ) -> None:
        self._transport = transport
        self._path = path
        self._items_key = items_key
        self._item_factory = item_factory
        self._page_size = page_size
        self._items: list[T] = []
        self._total_count: int | None = None
        self._next_page = 1
        self._exhausted = False

    def __len__(self) -> int:
        if self._total_count is None:
            self._fetch_page()
        return self._total_count  # type: ignore[return-value]

    def __iter__(self) -> Iterator[T]:
        index = 0
        while True:
            if index < len(self._items):
                yield self._items[index]
                index += 1
            elif self._exhausted:
                return
            else:
                self._fetch_page()

    @overload
    def __getitem__(self, index: int) -> T: ...
    @overload
    def __getitem__(self, index: slice) -> Sequence[T]: ...
    def __getitem__(self, index: int | slice) -> T | Sequence[T]:
        if isinstance(index, slice):
            self._fetch_all()
            return self._items[index]
        if index < 0:
            self._fetch_all()
            return self._items[index]
        while index >= len(self._items) and not self._exhausted:
            self._fetch_page()
        return self._items[index]

    def _fetch_page(self) -> None:
        if self._exhausted:
            return
        params: dict = {"page": self._next_page}
        if self._page_size is not None:
            params["count"] = self._page_size
        response = self._transport.get(self._path, params=params)
        self._total_count = response["count"]
        items = [self._item_factory(item) for item in response[self._items_key]]
        if self._page_size is None and items:
            self._page_size = len(items)
        self._items.extend(items)
        self._next_page += 1
        if len(self._items) >= self._total_count:
            self._exhausted = True

    def _fetch_all(self) -> None:
        while not self._exhausted:
            self._fetch_page()
