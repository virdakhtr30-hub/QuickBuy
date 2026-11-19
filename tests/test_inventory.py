
import importlib.util
from pathlib import Path
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest


# =====================================================
# LOAD INVENTORY SERVICE
# =====================================================

APP_PATH = (
    Path(__file__).resolve().parents[1]
    / "services"
    / "inventory-service"
    / "app.py"
)

spec = importlib.util.spec_from_file_location(
    "inventory_app",
    APP_PATH
)

inventory_app = importlib.util.module_from_spec(spec)
spec.loader.exec_module(inventory_app)


# =====================================================
# TEST FIXTURES
# =====================================================

@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("POSTGRES_USER", "test_user")
    monkeypatch.setenv("POSTGRES_PASSWORD", "test_password")

    inventory_app.app.config["TESTING"] = True

    return inventory_app.app.test_client()


@pytest.fixture
def mock_db():
    with patch.object(
        inventory_app.psycopg, "connect"
    ) as mock_connect:

        connection = MagicMock()
        cursor = MagicMock()

        mock_connect.return_value.__enter__.return_value = connection
        connection.cursor.return_value.__enter__.return_value = cursor

        yield connection, cursor


# =====================================================
# UT-01: SUCCESSFUL BATCH RESERVATION
# =====================================================

def test_successful_reservation(client, mock_db):

    connection, cursor = mock_db

    cursor.fetchone.side_effect = [
        {
            "product_id": 1,
            "name": "Keyboard",
            "price": Decimal("2500.00"),
            "stock_quantity": 23,
            "reorder_level": 5
        },
        {
            "product_id": 2,
            "name": "Mouse",
            "price": Decimal("1200.00"),
            "stock_quantity": 11,
            "reorder_level": 5
        }
    ]

    with patch.object(
        inventory_app, "publish_low_stock_event"
    ) as mock_publish:

        response = client.post(
            "/reservations",
            json={
                "items": [
                    {"product_id": 1, "quantity": 2},
                    {"product_id": 2, "quantity": 1}
                ]
            }
        )

        assert response.status_code == 200

        data = response.get_json()

        assert data["message"] == (
            "All products reserved successfully"
        )

        assert len(data["items"]) == 2

        assert data["items"][0] == {
            "product_id": 1,
            "name": "Keyboard",
            "price": "2500.00",
            "quantity_reserved": 2,
            "remaining_stock": 23
        }

        assert data["items"][1] == {
            "product_id": 2,
            "name": "Mouse",
            "price": "1200.00",
            "quantity_reserved": 1,
            "remaining_stock": 11
        }

        assert cursor.execute.call_count == 2

        assert cursor.execute.call_args_list[0].args[1] == (
            2, 1, 2
        )

        assert cursor.execute.call_args_list[1].args[1] == (
            1, 2, 1
        )

        connection.rollback.assert_not_called()
        mock_publish.assert_not_called()


# =====================================================
# UT-02: INSUFFICIENT STOCK AND ROLLBACK
# =====================================================

def test_insufficient_stock_rolls_back(client, mock_db):

    connection, cursor = mock_db

    cursor.fetchone.side_effect = [
        {
            "product_id": 1,
            "name": "Keyboard",
            "price": Decimal("2500.00"),
            "stock_quantity": 4,
            "reorder_level": 5
        },
        None,
        {"product_id": 2}
    ]

    with patch.object(
        inventory_app, "publish_low_stock_event"
    ) as mock_publish:

        response = client.post(
            "/reservations",
            json={
                "items": [
                    {"product_id": 1, "quantity": 2},
                    {"product_id": 2, "quantity": 100}
                ]
            }
        )

        assert response.status_code == 409

        data = response.get_json()

        assert data["error"] == "Insufficient stock"
        assert data["product_id"] == 2

        assert cursor.execute.call_count == 3

        connection.rollback.assert_called_once()
        mock_publish.assert_not_called()


# =====================================================
# UT-03: LOW-STOCK EVENT
# =====================================================

def test_low_stock_event_published(client, mock_db):

    connection, cursor = mock_db

    product = {
        "product_id": 3,
        "name": "Monitor",
        "price": Decimal("35000.00"),
        "stock_quantity": 10,
        "reorder_level": 10
    }

    cursor.fetchone.return_value = product

    with patch.object(
        inventory_app, "publish_low_stock_event"
    ) as mock_publish:

        response = client.post(
            "/reservations",
            json={
                "items": [
                    {"product_id": 3, "quantity": 1}
                ]
            }
        )

        assert response.status_code == 200

        assert response.get_json()["items"][0][
            "remaining_stock"
        ] == 10

        mock_publish.assert_called_once_with(product)


# =====================================================
# UT-04: NO LOW-STOCK EVENT
# =====================================================

def test_no_event_when_stock_is_sufficient(client, mock_db):

    connection, cursor = mock_db

    cursor.fetchone.return_value = {
        "product_id": 1,
        "name": "Keyboard",
        "price": Decimal("2500.00"),
        "stock_quantity": 6,
        "reorder_level": 5
    }

    with patch.object(
        inventory_app, "publish_low_stock_event"
    ) as mock_publish:

        response = client.post(
            "/reservations",
            json={
                "items": [
                    {"product_id": 1, "quantity": 1}
                ]
            }
        )

        assert response.status_code == 200
        mock_publish.assert_not_called()
