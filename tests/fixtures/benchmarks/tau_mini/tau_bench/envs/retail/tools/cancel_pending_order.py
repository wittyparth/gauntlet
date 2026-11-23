class CancelPendingOrder(Tool):
    @staticmethod
    def get_info():
        return {'type': 'function', 'function': {'name': 'cancel_pending_order', 'description': 'Cancel a pending order. Reason is no longer needed or ordered by mistake.', 'parameters': {'type': 'object', 'properties': {'order_id': {'type': 'string'}, 'reason': {'type': 'string'}}, 'required': ['order_id', 'reason']}}}
