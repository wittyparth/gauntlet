class GetUserDetails(Tool):
    @staticmethod
    def get_info():
        return {'type': 'function', 'function': {'name': 'get_user_details', 'description': 'Get the details of a user, including their orders.', 'parameters': {'type': 'object', 'properties': {'user_id': {'type': 'string'}}, 'required': ['user_id']}}}
