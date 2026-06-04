import json
import os

DB_FILE = os.path.join(os.path.dirname(__file__), "users.json")

def load_users():
    if not os.path.exists(DB_FILE):
        return {}

    with open(DB_FILE, "r", encoding="utf-8") as file:
        return json.load(file)

def get_user(email):
    users = load_users()
    return users.get(email)