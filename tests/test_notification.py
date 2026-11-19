
import importlib.util
import json
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest


# =====================================================
# LOAD NOTIFICATION CONSUMER
# =====================================================

@pytest.fixture
def consumer_module(monkeypatch):

    monkeypatch.setenv("RABBITMQ_USER", "test_user")
    monkeypatch.setenv("RABBITMQ_PASSWORD", "test_password")
    monkeypatch.setenv("POSTGRES_USER", "test_user")
    monkeypatch.setenv("POSTGRES_PASSWORD", "test_password")

    consumer_path = (
        Path(__file__).resolve().parents[1]
        / "services"
        / "notification-service"
        / "consumer.py"
    )

    spec = importlib.util.spec_from_file_location(
        "notification_consumer",
        consumer_path
    )

    consumer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(consumer)

    return consumer


# =====================================================
# UT-10: SAVE NOTIFICATION AND ACKNOWLEDGE MESSAGE
# =====================================================

def test_low_stock_notification_saved_and_acknowledged(
    consumer_module
):

    event = {
        "event_type": "LOW_STOCK",
        "product_id": 3,
        "product_name": "Monitor",
        "stock_quantity": 4,
        "reorder_level": 10
    }

    body = json.dumps(event).encode("utf-8")

    channel = MagicMock()

    method = MagicMock()
    method.delivery_tag = 1

    properties = MagicMock()

    with patch.object(
        consumer_module, "save_notification"
    ) as mock_save:

        operations = MagicMock()

        operations.attach_mock(
            mock_save, "save"
        )

        operations.attach_mock(
            channel.basic_ack, "ack"
        )

        consumer_module.process_message(
            channel,
            method,
            properties,
            body
        )

        mock_save.assert_called_once_with(event)

        channel.basic_ack.assert_called_once_with(
            delivery_tag=1
        )

        channel.basic_nack.assert_not_called()

        channel.basic_reject.assert_not_called()

        assert operations.mock_calls == [
            call.save(event),
            call.ack(delivery_tag=1)
        ]
