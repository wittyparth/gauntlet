class GetProductDetails(Tool):
    @staticmethod
    def get_info():
        return {'type': 'function', 'function': {'name': 'get_product_details', 'description': 'Get the inventory details of a product.', 'parameters': {'type': 'object', 'properties': {'product_id': {'type': 'string'}}, 'required': ['product_id']}}}
