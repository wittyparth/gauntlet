class GetOrderDetails(Tool):
    @staticmethod
    def get_info():
        return {'type': 'function', 'function': {'name': 'get_order_details', 'description': 'Get the status and details of an order.', 'parameters': {'type': 'object', 'properties': {'order_id': {'type': 'string'}}, 'required': ['order_id']}}}
