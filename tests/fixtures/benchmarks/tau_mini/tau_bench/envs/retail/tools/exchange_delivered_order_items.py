class ExchangeDeliveredOrderItems(Tool):
    @staticmethod
    def get_info():
        return {'type': 'function', 'function': {'name': 'exchange_delivered_order_items', 'description': 'Exchange items of a delivered order.', 'parameters': {'type': 'object', 'properties': {'order_id': {'type': 'string'}, 'item_ids': {'type': 'array', 'items': {'type': 'string'}}}, 'required': ['order_id', 'item_ids']}}}
