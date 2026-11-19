
from flask import Flask, jsonify, request
import psycopg
from psycopg.rows import dict_row
import requests
from decimal import Decimal
import os

app = Flask(__name__)


@app.route("/health", methods=["GET"])
def health_check():
    return jsonify({
        "service": "order-service",
        "status": "running"
    }), 200



@app.route("/db-health", methods=["GET"])
def database_health_check():
    try:
        with psycopg.connect(
            # host="localhost",
            # port=5433,
            host="postgres",
            port=5432,
            dbname="orders_db",
            user=os.environ["POSTGRES_USER"],
            password=os.environ["POSTGRES_PASSWORD"]
        ) as conn:

            with conn.cursor() as cur:
                cur.execute("SELECT current_database();")
                database_name = cur.fetchone()[0]

        return jsonify({
            "service": "order-service",
            "database": database_name,
            "status": "connected"
        }), 200

    except psycopg.Error as error:
        print("Database connection error:", error)

        return jsonify({
            "service": "order-service",
            "status": "database connection failed"
        }), 500



@app.route("/orders", methods=["GET"])
def get_orders():
    try:
        with psycopg.connect(
            # host="localhost",
            # port=5433,
            host="postgres",
            port=5432,
            dbname="orders_db",
            user=os.environ["POSTGRES_USER"],
            password=os.environ["POSTGRES_PASSWORD"],
            row_factory=dict_row
        ) as conn:

            with conn.cursor() as cur:
                cur.execute("""
                    SELECT
                        order_id,
                        customer_name,
                        total_amount,
                        status,
                        created_at
                    FROM orders
                    ORDER BY order_id;
                """)

                orders = cur.fetchall()

        return jsonify(orders), 200

    except psycopg.Error as error:
        print("Error fetching orders:", error)

        return jsonify({
            "error": "Failed to fetch orders"
        }), 500



@app.route("/inventory-test/<int:product_id>", methods=["GET"])
def test_inventory_communication(product_id):
    try:
        response = requests.get(
            # f"http://127.0.0.1:5001/products/{product_id}",
            f"http://inventory-service:5001/products/{product_id}",
            timeout=5
        )

        if response.status_code == 404:
            return jsonify({
                "error": "Product not found in Inventory Service"
            }), 404

        response.raise_for_status()

        product = response.json()

        return jsonify({
            "message": "Order Service successfully contacted Inventory Service",
            "product": product
        }), 200

    except requests.exceptions.RequestException as error:
        print("Inventory communication error:", error)

        return jsonify({
            "error": "Unable to communicate with Inventory Service"
        }), 503





@app.route("/orders", methods=["POST"])
def create_order():
    data = request.get_json(silent=True)

    if not isinstance(data, dict):
        return jsonify({
            "error": "Request body must be a JSON object"
        }), 400

    customer_name = data.get("customer_name")
    items = data.get("items")

    if not isinstance(customer_name, str) or not customer_name.strip():
        return jsonify({
            "error": "Customer name is required"
        }), 400

    if not isinstance(items, list) or not items:
        return jsonify({
            "error": "Order must contain at least one item"
        }), 400

    seen_products = set()

    for item in items:
        if not isinstance(item, dict):
            return jsonify({"error": "Invalid order item"}), 400

        product_id = item.get("product_id")
        quantity = item.get("quantity")

        if type(product_id) is not int or product_id <= 0:
            return jsonify({"error": "Invalid product_id"}), 400

        if type(quantity) is not int or quantity <= 0:
            return jsonify({"error": "Invalid quantity"}), 400

        if product_id in seen_products:
            return jsonify({"error": "Duplicate product_id"}), 400

        seen_products.add(product_id)

    # Step 1: Ask Inventory to reserve all products.
    try:
        inventory_response = requests.post(
            # "http://127.0.0.1:5001/reservations",
            "http://inventory-service:5001/reservations",
            json={"items": items},
            timeout=5
        )

    except requests.exceptions.RequestException as error:
        print("Inventory connection error:", error)
        return jsonify({
            "error": "Inventory Service unavailable"
        }), 503

    if inventory_response.status_code in (404, 409):
        return jsonify(inventory_response.json()), inventory_response.status_code

    if inventory_response.status_code != 200:
        return jsonify({
            "error": "Inventory reservation failed"
        }), 503

    reserved_products = inventory_response.json()["items"]

    # Step 2: Calculate the total using Inventory prices.
    total_amount = Decimal("0.00")

    for product in reserved_products:
        total_amount += (
            Decimal(product["price"])
            * product["quantity_reserved"]
        )

    # Step 3: Save the order and its items.
    try:
        with psycopg.connect(
            # host="localhost",
            # port=5433,
            host="postgres",
            port=5432,
            dbname="orders_db",
            user=os.environ["POSTGRES_USER"],
            password=os.environ["POSTGRES_PASSWORD"]
        ) as conn:

            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO orders (
                        customer_name,
                        total_amount,
                        status
                    )
                    VALUES (%s, %s, 'CONFIRMED')
                    RETURNING order_id;
                """, (
                    customer_name.strip(),
                    total_amount
                ))

                order_id = cur.fetchone()[0]

                for product in reserved_products:
                    cur.execute("""
                        INSERT INTO order_items (
                            order_id,
                            product_id,
                            quantity,
                            unit_price
                        )
                        VALUES (%s, %s, %s, %s);
                    """, (
                        order_id,
                        product["product_id"],
                        product["quantity_reserved"],
                        Decimal(product["price"])
                    ))

        return jsonify({
            "message": "Order placed successfully",
            "order_id": order_id,
            "customer_name": customer_name.strip(),
            "status": "CONFIRMED",
            "total_amount": str(total_amount),
            "items": reserved_products
        }), 201

    except psycopg.Error as error:
        print("Order database error:", error)

        # Compensate for a failed order database transaction.
        try:
            release_response = requests.post(
                # "http://127.0.0.1:5001/reservations/release",
                "http://inventory-service:5001/reservations/release",
                json={"items": items},
                timeout=5
            )

            if release_response.status_code != 200:
                print(
                    "WARNING: Stock release failed:",
                    release_response.text
                )

        except requests.exceptions.RequestException as release_error:
            print(
                "WARNING: Could not release stock:",
                release_error
            )

        return jsonify({
            "error": "Order could not be saved",
            "message": "Stock recovery may require administrator review"
        }), 500




if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5002, debug=False)
