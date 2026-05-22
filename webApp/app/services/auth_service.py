import json
from flask_login import LoginManager, UserMixin
from app.config import USERS_FILE


class User(UserMixin):
    def __init__(self, username):
        self.id = username


def load_users():
    with open(USERS_FILE) as f:
        return json.load(f)


def init_login_manager(app):
    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'

    @login_manager.user_loader
    def load_user(user_id):
        users = load_users()
        if user_id in users:
            return User(user_id)
        return None
