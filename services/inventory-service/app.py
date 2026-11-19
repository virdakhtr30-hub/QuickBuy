
from flask import Flask, jsonify, request
import psycopg
from psycopg.rows import dict_row
import json
import pika
import os

app = Flask(__name__)



def publish_low_stock_event(product):
    event = {
        "event_type": "LOW_STOCK",
        "product_id": product["product_id"],
        "product_name": product["name"],
        "stock_quantity": product["stock_quantity"],
        "reorder_level": product["reorder_level"]
    }

    credentials = pika.PlainCredentials(
        os.environ["RABBITMQ_USER"],
        os.environ["RABBITMQ_PASSWORD"]
    )

    parameters = pika.ConnectionParameters(
        # host="localhost",
        host="rabbitmq",
        port=5672,
        credentials=credentials,
        heartbeat=60,
        blocked_connection_timeout=5
    )

    connection = pika.BlockingConnection(parameters)

    try:
        channel = connection.channel()

        channel.queue_declare(
            queue="low_stock_queue",
            durable=True
        )

        channel.confirm_delivery()

        channel.basic_publish(
            exchange="",
            routing_key="low_stock_queue",
            body=json.dumps(event),
            properties=pika.BasicProperties(
                delivery_mode=2,
                content_type="application/json"
            ),
            mandatory=True
        )

        print(
            f"Published LOW_STOCK event for {product['name']}",
            flush=True
        )

    finally:
        connection.close()



@app.route("/health", methods=["GET"])
def health_check():
    return jsonify({
        "service": "inventory-service",
        "status": "running"
    }), 200


@app.route("/products", methods=["GET"])
def get_products():
    try:
        with psycopg.connect(
            # host="localhost",
            # port=5433,
            host="postgres",
            port=5432,
            dbname="inventory_db",
            user=os.environ["POSTGRES_USER"],
            password=os.environ["POSTGRES_PASSWORD"],
            row_factory=dict_row
        ) as connection:

            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT product_id, name, price,
                           stock_quantity, reorder_level
                    FROM products
                    ORDER BY product_id;
                """)

                products = cursor.fetchall()

        return jsonify(products), 200

    except psycopg.Error:
        app.logger.exception("Failed to retrieve products")
        return jsonify({
            "error": "Unable to retrieve products"
        }), 500



@app.route("/products", methods=["POST"])
def add_product():
    data = request.get_json(silent=True)

    if not isinstance(data, dict):
        return jsonify({"error": "A JSON object is required"}), 400

    required_fields = ["name", "price", "stock_quantity", "reorder_level"]

    if any(field not in data for field in required_fields):
        return jsonify({"error": "Missing required fields"}), 400

    name = data["name"]
    price = data["price"]
    stock = data["stock_quantity"]
    reorder = data["reorder_level"]

    if not isinstance(name, str) or not name.strip():
        return jsonify({"error": "Invalid product name"}), 400

    if (
        isinstance(price, bool) or not isinstance(price, (int, float))
        or price < 0 or price > 99999999.99
        or not isinstance(stock, int) or isinstance(stock, bool) or stock < 0
        or not isinstance(reorder, int) or isinstance(reorder, bool) or reorder < 0
    ):
        return jsonify({"error": "Invalid price or stock values"}), 400

    try:
        with psycopg.connect(
            # host="localhost",
            # port=5433,
            host="postgres",
            port=5432,
            dbname="inventory_db",
            user=os.environ["POSTGRES_USER"],
            password=os.environ["POSTGRES_PASSWORD"],
            row_factory=dict_row
        ) as connection:

            with connection.cursor() as cursor:
                cursor.execute("""
                    INSERT INTO products
                        (name, price, stock_quantity, reorder_level)
                    VALUES (%s, %s, %s, %s)
                    RETURNING product_id, name, price,
                              stock_quantity, reorder_level;
                """, (name.strip(), str(price), stock, reorder))

                product = cursor.fetchone()

        return jsonify(product), 201

    except psycopg.Error:
        app.logger.exception("Failed to create product")
        return jsonify({"error": "Unable to create product"}), 500




@app.route("/products/<int:product_id>", methods=["GET"])
def get_product(product_id):
    try:
        with psycopg.connect(
            # host="localhost",
            # port=5433,
            host="postgres",
            port=5432,
            dbname="inventory_db",
            user=os.environ["POSTGRES_USER"],
            password=os.environ["POSTGRES_PASSWORD"],
            row_factory=dict_row
        ) as connection:

            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT product_id, name, price,
                           stock_quantity, reorder_level
                    FROM products
                    WHERE product_id = %s;
                """, (product_id,))

                product = cursor.fetchone()

        if product is None:
            return jsonify({
                "error": "Product not found"
            }), 404

        return jsonify(product), 200

    except psycopg.Error:
        app.logger.exception("Failed to retrieve product")
        return jsonify({
            "error": "Unable to retrieve product"
        }), 500



