let cart = [];

async function loadProducts() {
    const productsDiv = document.getElementById("products");

    try {
        // const response = await fetch("http://localhost:8080/api/products");
        const response = await fetch("/api/products", {
            cache: "no-store"
        });

        if (!response.ok) {
            throw new Error("Failed to load products");
        }

        const products = await response.json();

        productsDiv.innerHTML = "";

        products.forEach(product => {
            const item = document.createElement("div");

            item.innerHTML = `
                <h3>${product.name}</h3>
                <p>Price: Rs. ${product.price}</p>
                <p>Available Stock: ${product.stock_quantity}</p>
                <button type="button">Add to Cart</button>
                <hr>
            `;

            item.querySelector("button").addEventListener("click", () => {
                addToCart(product);
                showToast("Added to cart!");
            });

            productsDiv.appendChild(item);
        });

    } catch (error) {
        productsDiv.textContent = "Error loading products: " + error.message;
    }
}

loadProducts();

function addToCart(product) {
    const existingItem = cart.find(
        item => item.product_id === product.product_id
    );

    const currentQuantity = existingItem ? existingItem.quantity : 0;

    if (currentQuantity >= product.stock_quantity) {
        alert("Cannot add more than the available stock.");
        return;
    }

    if (existingItem) {
        existingItem.quantity += 1;
    } else {
        cart.push({
            product_id: product.product_id,
            name: product.name,
            price: Number(product.price),
            quantity: 1
        });
    }

    displayCart();
}

function displayCart() {
    const cartDiv = document.getElementById("cart");

    if (cart.length === 0) {
        cartDiv.textContent = "Your cart is empty.";
        return;
    }

    let total = 0;

    cartDiv.innerHTML = "";

    cart.forEach(item => {
        const subtotal = item.price * item.quantity;
        total += subtotal;

        const row = document.createElement("p");

        row.textContent =
            `${item.name} × ${item.quantity} = Rs. ${subtotal.toFixed(2)} `;

        const removeButton = document.createElement("button");
        removeButton.type = "button";
        removeButton.textContent = "Remove";
        removeButton.className = "remove-btn";

        removeButton.addEventListener("click", () => {
            removeFromCart(item.product_id);
        });

        row.appendChild(removeButton);
        cartDiv.appendChild(row);
    });

    const totalElement = document.createElement("strong");
    totalElement.textContent = `Total: Rs. ${total.toFixed(2)}`;
    cartDiv.appendChild(totalElement);
}


async function placeOrder() {
    const customerName = document.getElementById("customerName").value.trim();
    const messageDiv = document.getElementById("orderMessage");
    const orderButton = document.getElementById("placeOrderBtn");

    if (!customerName) {
        messageDiv.textContent = "Please enter your name.";
        return;
    }

    if (cart.length === 0) {
        messageDiv.textContent = "Your cart is empty.";
        return;
    }

    const orderData = {
        customer_name: customerName,
        items: cart.map(item => ({
            product_id: item.product_id,
            quantity: item.quantity
        }))
    };

    orderButton.disabled = true;
    messageDiv.textContent = "Placing your order...";

    try {
        // const response = await fetch("http://localhost:8080/api/orders", {
        const response = await fetch("/api/orders", {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify(orderData)
        });

        const result = await response.json();

        if (!response.ok) {
            throw new Error(result.error || result.message || "Order failed");
        }

        messageDiv.textContent =
            `Order #${result.order_id} placed successfully!`;

        cart = [];
        displayCart();
        await loadProducts();
        await loadInventory();

    } catch (error) {
        messageDiv.textContent = "Error: " + error.message;
    } finally {
        orderButton.disabled = false;
    }
}

document.getElementById("placeOrderBtn")
    .addEventListener("click", placeOrder);


