import logging, copy, time, os
from flask import Blueprint, jsonify, current_app
from flasgger import swag_from
from ivit_i.web.api.stream import FAIL_CODE

# From /ivit_i/web/api
from .common import get_src, stop_src

# From /ivit_i/web
from ..tools.parser import get_pure_jsonify
from ..tools.handler import get_tasks
from ..tools.parser import get_pure_jsonify
from ivit_i.utils.err_handler import handle_exception
from ..ai.get_api import get_api

YAML_PATH   = "/workspace/ivit_i/web/docs/task"
BP_NAME     = 'task'
bp_tasks    = Blueprint(BP_NAME, __name__)

# Define Key which in app.config
TASK        = "TASK"
TASK_LIST   = "TASK_LIST"
UUID        = "UUID"
TAG         = "tag"

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

PASS_CODE   = 200
FAIL_CODE   = 400

# Brand & Framework Info
NV          = "nvidia"
TRT         = "tensorrt"
INTEL       = "intel"
OV          = "openvino"
XLNX        = "xilinx"
VTS         = "vitis-ai"

# Define Status
RUN         = "run"
STOP        = "stop"
ERROR       = "error"
STATUS      = "status"

# Define AI Inference Parameters
API         = "api"
RUNTIME     = "runtime"
DRAW_TOOLS  = "draw_tools"
PALETTE     = "palette"
FRAME_IDX   = "frame_index"
STREAM      = "stream"

START_TIME  = "start_time"
FIRST_TIME  = "first_time_flag"
LIVE_TIME   = "live_time"

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

    message = ""
    status  = 200

    try:
        message = [ ]
        
        is_err_path = current_app.config[TASK][uuid][LABEL_PATH] in [ "", "None", None, False ]
        if is_err_path:
            logging.warning("Could not found label file")
    
        with open( current_app.config[TASK][uuid][LABEL_PATH], 'r') as f:
            message = [ line.rstrip("\n") for line in f.readlines() ]

    except Exception as e:
        message = handle_exception(e)
        status = 400

    return jsonify( message ), status
    

@bp_tasks.route("/task/<uuid>/<key>/")
@swag_from("{}/{}".format(YAML_PATH, "universal_cmd.yml"))
def task_status(uuid, key):
    trg_key, org_key_list = None, current_app.config[TASK][uuid].keys()
    for org_key in org_key_list:
        if org_key == key:
            trg_key=org_key
    if trg_key==None:
        return jsonify("Unexcepted key ({})".format(org_key_list)), 400
    else:
        return jsonify(current_app.config[TASK][uuid][trg_key]), 200

@bp_tasks.route("/task/<uuid>/run/", methods=["GET"])
@swag_from("{}/{}".format(YAML_PATH, "task_run.yml"))
def run_task(uuid):
    
    # check if the task is ready to inference
    if current_app.config[TASK][uuid][STATUS] == ERROR:
        msg  = 'The task is not ready... {}'.format( current_app.config[TASK][uuid][ERROR])
        return msg, FAIL_CODE

    if current_app.config[TASK][uuid][STATUS] == RUN:
        msg  = 'The task is still running ... '
        code = 200
        return msg, PASS_CODE
    
    # create a source object if it is not exist
    src = get_src(uuid)
    src_status, src_err = src.get_status()
    if not src_status:
        logging.error('get source error')
        current_app.config[TASK][uuid][ERROR] = src_err
        return src_err, PASS_CODE
    
    # avoid changing the configuration data during initailization ( init_ai_model)
    temp_config = copy.deepcopy(current_app.config[TASK][uuid][CONFIG]) 
    
    # get ai objects
    init_ai_model = get_api()
    
    # only pose estimation in openvino have to input a frame
    is_openvino = (current_app.config[TASK][uuid][FRAMEWORK]==OV)
    is_pose = (current_app.config[TASK][uuid][CONFIG][TAG]=='pose')
    input_frame = src.read()[1] if is_openvino and is_pose else None
        
    current_app.config[TASK][uuid][API] = init_ai_model(temp_config, input_frame)
    
    # send info to web and update current_app.config
    current_app.config[TASK][uuid][STATUS] = RUN
    
    # set initialize time
    current_app.config[TASK][uuid][START_TIME]  = time.time()
    current_app.config[TASK][uuid][LIVE_TIME]   = 0
    current_app.config[TASK][uuid][FIRST_TIME]  = True
    
    # set frame information
    current_app.config[TASK][uuid][FRAME_IDX]   = 0

    # update list
    current_app.config[TASK_LIST]=get_tasks()

    msg = 'Run Application ({}) !'.format(uuid)
    return jsonify(msg), PASS_CODE

@bp_tasks.route("/task/<uuid>/stop/", methods=["GET"])
@swag_from("{}/{}".format(YAML_PATH, "task_stop.yml"))
def stop_task(uuid):
    """ 
    Stop the task: release source, set relative object to None, set task status to stop, reload task list 
    """
    try:
        logging.info("Stopping task ...")
        
        # stop source and release source
        stop_src(uuid, release=True)
        
        # set relative object to None
        for key in [API, RUNTIME, DRAW_TOOLS, PALETTE, STREAM]:
            current_app.config[TASK][uuid][key] = None
            logging.debug(" - setting current_app.config[TASK][{}][{}] to None".format(
                uuid,
                key ))
        
        # set the status of task to STOP
        current_app.config[TASK][uuid][STATUS] = STOP

        # update list
        current_app.config["TASK_LIST"] = get_tasks()
        
        # msg
        msg = f"Stop the task ({uuid})"
        logging.info( msg )
        return jsonify( msg ), PASS_CODE

    except Exception as e:
        return jsonify(handle_exception(e)), FAIL_CODE