@app.route("/products/<int:product_id>/stock", methods=["PATCH"])
def update_stock(product_id):
    data = request.get_json(silent=True)

    if not isinstance(data, dict):
        return jsonify({"error": "A JSON object is required"}), 400

    quantity_change = data.get("quantity_change")

    if (
        not isinstance(quantity_change, int)
        or isinstance(quantity_change, bool)
        or quantity_change == 0
    ):
        return jsonify({
            "error": "quantity_change must be a non-zero integer"
        }), 400

    try:
        with psycopg.connect(
            # host="localhost",
            # port=5433,
            host="postgres",
            port=5432,
            dbname="inventory_db",
            user=os.environ["POSTGRES_USER"],
            password=os.environ["POSTGRES_PASSWORD"],
            row_factory=dict_row
        ) as connection:

            with connection.cursor() as cursor:
                cursor.execute("""
                    UPDATE products
                    SET stock_quantity = stock_quantity + %s
                    WHERE product_id = %s
                      AND stock_quantity + %s >= 0
                    RETURNING product_id, name, price,
                              stock_quantity, reorder_level;
                """, (quantity_change, product_id, quantity_change))

                product = cursor.fetchone()

                if product is None:
                    cursor.execute("""
                        SELECT 1
                        FROM products
                        WHERE product_id = %s;
                    """, (product_id,))

                    if cursor.fetchone() is None:
                        return jsonify({
                            "error": "Product not found"
                        }), 404

                    return jsonify({
                        "error": "Insufficient stock"
                    }), 409

        return jsonify(product), 200

    except psycopg.Error:
        app.logger.exception("Failed to update stock")
        return jsonify({
            "error": "Unable to update stock"
        }), 500




@app.route("/products/<int:product_id>/reserve", methods=["POST"])
def reserve_stock(product_id):
    data = request.get_json(silent=True)

    if not isinstance(data, dict):
        return jsonify({"error": "A JSON object is required"}), 400

    quantity = data.get("quantity")

    if (
        not isinstance(quantity, int)
        or isinstance(quantity, bool)
        or quantity <= 0
    ):
        return jsonify({
            "error": "Quantity must be a positive integer"
        }), 400

    try:
        with psycopg.connect(
            # host="localhost",
            # port=5433,
            host="postgres",
            port=5432,
            dbname="inventory_db",
            user=os.environ["POSTGRES_USER"],
            password=os.environ["POSTGRES_PASSWORD"],
            row_factory=dict_row
        ) as connection:

            with connection.cursor() as cursor:
                cursor.execute("""
                    UPDATE products
                    SET stock_quantity = stock_quantity - %s
                    WHERE product_id = %s
                      AND stock_quantity >= %s
                    RETURNING product_id, name, price,
                              stock_quantity, reorder_level;
                """, (quantity, product_id, quantity))

                product = cursor.fetchone()

                if product is None:
                    cursor.execute("""
                        SELECT 1
                        FROM products
                        WHERE product_id = %s;
                    """, (product_id,))

                    if cursor.fetchone() is None:
                        return jsonify({
                            "error": "Product not found"
                        }), 404

                    return jsonify({
                        "error": "Insufficient stock"
                    }), 409

        return jsonify({
            "message": "Stock reserved successfully",
            "product": product
        }), 200

    except psycopg.Error:
        app.logger.exception("Stock reservation failed")
        return jsonify({
            "error": "Unable to reserve stock"
        }), 500





