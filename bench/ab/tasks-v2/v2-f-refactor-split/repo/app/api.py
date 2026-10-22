"""JSON facade over the order service, used by the HTTP layer."""
from app.core import (
    Customer,
    OrderService,
    ShopError,
    format_money,
    order_to_dict,
    sales_summary,
)


class ShopAPI:
    def __init__(self, inventory):
        self.service = OrderService(inventory)
        self.customers = {}

    def _customer(self, email):
        key = email.lower()
        if key not in self.customers:
            self.customers[key] = Customer(email)
        return self.customers[key]

    def create_order(self, payload):
        try:
            order = self.service.new_order(self._customer(payload["email"]),
                                           coupon=payload.get("coupon"))
            for line in payload.get("items", []):
                self.service.add_item(order.order_id, line["sku"], line.get("quantity", 1))
            breakdown = self.service.place(order.order_id)
        except ShopError as exc:
            return 400, {"error": str(exc)}
        body = order_to_dict(order)
        body["total"] = format_money(breakdown.total_cents)
        return 201, body

    def summary(self):
        return 200, sales_summary(self.service.orders.values())