async function loadInventory() {
    const inventoryDiv = document.getElementById("inventory");

    try {
        const response = await fetch("/api/products", {
            cache: "no-store"
        });

        if (!response.ok) {
            throw new Error("Failed to load inventory");
        }

        const products = await response.json();

        inventoryDiv.innerHTML = "";

        products.forEach(product => {
            const row = document.createElement("div");

            row.innerHTML = `
                <p>
                    <strong>${product.name}</strong>
                    | Stock: ${product.stock_quantity}
                    | Reorder Level: ${product.reorder_level}
                </p>
                <input type="number" placeholder="Quantity change">
                <button type="button">Update Stock</button>
                <hr>
            `;

            const input = row.querySelector("input");
            const button = row.querySelector("button");

            button.addEventListener("click", async () => {
                const quantityChange = Number(input.value);

                if (
                    input.value.trim() === "" ||
                    !Number.isInteger(quantityChange) ||
                    quantityChange === 0
                ) {
                    alert("Enter a non-zero whole number.");
                    return;
                }

                button.disabled = true;

                try {
                    const response = await fetch(
                        `/api/products/${product.product_id}/stock`,
                        {
                            method: "PATCH",
                            headers: {
                                "Content-Type": "application/json"
                            },
                            body: JSON.stringify({
                                quantity_change: quantityChange
                            })
                        }
                    );

                    const result = await response.json();

                    if (!response.ok) {
                        throw new Error(
                            result.error || result.message || "Stock update failed"
                        );
                    }

                    alert("Stock updated successfully!");

                    await loadInventory();
                    await loadProducts();

                } catch (error) {
                    alert("Error: " + error.message);
                } finally {
                    button.disabled = false;
                }
            });

            inventoryDiv.appendChild(row);
        });

    } catch (error) {
        inventoryDiv.textContent = "Error: " + error.message;
    }
}

loadInventory();



async function loadNotifications() {
    const notificationsDiv = document.getElementById("notifications");

    try {
        const response = await fetch("/api/notifications", {
            cache: "no-store"
        });

        if (!response.ok) {
            throw new Error("Failed to load notifications");
        }

        const notifications = await response.json();

        notificationsDiv.innerHTML = "";

        if (notifications.length === 0) {
            notificationsDiv.textContent = "No notifications available.";
            return;
        }

        notifications.forEach(notification => {
            const item = document.createElement("div");

            const message = document.createElement("p");
            message.textContent = notification.message;

            const status = document.createElement("small");
            status.textContent = `Status: ${notification.status}`;

            item.appendChild(message);
            item.appendChild(status);
            item.appendChild(document.createElement("hr"));

            notificationsDiv.appendChild(item);
        });

    } catch (error) {
        notificationsDiv.textContent =
            "Error loading notifications: " + error.message;
    }
}

loadNotifications();


function showPage(page) {

    // Hide all three pages
    document.getElementById("shopPage").style.display = "none";
    document.getElementById("cartPage").style.display = "none";
    document.getElementById("adminPage").style.display = "none";

    // Show the selected page
    document.getElementById(page + "Page").style.display = "block";

    // Remove active highlight from all main navigation buttons
    document.querySelectorAll(".main-nav button").forEach(button => {
        button.classList.remove("active");
    });

    // Highlight the selected button
    document.querySelector(
        `.main-nav button[onclick="showPage('${page}')"]`
    ).classList.add("active");

    // Refresh data when opening the selected page
    if (page === "admin") {
        loadInventory();
        loadNotifications();
    }

    if (page === "shop") {
        loadProducts();
    }
}

showPage("shop");

function showToast(message) {
    const toast = document.createElement("div");

    toast.textContent = message;
    toast.className = "toast";

    document.body.appendChild(toast);

    setTimeout(() => {
        toast.remove();
    }, 2000);
}


function removeFromCart(productId) {

    cart = cart.filter(item => item.product_id !== productId);

    displayCart();
}


function showAdminTab(tab) {

    // Hide both Admin sections
    document.getElementById("inventoryTab").style.display = "none";
    document.getElementById("notificationsTab").style.display = "none";

    // Show the selected section
    document.getElementById(tab + "Tab").style.display = "block";

    // Remove active highlight from Admin buttons
    document.querySelectorAll(".admin-nav button").forEach(button => {
        button.classList.remove("active");
    });

    // Highlight the selected button
    document.querySelector(
        `.admin-nav button[onclick="showAdminTab('${tab}')"]`
    ).classList.add("active");

    if (tab === "notifications") {
        loadNotifications();
    }
}

showAdminTab("inventory");