class FindUserIdByEmail(Tool):
    @staticmethod
    def get_info():
        return {'type': 'function', 'function': {'name': 'find_user_id_by_email', 'description': 'Find user id by email. If the user is not found, the function will return an error message.', 'parameters': {'type': 'object', 'properties': {'email': {'type': 'string'}}, 'required': ['email']}}}
