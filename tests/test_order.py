
import importlib.util
from pathlib import Path
from decimal import Decimal
from unittest.mock import MagicMock, patch, call

import pytest


# =====================================================
# LOAD ORDER SERVICE
# =====================================================

APP_PATH = (
    Path(__file__).resolve().parents[1]
    / "services"
    / "order-service"
    / "app.py"
)

spec = importlib.util.spec_from_file_location(
    "order_app",
    APP_PATH
)

order_app = importlib.util.module_from_spec(spec)
spec.loader.exec_module(order_app)


# =====================================================
# TEST FIXTURES
# =====================================================

@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("POSTGRES_USER", "test_user")
    monkeypatch.setenv("POSTGRES_PASSWORD", "test_password")

    order_app.app.config["TESTING"] = True

    return order_app.app.test_client()


@pytest.fixture
def mock_db():
    with patch.object(
        order_app.psycopg, "connect"
    ) as mock_connect:

        connection = MagicMock()
        cursor = MagicMock()

        mock_connect.return_value.__enter__.return_value = connection
        connection.cursor.return_value.__enter__.return_value = cursor

        yield mock_connect, connection, cursor


@pytest.fixture
def mock_inventory():
    with patch.object(
        order_app.requests, "post"
    ) as mock_post:

        yield mock_post


@pytest.fixture
def valid_order():
    return {
        "customer_name": "Test Customer",
        "items": [
            {"product_id": 1, "quantity": 2},
            {"product_id": 2, "quantity": 3}
        ]
    }


@pytest.fixture
def reservation_response():
    response = MagicMock()

    response.status_code = 200

    response.json.return_value = {
        "message": "All products reserved successfully",
        "items": [
            {
                "product_id": 1,
                "name": "Keyboard",
                "price": "2500.00",
                "quantity_reserved": 2,
                "remaining_stock": 23
            },
            {
                "product_id": 2,
                "name": "Mouse",
                "price": "1200.00",
                "quantity_reserved": 3,
                "remaining_stock": 9
            }
        ]
    }

    return response


# =====================================================
# UT-05: INVALID ORDER QUANTITY
# =====================================================

def test_invalid_order_quantity(
    client, mock_db, mock_inventory, valid_order
):

    mock_connect, connection, cursor = mock_db

    valid_order["items"][0]["quantity"] = -2

    response = client.post(
        "/orders",
        json=valid_order
    )

    assert response.status_code == 400

    assert response.get_json()["error"] == (
        "Invalid quantity"
    )

    mock_inventory.assert_not_called()
    mock_connect.assert_not_called()


# =====================================================
# UT-06: SUCCESSFUL ORDER
# =====================================================

def test_successful_order(
    client,
    mock_db,
    mock_inventory,
    valid_order,
    reservation_response
):

    mock_connect, connection, cursor = mock_db

    mock_inventory.return_value = reservation_response

    cursor.fetchone.return_value = (101,)

    response = client.post(
        "/orders",
        json=valid_order
    )

    assert response.status_code == 201

    data = response.get_json()

    assert data["message"] == "Order placed successfully"
    assert data["order_id"] == 101
    assert data["customer_name"] == "Test Customer"
    assert data["status"] == "CONFIRMED"
    assert data["total_amount"] == "8600.00"

    assert data["items"] == (
        reservation_response.json.return_value["items"]
    )

    mock_inventory.assert_called_once_with(
        "http://inventory-service:5001/reservations",
        json={"items": valid_order["items"]},
        timeout=5
    )

    mock_connect.assert_called_once()

    assert mock_connect.call_args.kwargs["dbname"] == (
        "orders_db"
    )

    assert cursor.execute.call_count == 3

    # Verify order insertion
    assert cursor.execute.call_args_list[0].args[1] == (
        "Test Customer",
        Decimal("8600.00")
    )

    assert "'CONFIRMED'" in (
        cursor.execute.call_args_list[0].args[0]
    )

    # Verify Keyboard order item insertion
    assert cursor.execute.call_args_list[1].args[1] == (
        101,
        1,
        2,
        Decimal("2500.00")
    )

    # Verify Mouse order item insertion
    assert cursor.execute.call_args_list[2].args[1] == (
        101,
        2,
        3,
        Decimal("1200.00")
    )


# =====================================================
# UT-07: INSUFFICIENT INVENTORY
# =====================================================

def test_order_rejected_when_stock_is_insufficient(
    client, mock_db, mock_inventory, valid_order
):

    mock_connect, connection, cursor = mock_db

    inventory_response = MagicMock()

    inventory_response.status_code = 409

    inventory_response.json.return_value = {
        "error": "Insufficient stock",
        "product_id": 1
    }

    mock_inventory.return_value = inventory_response

    response = client.post(
        "/orders",
        json=valid_order
    )

    assert response.status_code == 409

    assert response.get_json() == {
        "error": "Insufficient stock",
        "product_id": 1
    }

    mock_inventory.assert_called_once_with(
        "http://inventory-service:5001/reservations",
        json={"items": valid_order["items"]},
        timeout=5
    )

    mock_connect.assert_not_called()


# =====================================================
# UT-08: DATABASE FAILURE AND STOCK RELEASE
# =====================================================

def test_database_failure_releases_stock(
    client,
    mock_db,
    mock_inventory,
    valid_order,
    reservation_response
):

    mock_connect, connection, cursor = mock_db

    release_response = MagicMock()
    release_response.status_code = 200

    mock_inventory.side_effect = [
        reservation_response,
        release_response
    ]

    cursor.fetchone.return_value = (101,)

    cursor.execute.side_effect = [
        None,
        order_app.psycopg.Error(
            "Simulated database failure"
        )
    ]

    response = client.post(
        "/orders",
        json=valid_order
    )

    assert response.status_code == 500

    assert response.get_json()["error"] == (
        "Order could not be saved"
    )

    mock_connect.assert_called_once()

    assert cursor.execute.call_count == 2

    assert mock_inventory.call_count == 2

    assert mock_inventory.call_args_list == [
        call(
            "http://inventory-service:5001/reservations",
            json={"items": valid_order["items"]},
            timeout=5
        ),
        call(
            "http://inventory-service:5001/reservations/release",
            json={"items": valid_order["items"]},
            timeout=5
        )
    ]


# =====================================================
# UT-09: INVENTORY SERVICE UNAVAILABLE
# =====================================================

def test_order_rejected_when_inventory_is_unavailable(
    client, mock_db, mock_inventory, valid_order
):

    mock_connect, connection, cursor = mock_db

    mock_inventory.side_effect = (
        order_app.requests.exceptions.ConnectionError(
            "Simulated Inventory Service failure"
        )
    )

    response = client.post(
        "/orders",
        json=valid_order
    )

    assert response.status_code == 503

    assert response.get_json()["error"] == (
        "Inventory Service unavailable"
    )

    mock_inventory.assert_called_once_with(
        "http://inventory-service:5001/reservations",
        json={"items": valid_order["items"]},
        timeout=5
    )

    mock_connect.assert_not_called()
