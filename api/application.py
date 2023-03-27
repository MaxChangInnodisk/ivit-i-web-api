from flask import Blueprint, jsonify, current_app
from flasgger import swag_from
from .common import get_request_data
from ..tools.common import http_msg

YAML_PATH   = "../docs/application"
BP_NAME     = "application"
bp_application = Blueprint(BP_NAME, __name__)

TAG_APP     = "TAG_APP"
MODEL_APP   = "MODEL_APP"
APP_MODEL   = "APP_MODEL"
APP_CTRL    = "APP_CTRL"
APP_DIR     = "APP_DIR"

@bp_application.route("/tag_app", methods=["GET"] )
@swag_from("{}/{}".format(YAML_PATH, "tag_app.yml"))
def tag_app():
    return http_msg( current_app.config[TAG_APP], 200 )

@bp_application.route("/get_all_app", methods=["GET"] )
def get_all_app():
    return http_msg( list(current_app.config[APP_CTRL].get_all_apps().keys()), 200 )

@bp_application.route("/get_sort_app", methods=["GET"] )
def get_sort_app():
    return http_msg( current_app.config[APP_CTRL].get_sort_apps(), 200 )

@bp_application.route("/register_app_folder", methods=["GET"] )
def register_app():
    with current_app.app_context():
        current_app.config[APP_CTRL].register_from_folder( current_app.config[APP_DIR] )
    return http_msg( current_app.config[APP_CTRL].get_sort_apps(), 200 )
