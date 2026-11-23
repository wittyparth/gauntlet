class FindUserIdByNameZip(Tool):
    @staticmethod
    def get_info():
        return {'type': 'function', 'function': {'name': 'find_user_id_by_name_zip', 'description': 'Find user id by first name, last name, and zip code.', 'parameters': {'type': 'object', 'properties': {'first_name': {'type': 'string'}, 'last_name': {'type': 'string'}, 'zip': {'type': 'string'}}, 'required': ['first_name', 'last_name', 'zip']}}}
