import logging, os, sys, time

from flask import Blueprint, current_app
from flasgger import swag_from
from .common import PASS_CODE, FAIL_CODE
from ..tools.common import http_msg
from ..tools.handler import update_model_relation

YAML_PATH   = "../docs/model"
BP_NAME     = "model"
bp_model = Blueprint(BP_NAME, __name__)

MODEL_TASK_KEY = "MODEL_TASK"
MODEL_KEY = "MODEL"
MODEL_APP_KEY = "MODEL_APP"
TAG_APP = "TAG_APP"


def get_model_info(name):
    if not (name in current_app.config[MODEL_KEY]):
        raise KeyError(
            "Unexpected model name ( {} ), expect is [ {} ]".format(
                name, ', '.join(current_app.config[MODEL_KEY].keys()))
        )
    return current_app.config[MODEL_KEY][name]


def get_model_key(name, key):
    
    info = get_model_info(name)
    
    if not (key in info):
        raise KeyError("Unexpected key ({}), supported key is [ {} ]".format(
            key, 
            ', '.join(info.keys())))
    
    return info[key]


@bp_model.route("/model", methods=["GET"])
@swag_from(f'{YAML_PATH}/{"get_all_model.yml"}')
def get_model():
    return http_msg( current_app.config[MODEL_KEY], PASS_CODE )


@bp_model.route("/model/<name>", methods=["GET"])
@swag_from("{}/{}".format(YAML_PATH, "get_model.yml"))
def get_target_model_info(name):

    try:
        return http_msg( get_model_info(name), PASS_CODE )

    except Exception as e:
        return http_msg(e, FAIL_CODE)


@bp_model.route("/model/<name>/<key>", methods=["GET"])
@swag_from("{}/{}".format(YAML_PATH, "get_model_param.yml"))
def get_target_model_param(name, key):

    try:
        return http_msg( get_model_key(name, key), PASS_CODE )
    except Exception as e:
        return http_msg(e, FAIL_CODE)    


@bp_model.route("/model/<name>/labels", methods=["GET"])
@swag_from("{}/{}".format(YAML_PATH, "task_label.yml"))
def get_model_label(name):
    """ Get the model label in target task """
    
    try:
        label_path = get_model_key(name, "label_path")

        with open( label_path, 'r') as f:
            message = [ line.rstrip("\n") for line in f.readlines() ]

        return http_msg( message, PASS_CODE )

    except Exception as e:
        return http_msg(e, FAIL_CODE)


@bp_model.route("/model_task", methods=["GET"])
@swag_from(f'{YAML_PATH}/{"get_model_task.yml"}')
def get_model_task():
    try:
        update_model_relation()
        return http_msg( current_app.config[MODEL_TASK_KEY], PASS_CODE )
    except Exception as e:
        return http_msg(e, FAIL_CODE)

    
@bp_model.route("/model_app", methods=['GET'])
@swag_from(f'{YAML_PATH}/get_model_app.yml')
def get_model_app():

    try:
        update_model_relation()
        return http_msg( current_app.config[MODEL_APP_KEY], PASS_CODE)
    
    except Exception as e:
        return http_msg(e, FAIL_CODE)