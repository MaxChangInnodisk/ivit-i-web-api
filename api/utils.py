import json
import logging, subprocess
from flask import Blueprint, abort, jsonify, current_app
from init_i.web.utils import get_address, get_gpu_info, get_v4l2, get_pure_jsonify

bp_utils = Blueprint('utils', __name__)

@bp_utils.route("/v4l2/")
def web_v4l2():
    return jsonify(get_pure_jsonify(get_v4l2()))

@bp_utils.route("/device/")
def web_device_info():
    if current_app.config["PLATFORM"]=="nvidia":
        return jsonify(get_gpu_info())
    else:
        return jsonify("Intel device")

@bp_utils.route("/source")
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
