import logging, copy
from flask import Blueprint, abort, jsonify, current_app
from flasgger import swag_from

from ..tools.parser import get_pure_jsonify

YAML_PATH = "/workspace/ivit_i/web/docs/task"

TASK        = "TASK"
TASK_LIST   = "TASK_LIST"
UUID        = "UUID"

FRAMEWORK   = "framework"
CONFIG      = "config"
LABEL_PATH  = "label_path"
APPLICATION = "application"
MODEL       = "model"
NAME        = "name"
SOURCE      = "source"
SOURCE_TYPE = "source_type"
DEVICE      = "device"
STATUS      = "status"
THRES       = "thres"

bp_tasks = Blueprint('task', __name__)


@bp_tasks.route("/task/")
@swag_from("{}/{}".format(YAML_PATH, "task.yml"))
def entrance():
    return jsonify(current_app.config[TASK_LIST]), 200

@bp_tasks.route("/uuid/")
@swag_from("{}/{}".format(YAML_PATH, "uuid.yml"))
def get_uuid():
    return jsonify( current_app.config[UUID] ), 200

@bp_tasks.route("/task/<uuid>/")
@swag_from("{}/{}".format(YAML_PATH, "task_info.yml"))
def task_info(uuid):
    return jsonify(get_pure_jsonify(current_app.config[TASK][uuid])), 200

@bp_tasks.route("/task/<uuid>/info/")
@swag_from("{}/{}".format(YAML_PATH, "task_simple_info.yml"))
def task_simple_info(uuid):
    af = current_app.config[TASK][uuid][FRAMEWORK]
    simple_config = {
        FRAMEWORK   : af, 
        APPLICATION : current_app.config[TASK][uuid][APPLICATION] if APPLICATION in current_app.config[TASK][uuid] else None,
        MODEL       : current_app.config[TASK][uuid][MODEL] if MODEL in current_app.config[TASK][uuid] else None,
        NAME        : current_app.config[TASK][uuid][NAME] if NAME in current_app.config[TASK][uuid] else None, 
        SOURCE      : current_app.config[TASK][uuid][SOURCE] if SOURCE in current_app.config[TASK][uuid] else None, 
        SOURCE_TYPE : current_app.config[TASK][uuid][CONFIG][SOURCE_TYPE] if SOURCE_TYPE in current_app.config[TASK][uuid] else None, 
        DEVICE      : current_app.config[TASK][uuid][DEVICE] if DEVICE in current_app.config[TASK][uuid] else None ,
        STATUS      : current_app.config[TASK][uuid][STATUS] if STATUS in current_app.config[TASK][uuid] else None,
        THRES       : current_app.config[TASK][uuid][CONFIG][af][THRES] if CONFIG in current_app.config[TASK][uuid] else None,
    }
    return jsonify(simple_config), 200

@bp_tasks.route("/task/<uuid>/label/")
@swag_from("{}/{}".format(YAML_PATH, "task_label.yml"))
def task_label(uuid):
    try:
        label_list = []
        with open( current_app.config[TASK][uuid][LABEL_PATH], 'r') as f:
            [ label_list.append( line.rstrip("\n") ) for line in f.readlines() ]
        return jsonify( label_list ), 200
    except Exception as e:
        return jsonify( e ), 400

@bp_tasks.route("/task/<uuid>/<key>/")
def task_status(uuid, key):
    trg_key, org_key_list = None, current_app.config[TASK][uuid].keys()
    for org_key in org_key_list:
        if org_key == key:
            trg_key=org_key
    if trg_key==None:
        return jsonify("Unexcepted key ({})".format(org_key_list)), 400
    else:
        return jsonify(current_app.config[TASK][uuid][trg_key]), 200
