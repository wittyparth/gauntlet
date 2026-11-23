class TransferToHumanAgents(Tool):
    @staticmethod
    def get_info():
        return {'type': 'function', 'function': {'name': 'transfer_to_human_agents', 'description': 'Transfer the user to a human agent.', 'parameters': {'type': 'object', 'properties': {'summary': {'type': 'string'}}, 'required': ['summary']}}}
