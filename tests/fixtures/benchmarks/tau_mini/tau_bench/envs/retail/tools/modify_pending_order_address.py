class ModifyPendingOrderAddress(Tool):
    @staticmethod
    def get_info():
        return {'type': 'function', 'function': {'name': 'modify_pending_order_address', 'description': 'Modify the shipping address of a pending order.', 'parameters': {'type': 'object', 'properties': {'order_id': {'type': 'string'}, 'address1': {'type': 'string'}, 'address2': {'type': 'string'}, 'city': {'type': 'string'}, 'state': {'type': 'string'}, 'country': {'type': 'string'}, 'zip': {'type': 'string'}}, 'required': ['order_id', 'address1', 'address2', 'city', 'state', 'country', 'zip']}}}