@app.route("/reservations", methods=["POST"])
def reserve_multiple_products():
    data = request.get_json(silent=True)

    if not isinstance(data, dict):
        return jsonify({"error": "Invalid JSON body"}), 400

    items = data.get("items")

    if not isinstance(items, list) or not items:
        return jsonify({
            "error": "At least one item is required"
        }), 400

    seen_products = set()

    for item in items:
        if not isinstance(item, dict):
            return jsonify({
                "error": "Invalid order item"
            }), 400

        product_id = item.get("product_id")
        quantity = item.get("quantity")

        if type(product_id) is not int or product_id <= 0:
            return jsonify({
                "error": "Invalid product_id"
            }), 400

        if type(quantity) is not int or quantity <= 0:
            return jsonify({
                "error": "Quantity must be a positive integer"
            }), 400

        if product_id in seen_products:
            return jsonify({
                "error": "Duplicate product_id"
            }), 400

        seen_products.add(product_id)

    # NEW 1: Collect products that become low-stock.
    low_stock_products = []

    try:
        with psycopg.connect(
            # host="localhost",
            # port=5433,
            host="postgres",
            port=5432,
            dbname="inventory_db",
            user=os.environ["POSTGRES_USER"],
            password=os.environ["POSTGRES_PASSWORD"],
            row_factory=dict_row
        ) as conn:

            with conn.cursor() as cur:
                reserved_products = []

                # Consistent ordering reduces deadlock risk.
                sorted_items = sorted(
                    items,
                    key=lambda item: item["product_id"]
                )

                for item in sorted_items:
                    product_id = item["product_id"]
                    quantity = item["quantity"]

                    cur.execute("""
                        UPDATE products
                        SET stock_quantity = stock_quantity - %s
                        WHERE product_id = %s
                          AND stock_quantity >= %s
                        RETURNING
                            product_id,
                            name,
                            price,
                            stock_quantity,
                            reorder_level;
                    """, (quantity, product_id, quantity))

                    product = cur.fetchone()

                    if product is None:
                        cur.execute("""
                            SELECT product_id
                            FROM products
                            WHERE product_id = %s;
                        """, (product_id,))

                        exists = cur.fetchone()

                        # Undo all earlier updates in this batch.
                        conn.rollback()

                        if exists is None:
                            return jsonify({
                                "error": "Product not found",
                                "product_id": product_id
                            }), 404

                        return jsonify({
                            "error": "Insufficient stock",
                            "product_id": product_id
                        }), 409

                    reserved_products.append({
                        "product_id": product["product_id"],
                        "name": product["name"],
                        "price": str(product["price"]),
                        "quantity_reserved": quantity,
                        "remaining_stock": product["stock_quantity"]
                    })

                    # NEW 2: Check stock after deduction.
                    if (
                        product["stock_quantity"]
                        <= product["reorder_level"]
                    ):
                        low_stock_products.append(product)

            # Exiting the connection context successfully
            # commits the transaction automatically.

        # NEW 3: Publish only after the database commit.
        for product in low_stock_products:
            try:
                publish_low_stock_event(product)
            except Exception as error:
                print(
                    f"WARNING: Could not publish low-stock "
                    f"event for {product['name']}: {error}",
                    flush=True
                )

        return jsonify({
            "message": "All products reserved successfully",
            "items": reserved_products
        }), 200

    except psycopg.Error as error:
        print("Batch reservation error:", error)

        return jsonify({
            "error": "Failed to reserve products"
        }), 500





@app.route("/reservations/release", methods=["POST"])
def release_multiple_products():
    data = request.get_json(silent=True)

    if not isinstance(data, dict):
        return jsonify({"error": "Invalid JSON body"}), 400

    items = data.get("items")

    if not isinstance(items, list) or not items:
        return jsonify({"error": "Items are required"}), 400

    seen_products = set()

    for item in items:
        if not isinstance(item, dict):
            return jsonify({"error": "Invalid item"}), 400

        product_id = item.get("product_id")
        quantity = item.get("quantity")

        if type(product_id) is not int or product_id <= 0:
            return jsonify({"error": "Invalid product_id"}), 400

        if type(quantity) is not int or quantity <= 0:
            return jsonify({"error": "Invalid quantity"}), 400

        if product_id in seen_products:
            return jsonify({"error": "Duplicate product_id"}), 400

        seen_products.add(product_id)

    try:
        with psycopg.connect(
            # host="localhost",
            # port=5433,
            host="postgres",
            port=5432,
            dbname="inventory_db",
            user=os.environ["POSTGRES_USER"],
            password=os.environ["POSTGRES_PASSWORD"]
        ) as conn:

            with conn.cursor() as cur:
                for item in sorted(
                    items,
                    key=lambda item: item["product_id"]
                ):
                    cur.execute("""
                        UPDATE products
                        SET stock_quantity = stock_quantity + %s
                        WHERE product_id = %s
                        RETURNING product_id;
                    """, (
                        item["quantity"],
                        item["product_id"]
                    ))

                    if cur.fetchone() is None:
                        conn.rollback()
                        return jsonify({
                            "error": "Product not found",
                            "product_id": item["product_id"]
                        }), 404

        return jsonify({
            "message": "Stock released successfully"
        }), 200

    except psycopg.Error as error:
        print("Stock release error:", error)
        return jsonify({
            "error": "Unable to release stock"
        }), 500



if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=False)
