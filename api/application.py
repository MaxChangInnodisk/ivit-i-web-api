from flask import Blueprint, abort, jsonify, current_app

bp_application = Blueprint('application', __name__)

@bp_application.route("/tag_app/")
def tag_app():
    return jsonify( current_app.config["TAG_APP"] )

@bp_application.route("/model_app/")
def model_app():
    return jsonify( current_app.config["MODEL_APP"] )

@bp_application.route("/app_model/")
def app_model():
    return jsonify( current_app.config["APP_MODEL"] )