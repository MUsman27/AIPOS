from fastapi.testclient import TestClient

from app.server import app


class FakeItem:
    def __init__(self):
        self.item_code = "A100"
        self.description_en = "Widget"
        self.description_ur = "ویجیٹ"
        self.model = "M-1"
        self.purchase_price = 120.5


def test_parse_pdf_route_returns_extracted_items(monkeypatch):
    monkeypatch.setattr(
        "app.server.read_price_list",
        lambda path: ("Demo Manufacturer", [FakeItem()]),
    )

    client = TestClient(app)
    response = client.post(
        "/api/pdf/parse",
        files={"file": ("sample.pdf", b"%PDF-1.4\n", "application/pdf")},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "success"
    assert payload["manufacturer_name"] == "Demo Manufacturer"
    assert payload["items"][0]["item_code"] == "A100"


def test_local_api_token_is_required_when_configured(monkeypatch):
    monkeypatch.setenv("AIPOS_LOCAL_API_TOKEN", "test-launch-token")
    client = TestClient(app)

    assert client.get("/health").status_code == 401
    assert client.get("/health", headers={"X-AIPOS-Local-Token": "wrong"}).status_code == 401
    assert client.get(
        "/health", headers={"X-AIPOS-Local-Token": "test-launch-token"}
    ).status_code == 200

    preflight = client.options(
        "/health",
        headers={
            "Origin": "null",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "x-aipos-local-token",
        },
    )
    assert preflight.status_code == 200


def test_account_register_preflight_allows_local_web_origin():
    response = TestClient(app).options(
        "/account/register",
        headers={
            "Origin": "http://localhost:8084",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:8084"


def test_save_item_route_persists_product_payload():
    payload = {
        "name": "Widget",
        "sku": "A100",
        "manufacturer_name": "Demo Manufacturer",
        "cost_price": 120.5,
        "unit_price": 150.0,
    }

    with TestClient(app) as client:
        first = client.post("/api/items/save", json=payload)
        second = client.post("/api/items/save", json=payload)

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["status"] == "saved"
    assert second.json()["status"] == "saved"
    assert first.json()["item"]["name"] == "Widget"
    assert second.json()["item"]["name"] == "Widget"
