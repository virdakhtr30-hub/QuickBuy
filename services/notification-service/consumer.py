
import json
import time

import pika
import psycopg
import os


# RABBITMQ_HOST = "localhost"
RABBITMQ_HOST = "rabbitmq"
RABBITMQ_USER = os.environ["RABBITMQ_USER"]
RABBITMQ_PASSWORD = os.environ["RABBITMQ_PASSWORD"]
QUEUE_NAME = "low_stock_queue"


def save_notification(event):
    product_id = event["product_id"]
    product_name = event["product_name"]
    stock_quantity = event["stock_quantity"]
    reorder_level = event["reorder_level"]

    message = (
        f"Low Stock Alert: {product_name} has only "
        f"{stock_quantity} units remaining. "
        f"Reorder level is {reorder_level}."
    )

    with psycopg.connect(
        # host="localhost",
        # port=5433,
        host="postgres",
        port=5432,
        dbname="notifications_db",
        user=os.environ["POSTGRES_USER"],
        password=os.environ["POSTGRES_PASSWORD"]
    ) as conn:

        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO notifications (
                    product_id,
                    product_name,
                    stock_quantity,
                    reorder_level,
                    message
                )
                VALUES (%s, %s, %s, %s, %s)
                """,
                (
                    product_id,
                    product_name,
                    stock_quantity,
                    reorder_level,
                    message
                )
            )

    print(f"Saved notification: {message}", flush=True)


def process_message(channel, method, properties, body):
    try:
        event = json.loads(body)

        if event.get("event_type") != "LOW_STOCK":
            print("Unsupported event type. Discarding message.")
            channel.basic_ack(delivery_tag=method.delivery_tag)
            return

        save_notification(event)

        channel.basic_ack(delivery_tag=method.delivery_tag)

    except (ValueError, KeyError, TypeError) as error:
        print(f"Invalid message: {error}")
        channel.basic_reject(
            delivery_tag=method.delivery_tag,
            requeue=False
        )

    except Exception as error:
        print(f"Processing failed: {error}")
        channel.basic_nack(
            delivery_tag=method.delivery_tag,
            requeue=True
        )
        raise


def start_consumer():
    credentials = pika.PlainCredentials(
        RABBITMQ_USER,
        RABBITMQ_PASSWORD
    )

    parameters = pika.ConnectionParameters(
        host=RABBITMQ_HOST,
        port=5672,
        credentials=credentials,
        heartbeat=60
    )

    while True:
        try:
            connection = pika.BlockingConnection(parameters)
            channel = connection.channel()

            channel.queue_declare(
                queue=QUEUE_NAME,
                durable=True
            )

            channel.basic_qos(prefetch_count=1)

            channel.basic_consume(
                queue=QUEUE_NAME,
                on_message_callback=process_message,
                auto_ack=False
            )

            print("Notification Service is waiting for messages...")
            channel.start_consuming()

        except KeyboardInterrupt:
            print("Notification consumer stopped.")
            break

        except Exception as error:
            print(f"RabbitMQ connection/consumer error: {error}")
            print("Retrying in 5 seconds...")
            time.sleep(5)

        finally:
            if "connection" in locals() and connection.is_open:
                connection.close()


if __name__ == "__main__":
    start_consumer()
