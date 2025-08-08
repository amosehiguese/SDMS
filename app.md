# SuccessDirectMarketStore App

###  Django Ecommerce AJAX Store (Temu-Style) with Blog, Paystack, Celery, Receipts**

---

Build a **complete, production-ready ecommerce application** using **Django** and the specifications below. Do **not** overengineer or use placeholders — everything should be **fully implemented**.

---

### ⚙️ **Stack & Core Technologies**

* **Django** as backend framework
* **Django-Allauth** for user authentication
* **Tailwind CSS** for styling (⚠️ no inline CSS)
* **Font Awesome** icons (❌ no emojis)
* **AJAX everywhere** (no full-page reloads)
* **Celery + Redis** for background task processing
* **Paystack** for payments (in **Naira**)

---

### 🛒 **Ecommerce Features**

#### ✅ Product Features

* Title, slug, price, description, stock, category
* Flash sale (optional sale price + end time)
* Countdown timer on flash sales
* Admin can toggle flash sale per product

#### ✅ Purchase Options (Choose at Checkout)

* Buyer must choose one before purchase:

  * **Hold as Asset** → stored digitally, not shipped
  * **Deliver to Me** → standard shipping flow
* Held assets can later be **liquidated**:

  * Buyer provides shipping address
  * Triggers normal shipping process

---

### 📦 **Order Lifecycle**

* Order statuses:
  `Pending → Paid → Shipped → Delivered`
* Buyer sees status tracker on order
* Admin controls transitions:

  * Admin marks order as **Shipped**
  * Admin marks shipped order as **Delivered**

All order operations (checkout, updates) must be done via **AJAX**.

---

### 💳 **Payments & Receipts**

* Use **Paystack** for payment integration
* On successful payment:

  * Mark order as **Paid**
  * Generate **receipt (HTML or PDF)**
  * Email receipt to buyer using **Celery**
  * Log receipt reference in order history

---

### 📨 **Email System (Async)**

All emails must be:

* Sent **asynchronously using Celery**
* Based on reusable **HTML email templates**

Emails to implement:

* Welcome email
* Order confirmation
* Receipt (with downloadable link or PDF)
* Order status updates

---

### 🔐 **Authentication**

* Use **Django-Allauth** for auth
* All login, register, logout, and reset flows must be **AJAX-based**

User dashboard should include:

* Held assets list
* Order history with tracking
* Action to **liquidate** held assets

---

### 🛠️ **Admin Features & Site Config**

* Admin-only site configuration panel:

  * Manage Paystack keys
  * Upload logo and branding
  * Toggle flash sales globally
* Admin Dashboard:

  * Sales graphs (daily, weekly, monthly)
  * Generate/export reports (CSV)
  * Track flash sale performance
  * Filter by order status, product, category, date range
  * Manually move order status from **Shipped → Delivered**

---

### ✍️ **Blog Feature**

Include a basic blog:

* Post model with title, slug, content (RichText), created\_at
* Blog homepage and post detail view
* AJAX-based comment system (only for logged-in users)
* Blog URL structure: `/blog/<slug>/`
* Admins can post from the admin dashboard

---

### 💡 **Design & UI**

* Mimic **temu.com** design simplicity and layout
* Color palette: **White**, **Black**, **Gold**

---

### 🔧 **Structure & Deliverables**

* Avoid third-party ecommerce libraries like Oscar or Saleor
* Clean Django structure:

  * Multiple apps: `products`, `orders`, `cart`, `blog`, `payments`, `core`, etc.
  * Use separate `models.py`, `views.py`, `urls.py`, `templates/`, `static/`
* Provide `README.md` with:

  * Setup instructions
  * Paystack & Celery configuration


