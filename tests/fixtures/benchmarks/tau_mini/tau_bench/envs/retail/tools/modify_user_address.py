class ModifyUserAddress(Tool):
    @staticmethod
    def get_info():
        return {'type': 'function', 'function': {'name': 'modify_user_address', 'description': 'Modify the default address of a user.', 'parameters': {'type': 'object', 'properties': {'user_id': {'type': 'string'}, 'address1': {'type': 'string'}, 'address2': {'type': 'string'}, 'city': {'type': 'string'}, 'state': {'type': 'string'}, 'country': {'type': 'string'}, 'zip': {'type': 'string'}}, 'required': ['user_id', 'address1', 'address2', 'city', 'state', 'country', 'zip']}}}
