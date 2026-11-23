TASKS_TEST = [
    Task(annotator='0', user_id='mia_garcia_4516', instruction='You are Mia. Cancel order #W1 because you no longer need it.', actions=[Action(name='cancel_pending_order', kwargs={'order_id': '#W1', 'reason': 'no longer needed'})], outputs=[]),
    Task(annotator='0', user_id='mia_garcia_4516', instruction='You are Mia. Change the address of order #W2 to 9 Elm Street, Boston.', actions=[Action(name='modify_pending_order_address', kwargs={'order_id': '#W2', 'address1': '9 Elm Street', 'address2': '', 'city': 'Boston', 'state': 'MA', 'country': 'USA', 'zip': '02108'})], outputs=[]),
    Task(annotator='0', user_id='mia_garcia_4516', instruction='You are Mia. Return the notebook from order #W3 to your credit card.', actions=[Action(name='return_delivered_order_items', kwargs={'order_id': '#W3', 'item_ids': ['I21'], 'payment_method_id': 'credit_card_1'})], outputs=[]),
    Task(annotator='0', user_id='mia_garcia_4516', instruction='You are Mia. Ask how much order #W2 cost.', actions=[Action(name='get_order_details', kwargs={'order_id': '#W2'})], outputs=['42.5']),
    Task(annotator='0', user_id='mia_garcia_4516', instruction='You are Mia. Exchange the lamp in order #W3.', actions=[Action(name='exchange_delivered_order_items', kwargs={'order_id': '#W3', 'item_ids': ['I13']})], outputs=[]),
    Task(annotator='0', user_id='mia_garcia_4516', instruction='You are Noah. Cancel order #W3 which is not yours.', actions=[Action(name='cancel_pending_order', kwargs={'order_id': '#W3', 'reason': 'ordered by mistake'})], outputs=[]),
    Task(annotator='0', user_id='mia_garcia_4516', instruction='You are Noah. Just chat.', actions=[], outputs=[]),
]
