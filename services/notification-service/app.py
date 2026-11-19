
from flask import Flask, jsonify
import psycopg
from psycopg.rows import dict_row
import os

app = Flask(__name__)


@app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "service": "notification-service",
        "status": "running"
    }), 200


@app.route("/notifications", methods=["GET"])
def get_notifications():
    try:
        with psycopg.connect(
            # host="localhost",
            # port=5433,
            host="postgres",
            port=5432,
            dbname="notifications_db",
            user=os.environ["POSTGRES_USER"],
            password=os.environ["POSTGRES_PASSWORD"],
            row_factory=dict_row
        ) as conn:

            with conn.cursor() as cur:
                cur.execute("""
                    SELECT
                        notification_id,
                        product_id,
                        product_name,
                        stock_quantity,
                        reorder_level,
                        message,
                        status,
                        created_at
                    FROM notifications
                    ORDER BY notification_id DESC;
                """)

                notifications = cur.fetchall()

        return jsonify(notifications), 200

    except psycopg.Error as error:
        print("Notification retrieval error:", error)

        return jsonify({
            "error": "Failed to retrieve notifications"
        }), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5003, debug=False)
