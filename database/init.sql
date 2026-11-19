
-- =====================================================
-- QUICKBUY DATABASE INITIALIZATION
-- =====================================================

-- =====================================================
-- 1. INVENTORY DATABASE
-- =====================================================

\connect inventory_db

CREATE TABLE public.products (
    product_id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    price NUMERIC(10,2) NOT NULL,
    stock_quantity INTEGER DEFAULT 0 NOT NULL,
    reorder_level INTEGER DEFAULT 5 NOT NULL,

    CONSTRAINT products_price_check
        CHECK (price >= 0),

    CONSTRAINT products_stock_quantity_check
        CHECK (stock_quantity >= 0),

    CONSTRAINT products_reorder_level_check
        CHECK (reorder_level >= 0)
);

-- Initial product catalogue

INSERT INTO public.products
    (name, price, stock_quantity, reorder_level)
VALUES
    ('Keyboard',   2500.00, 25, 5),
    ('Mouse',      1200.00, 12, 5),
    ('Monitor',   35000.00,  4, 10),
    ('USB Cable',   500.00, 30, 10),
    ('Headphones', 4500.00, 12, 5),
    ('Webcam',     6500.00, 15, 5);


-- =====================================================
-- 2. ORDER DATABASE
-- =====================================================

CREATE DATABASE orders_db;

\connect orders_db

CREATE TABLE public.orders (
    order_id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_name VARCHAR(100) NOT NULL,
    total_amount NUMERIC(12,2) DEFAULT 0 NOT NULL,
    status VARCHAR(20) DEFAULT 'PENDING' NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE
        DEFAULT CURRENT_TIMESTAMP NOT NULL,

    CONSTRAINT orders_total_amount_check
        CHECK (total_amount >= 0),

    CONSTRAINT orders_status_check
        CHECK (status IN ('PENDING', 'CONFIRMED', 'FAILED'))
);

CREATE TABLE public.order_items (
    item_id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    order_id INTEGER NOT NULL,
    product_id INTEGER NOT NULL,
    quantity INTEGER NOT NULL,
    unit_price NUMERIC(10,2) NOT NULL,

    CONSTRAINT order_items_quantity_check
        CHECK (quantity > 0),

    CONSTRAINT order_items_unit_price_check
        CHECK (unit_price >= 0),

    CONSTRAINT fk_order
        FOREIGN KEY (order_id)
        REFERENCES public.orders(order_id)
);


-- =====================================================
-- 3. NOTIFICATION DATABASE
-- =====================================================

CREATE DATABASE notifications_db;

\connect notifications_db

CREATE TABLE public.notifications (
    notification_id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    product_id INTEGER NOT NULL,
    product_name VARCHAR(100) NOT NULL,
    stock_quantity INTEGER NOT NULL,
    reorder_level INTEGER NOT NULL,
    message TEXT NOT NULL,
    status VARCHAR(20) DEFAULT 'UNREAD' NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE
        DEFAULT CURRENT_TIMESTAMP NOT NULL,

    CONSTRAINT notifications_status_check
        CHECK (status IN ('UNREAD', 'READ'))
);
