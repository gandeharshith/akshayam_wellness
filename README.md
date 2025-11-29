# Akshayam Wellness - Backend API

FastAPI backend for the Akshayam Wellness e-commerce platform specializing in organic products.

## Features

- **Authentication**: JWT-based admin authentication
- **Products & Categories**: Full CRUD operations
- **Orders Management**: Order creation, tracking, and status updates
- **Content Management**: Dynamic content for home and about pages
- **File Uploads**: Image uploads for products, categories, and logos
- **Analytics**: Sales reporting and order analytics
- **Password-Protected Orders**: Secure customer order tracking

## Tech Stack

- **Framework**: FastAPI
- **Database**: MongoDB with Motor (async driver)
- **Authentication**: JWT tokens with bcrypt password hashing
- **File Handling**: Multipart file uploads
- **CORS**: Enabled for frontend integration

## Quick Start

1. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

2. **Set up environment** (optional)
   Create a `.env` file with your MongoDB URI:
   ```
   MONGODB_URI=your_mongodb_connection_string
   ```
   *(If not provided, it will use default local MongoDB)*

3. **Run the server**
   ```bash
   python main.py
   ```

The server will start on `http://localhost:8000`

**That's it!** The backend is now running and ready to use.

## API Endpoints

### Authentication
- `POST /api/admin/login` - Admin login

### Categories
- `GET /api/categories` - Get all categories
- `POST /api/admin/categories` - Create category (Admin)
- `PUT /api/admin/categories/{id}` - Update category (Admin)
- `DELETE /api/admin/categories/{id}` - Delete category (Admin)

### Products
- `GET /api/products` - Get all products
- `GET /api/products/{id}` - Get product by ID
- `POST /api/admin/products` - Create product (Admin)
- `PUT /api/admin/products/{id}` - Update product (Admin)
- `DELETE /api/admin/products/{id}` - Delete product (Admin)

### Orders
- `POST /api/orders` - Create new order
- `POST /api/orders/user` - Get user orders (with email/password auth)
- `GET /api/admin/orders` - Get all orders (Admin)
- `PUT /api/admin/orders/{id}/status` - Update order status (Admin)
- `DELETE /api/admin/orders/{id}` - Delete order (Admin)
- `GET /api/admin/orders/analytics` - Get order analytics (Admin)

### Content
- `GET /api/content/{page}` - Get page content
- `PUT /api/admin/content/{page}` - Update page content (Admin)

### File Uploads
- `POST /api/admin/categories/{id}/image` - Upload category image
- `POST /api/admin/products/{id}/image` - Upload product image
- `POST /api/admin/content/{page}/logo` - Upload page logo

## Database Collections

- `admins` - Admin users
- `categories` - Product categories
- `products` - Products
- `orders` - Customer orders
- `users` - Customer accounts
- `content` - Page content (home, about)

## Security Features

- JWT token authentication for admin routes
- Password hashing with bcrypt
- CORS protection
- Environment variable configuration
- Input validation with Pydantic models

## Development

The API includes automatic documentation at:
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`
