class ReturnDeliveredOrderItems(Tool):
    @staticmethod
    def get_info():
        return {'type': 'function', 'function': {'name': 'return_delivered_order_items', 'description': 'Return some items of a delivered order.', 'parameters': {'type': 'object', 'properties': {'order_id': {'type': 'string'}, 'item_ids': {'type': 'array', 'items': {'type': 'string'}}, 'payment_method_id': {'type': 'string'}}, 'required': ['order_id', 'item_ids', 'payment_method_id']}}}
