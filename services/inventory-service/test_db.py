
import psycopg
import os

try:
    connection = psycopg.connect(
        host="localhost",
        port=5433,
        dbname="inventory_db",
        user=os.environ["POSTGRES_USER"],
        password=os.environ["POSTGRES_PASSWORD"]
    )

    print("Successfully connected to PostgreSQL!")

    cursor = connection.cursor()

    cursor.execute("SELECT * FROM products;")

    products = cursor.fetchall()

    for product in products:
        print(product)

    cursor.close()
    connection.close()

except psycopg.Error as error:
    print("Database operation failed:")
    print(error)
