from flask import Blueprint, abort, jsonify, current_app
from flasgger import swag_from

bp_application = Blueprint('application', __name__)
yaml_path = "/workspace/init_i/web/docs/application"


@bp_application.route("/tag_app/")
@swag_from("{}/{}".format(yaml_path, "tag_app.yml"))
def tag_app():
    return jsonify( current_app.config["TAG_APP"] )

@bp_application.route("/model_app/")
@swag_from("{}/{}".format(yaml_path, "model_app.yml"))
def model_app():
    return jsonify( current_app.config["MODEL_APP"] )

@bp_application.route("/app_model/")
@swag_from("{}/{}".format(yaml_path, "app_model.yml"))
def app_model():
    return jsonify( current_app.config["APP_MODEL"] )