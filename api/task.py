import logging, copy
from flask import Blueprint, abort, jsonify, current_app
from init_i.web.utils import get_address, get_gpu_info, get_v4l2, get_pure_jsonify

bp_tasks = Blueprint('task', __name__)

@bp_tasks.route("/task/")
@bp_tasks.route("/tasks/")
def entrance():
    return jsonify(current_app.config["TASK_LIST"]), 200

@bp_tasks.route("/task/<uuid>/")
def task_info(uuid):
    return jsonify(get_pure_jsonify(current_app.config['TASK'][uuid])), 200

@bp_tasks.route("/task/<uuid>/info/")
def task_simple_info(uuid):
    af = current_app.config['TASK'][uuid]["framework"]
    simple_config = {
        "framework": af, 
        "application": current_app.config['TASK'][uuid]['application'],
        "name": current_app.config['TASK'][uuid]['name'], 
        "source": current_app.config['TASK'][uuid]['source'], 
        "source_type": current_app.config['TASK'][uuid]['config']['source_type'], 
        "device": current_app.config['TASK'][uuid]['device'] ,
        "thres": current_app.config['TASK'][uuid]['config'][af]['thres'],
        "status": current_app.config['TASK'][uuid]['status'],
    }
    return jsonify(simple_config), 200

@bp_tasks.route("/task/<uuid>/<key>/")
def task_status(uuid, key):
    trg_key, org_key_list = None, current_app.config['TASK'][uuid].keys()
    for org_key in org_key_list:
        if org_key == key:
            trg_key=org_key
    if trg_key==None:
        return jsonify("Unexcepted key ({})".format(org_key_list)), 400
    else:
        return jsonify(current_app.config['TASK'][uuid][trg_key]), 200
