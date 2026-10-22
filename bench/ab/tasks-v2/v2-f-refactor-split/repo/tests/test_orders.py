import unittest

from app.api import ShopAPI
from app.catalog import load_catalog
from app.core import Customer, OrderService, OrderStateError, OutOfStockError

CATALOG = """sku,name,price,stock,taxable
PEN-001,Pen,2.50,20,yes
BK-1001,Book,12.00,3,no
"""


class OrderFlowTest(unittest.TestCase):
    def setUp(self):
        self.inv = load_catalog(CATALOG)
        self.svc = OrderService(self.inv)
        self.events = []
        self.svc.on("placed", lambda e, o: self.events.append((e, o.order_id)))

    def test_place_reserves_and_ship_commits(self):
        order = self.svc.new_order(Customer("x@y.io"))
        self.svc.add_item(order.order_id, "BK-1001", 2)
        self.svc.place(order.order_id)
        self.assertEqual(self.inv.available("BK-1001"), 1)
        self.assertEqual(self.inv.on_hand("BK-1001"), 3)
        self.svc.ship(order.order_id)
        self.assertEqual(self.inv.on_hand("BK-1001"), 1)
        self.assertEqual(order.customer.completed_orders, 1)
        self.assertEqual(self.events, [("placed", order.order_id)])

    def test_out_of_stock_reserves_nothing(self):
        order = self.svc.new_order(Customer("x@y.io"))
        self.svc.add_item(order.order_id, "PEN-001", 5)
        self.svc.add_item(order.order_id, "BK-1001", 4)
        with self.assertRaises(OutOfStockError):
            self.svc.place(order.order_id)
        self.assertEqual(self.inv.available("PEN-001"), 20)

    def test_cancel_and_state_errors(self):
        order = self.svc.new_order(Customer("x@y.io"))
        self.svc.add_item(order.order_id, "PEN-001")
        self.svc.place(order.order_id)
        self.svc.cancel(order.order_id)
        self.assertEqual(self.inv.available("PEN-001"), 20)
        with self.assertRaises(OrderStateError):
            self.svc.ship(order.order_id)

    def test_api_create_order(self):
        api = ShopAPI(self.inv)
        status, body = api.create_order({"email": "Q@x.io",
                                         "items": [{"sku": "PEN-001", "quantity": 2}]})
        self.assertEqual(status, 201)
        self.assertEqual(body["total"], "€6.00")
        status, body = api.create_order({"email": "q@x.io", "items": [{"sku": "ZZ-999"}]})
        self.assertEqual(status, 400)
        self.assertEqual(api.summary()[1]["orders"], 1)


if __name__ == "__main__":
    unittest.main()
