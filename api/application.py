from flask import Blueprint, jsonify, current_app
from flasgger import swag_from

YAML_PATH   = "/workspace/ivit_i/web/docs/application"
BP_NAME     = "application"
bp_application = Blueprint(BP_NAME, __name__)

TAG_APP     = "TAG_APP"
MODEL_APP   = "MODEL_APP"
APP_MODEL   = "APP_MODEL"

@bp_application.route("/tag_app/")
@swag_from("{}/{}".format(YAML_PATH, "tag_app.yml"))
def tag_app():
    return jsonify( current_app.config[TAG_APP] )

@bp_application.route("/model_app/")
@swag_from("{}/{}".format(YAML_PATH, "model_app.yml"))
def model_app():
    return jsonify( current_app.config[MODEL_APP] )

@bp_application.route("/app_model/")
@swag_from("{}/{}".format(YAML_PATH, "app_model.yml"))
def app_model():
    return jsonify( current_app.config[APP_MODEL] )