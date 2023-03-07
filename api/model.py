import logging, os, sys, time

from flask import Blueprint, jsonify, current_app
from flasgger import swag_from
from .common import get_request_data, PASS_CODE, FAIL_CODE
from ..tools.common import http_msg

YAML_PATH   = "../docs/model"
BP_NAME     = "model"
bp_model = Blueprint(BP_NAME, __name__)

@bp_model.route("/model", methods=["GET"])
@swag_from(f'{YAML_PATH}/{"get_model.yml"}')
def get_model():
    return http_msg( current_app.config["MODEL"], PASS_CODE )

# @bp_model.route("/model", methods=["DEL"])
# def del_model():
#     """
#     Delete Model
#     * args
#         - model: model name
#     * workflow
#         - clear model information in app.config
#         - clear model file in app.config[MODEL_DIR]
#     """
#     data = get_request_data()
#     trg_model = data["model"]
    
#     if not current_app.config["MODEL"].__contains__(trg_model):
#         return http_msg("Unexpected Model Name: {}, expected {}".format(
#             trg_model, ', '.join(current_app.config["MODEL"].keys())
#         ))

#     return http_msg( current_app.config["MODEL"], PASS_CODE )
