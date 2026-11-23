class ListAllProductTypes(Tool):
    @staticmethod
    def get_info():
        return {'type': 'function', 'function': {'name': 'list_all_product_types', 'description': 'List the name and product id of all product types.', 'parameters': {'type': 'object', 'properties': {}, 'required': []}}}
