from flask import Flask
from app.config import SECRET_KEY, MQTT_BROKER, MQTT_CONFIG_PORT, CLASS_LABELS_FILE
from app.services.auth_service import init_login_manager
from app.services.acoustics import load_class_labels


def create_app():
    app = Flask(
        __name__,
        template_folder='templates',
        static_folder='static'
    )
    app.secret_key = SECRET_KEY

    # Flask-Login
    init_login_manager(app)

    # ConfigManager (MQTT)
    from app.services.config_manager import ConfigManager
    app.config_mgr = ConfigManager(mqtt_broker=MQTT_BROKER, mqtt_port=MQTT_CONFIG_PORT)
    app.config_mgr.start()
    print('[Flask] ConfigManager iniciado')

    # Mapeamento de labels YAMNet
    app.id_to_name = load_class_labels(CLASS_LABELS_FILE)

    # Blueprints
    from app.blueprints.auth.routes  import auth_bp
    from app.blueprints.pages.routes import pages_bp
    from app.blueprints.api.routes   import api_bp
    from app.blueprints.proxy.routes import proxy_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(pages_bp)
    app.register_blueprint(api_bp)
    app.register_blueprint(proxy_bp)

    return app
