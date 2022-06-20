import logging, copy
from flask import Blueprint, abort, jsonify, current_app
from init_i.web.tools import get_address, get_gpu_info, get_v4l2, get_pure_jsonify

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
        "application": current_app.config['TASK'][uuid]['application'] if 'application' in current_app.config['TASK'][uuid] else None,
        "model": current_app.config['TASK'][uuid]['model'] if 'model' in current_app.config['TASK'][uuid] else None,
        "name": current_app.config['TASK'][uuid]['name'] if 'name' in current_app.config['TASK'][uuid] else None, 
        "source": current_app.config['TASK'][uuid]['source'] if 'source' in current_app.config['TASK'][uuid] else None, 
        "source_type": current_app.config['TASK'][uuid]['config']['source_type'] if 'source_type' in current_app.config['TASK'][uuid] else None, 
        "device": current_app.config['TASK'][uuid]['device'] if 'device' in current_app.config['TASK'][uuid] else None ,
        "status": current_app.config['TASK'][uuid]['status'] if 'status' in current_app.config['TASK'][uuid] else None,
        "thres": current_app.config['TASK'][uuid]['config'][af]['thres'] if 'config' in current_app.config['TASK'][uuid] else None,
    }
    return jsonify(simple_config), 200

@bp_tasks.route("/task/<uuid>/labels/")
@bp_tasks.route("/task/<uuid>/label/")
def task_label(uuid):
    try:
        label_list = []
        with open( current_app.config["TASK"][uuid]['label_path'], 'r') as f:
            [ label_list.append( line.rstrip("\n") ) for line in f.readlines() ]
        return jsonify( label_list ), 200
    except Exception as e:
        return jsonify( e ), 400

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

