import logging, os, sys, time

from flask import Blueprint, jsonify, current_app
from flasgger import swag_from
from .common import get_request_data, PASS_CODE, FAIL_CODE
from ..tools.common import http_msg

YAML_PATH   = "../docs/model"
BP_NAME     = "model"
bp_model = Blueprint(BP_NAME, __name__)

MODEL_TASK_KEY = "MODEL_TASK"

@bp_model.route("/model_task", methods=["GET"])
@swag_from(f'{YAML_PATH}/{"get_model.yml"}')
def get_model():
    return http_msg( current_app.config[MODEL_TASK_KEY], PASS_CODE )
