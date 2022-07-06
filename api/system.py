import logging, subprocess, json, os

from flask import Blueprint, abort, jsonify, current_app, request
from init_i.web.tools import get_address, get_gpu_info, get_v4l2, get_pure_jsonify
from init_i.web.tools.common import handle_exception

bp_system = Blueprint('system', __name__)

@bp_system.route("/v4l2/")
def web_v4l2():
    return jsonify(get_v4l2())

@bp_system.route("/device/")
def web_device_info():
    if current_app.config["PLATFORM"]=="nvidia":
        return jsonify(get_gpu_info())
    else:
        ret = {
            "CPU": {
                "id": 0,
                "name": "CPU"
            }
        }
        return jsonify(ret)

@bp_system.route("/source")
def web_source():
    # return jsonify( get_pure_jsonify(current_app.config["SRC"]) )
    temp_src_config = dict()
    for dev, cnt in current_app.config['SRC'].items():
        temp_src_config[dev] = dict()
        for key, val in cnt.items():
            if key=='object': 
                if val != None or "":
                    temp_src_config[dev][key] = 'source object'
                else:
                    temp_src_config[dev][key] = None
            else:
                temp_src_config[dev].update( {key:val} )
    try:
        pure_src_config = get_pure_jsonify( temp_src_config )
        return pure_src_config, 200
    except Exception as e:
        return e, 400

@bp_system.route("/log")
def get_log():
    data = []
    logging.debug("Log path: {}".format(current_app.config['LOGGER']))
    with open( current_app.config['LOGGER'], newline='') as f:
        for line in f.readlines():
            data.append( line.rstrip("\n") )
    
    if len(data) >= 1000:
        data = data[(len(data)-1000):]

    return jsonify( data ), 200

@bp_system.route("/read_file/", methods=["POST"])
def read_file():
    """
    Read Text and JSON file.
    """
    data = request.get_json()
    path = data["path"]
    try:
        ret_data = []
        name, ext = os.path.splitext(path)
        if ext == '.txt':
            with open( path, 'r') as f:
                for line in f.readlines():
                    ret_data.append(line.strip('\n'))
        if ext == '.json':
            with open( path, 'r') as f:
                ret_data = json.load(f)
        
        return jsonify( ret_data ), 200
    except Exception as e:
        handle_exception(error=e, title="Could not load application ... set app to None", exit=False)
        return "Erro in read file", 400