import httpx
import respx

from flowbio.v2._pagination import PageIterator
from flowbio.v2._transport import HttpTransport

from tests.unit.v2.conftest import DEFAULT_BASE_URL


class TestPageIteratorIteration:

    @respx.mock
    def test_yields_all_items_from_single_page(self) -> None:
        respx.get(f"{DEFAULT_BASE_URL}/items").mock(
            return_value=httpx.Response(200, json={
                "count": 2,
                "items": [{"name": "a"}, {"name": "b"}],
            }),
        )

        transport = HttpTransport(DEFAULT_BASE_URL)
        pages = PageIterator(
            transport, "/items", items_key="items",
            item_factory=lambda d: d["name"],
        )

        assert list(pages) == ["a", "b"]

    @respx.mock
    def test_paginates_across_multiple_pages(self) -> None:
        route = respx.get(f"{DEFAULT_BASE_URL}/items")
        route.side_effect = [
            httpx.Response(200, json={
                "count": 3,
                "items": [{"name": "a"}, {"name": "b"}],
            }),
            httpx.Response(200, json={
                "count": 3,
                "items": [{"name": "c"}],
            }),
        ]

        transport = HttpTransport(DEFAULT_BASE_URL)
        pages = PageIterator(
            transport, "/items", items_key="items",
            item_factory=lambda d: d["name"],
        )

        assert list(pages) == ["a", "b", "c"]

    @respx.mock
    def test_fetches_pages_lazily(self) -> None:
        route = respx.get(f"{DEFAULT_BASE_URL}/items")
        route.side_effect = [
            httpx.Response(200, json={
                "count": 3,
                "items": [{"name": "a"}, {"name": "b"}],
            }),
            httpx.Response(200, json={
                "count": 3,
                "items": [{"name": "c"}],
            }),
        ]

        transport = HttpTransport(DEFAULT_BASE_URL)
        pages = PageIterator(
            transport, "/items", items_key="items",
            item_factory=lambda d: d["name"],
        )

        assert route.call_count == 0

        iterator = iter(pages)
        next(iterator)
        assert route.call_count == 1

        next(iterator)
        assert route.call_count == 1

        next(iterator)
        assert route.call_count == 2

    @respx.mock
    def test_empty_response_yields_nothing(self) -> None:
        respx.get(f"{DEFAULT_BASE_URL}/items").mock(
            return_value=httpx.Response(200, json={
                "count": 0,
                "items": [],
            }),
        )

        transport = HttpTransport(DEFAULT_BASE_URL)
        pages = PageIterator(
            transport, "/items", items_key="items",
            item_factory=lambda d: d["name"],
        )

        assert list(pages) == []


class TestPageIteratorLen:

    @respx.mock
    def test_returns_total_count(self) -> None:
        respx.get(f"{DEFAULT_BASE_URL}/items").mock(
            return_value=httpx.Response(200, json={
                "count": 5,
                "items": [{"name": "a"}],
            }),
        )

        transport = HttpTransport(DEFAULT_BASE_URL)
        pages = PageIterator(
            transport, "/items", items_key="items",
            item_factory=lambda d: d["name"],
        )

        assert len(pages) == 5

    @respx.mock
    def test_len_only_fetches_first_page(self) -> None:
        route = respx.get(f"{DEFAULT_BASE_URL}/items")
        route.side_effect = [
            httpx.Response(200, json={
                "count": 3,
                "items": [{"name": "a"}],
            }),
            httpx.Response(200, json={
                "count": 3,
                "items": [{"name": "b"}],
            }),
        ]

        transport = HttpTransport(DEFAULT_BASE_URL)
        pages = PageIterator(
            transport, "/items", items_key="items",
            item_factory=lambda d: d["name"],
        )

        len(pages)

        assert route.call_count == 1


class TestPageIteratorPageSize:

    @respx.mock
    def test_does_not_send_count_param_on_first_request_when_page_size_omitted(self) -> None:
        route = respx.get(f"{DEFAULT_BASE_URL}/items").mock(
            return_value=httpx.Response(200, json={
                "count": 1,
                "items": [{"name": "a"}],
            }),
        )

        transport = HttpTransport(DEFAULT_BASE_URL)
        pages = PageIterator(
            transport, "/items", items_key="items",
            item_factory=lambda d: d["name"],
        )
        list(pages)

        assert "count" not in str(route.calls[0].request.url)

    @respx.mock
    def test_infers_page_size_from_first_response(self) -> None:
        route = respx.get(f"{DEFAULT_BASE_URL}/items")
        route.side_effect = [
            httpx.Response(200, json={
                "count": 3,
                "items": [{"name": "a"}, {"name": "b"}],
            }),
            httpx.Response(200, json={
                "count": 3,
                "items": [{"name": "c"}],
            }),
        ]

        transport = HttpTransport(DEFAULT_BASE_URL)
        pages = PageIterator(
            transport, "/items", items_key="items",
            item_factory=lambda d: d["name"],
        )
        list(pages)

        assert "count" not in str(route.calls[0].request.url)
        assert route.calls[1].request.url.params["count"] == "2"

    @respx.mock
    def test_sends_count_param_when_page_size_specified(self) -> None:
        route = respx.get(f"{DEFAULT_BASE_URL}/items").mock(
            return_value=httpx.Response(200, json={
                "count": 1,
                "items": [{"name": "a"}],
            }),
        )

        transport = HttpTransport(DEFAULT_BASE_URL)
        pages = PageIterator(
            transport, "/items", items_key="items",
            item_factory=lambda d: d["name"], page_size=50,
        )
        list(pages)

        assert route.calls[0].request.url.params["count"] == "50"
