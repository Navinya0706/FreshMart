# FreshMart (Python + Flask + SQLite)

## Run
    pip install -r requirements.txt
    python app.py
Open http://localhost:8080

Pages: Dashboard, New Order (billing), Bill history, Reports, Reviews.
Member customers get 5% discount; GST 5% after discount. Stock is validated and deducted per order.

## API
GET /api/products | GET /api/bills | GET /api/bills/<id> | POST /api/orders
GET /api/report | GET /api/report/full | GET/POST /api/reviews
