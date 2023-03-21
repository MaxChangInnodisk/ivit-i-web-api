import logging, copy, time, os
from flask import Blueprint, jsonify, current_app
from flasgger import swag_from

# From /ivit_i/web/api
from .common import get_src, stop_src, check_uuid_in_config

# From /ivit_i/web
from ..tools.common import http_msg, simple_exception, handle_exception, json_exception
from ..tools.parser import get_pure_jsonify
from ..tools.handler import get_tasks
from ..tools.parser import get_pure_jsonify
from ..ai.get_api import get_api

YAML_PATH   = "../docs/task"
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
FAIL_CODE   = 500

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

@bp_tasks.route("/task", methods=["GET"])
@swag_from("{}/{}".format(YAML_PATH, "task.yml"))
def entrance():
    current_app.config[TASK_LIST]=get_tasks()
    return http_msg(current_app.config[TASK_LIST], PASS_CODE)

@bp_tasks.route("/uuid", methods=["GET"])
@swag_from("{}/{}".format(YAML_PATH, "uuid.yml"))
def get_uuid():
    return http_msg( current_app.config[UUID], PASS_CODE )

# @bp_tasks.route("/model", methods=["GET"])
# def get_model():
#     return http_msg( current_app.config["MODEL"], PASS_CODE )

@bp_tasks.route("/task/<uuid>", methods=["GET"])
@swag_from("{}/{}".format(YAML_PATH, "task_info.yml"))
def task_info(uuid):
    info = current_app.config[TASK].get(uuid)
    temp_info = copy.deepcopy(info)
    if info is None:
        return http_msg('Support Task UUID is ({}) , but got {}.'.format(
            ', '.join(current_app.config[UUID].keys()), uuid ), FAIL_CODE)
    
    return http_msg(get_pure_jsonify(temp_info), PASS_CODE)

MODEL_TAG = {
    "cls": "classification",
    "obj": "object detection",
    "seg": "segmentation",
    "pose": "pose estimation"
}

def get_simple_task():
    _tasks = [] 
    for stats in [ 'ready', 'failed']:
        for task in current_app.config[TASK_LIST][stats]:
            _info = {}
            for key in [ 'name', 'uuid', 'status', 'model', 'tag', 'error', 'application']:
                if key == 'tag':
                    data = MODEL_TAG.get( task.get(key) )
                
                elif key == 'application':
                    data = task[key].get('name') if task.get(key) else None
                        
                else:
                    data = task.get(key)
                
                _info.update( { key: data } )
            
            _tasks.append( _info )
    
    return _tasks

@bp_tasks.route("/task/simple", methods=["GET"])
def return_simple_task():
    try:
        return http_msg(get_simple_task(), 200)
    except Exception as e:
        return http_msg(e, 500)

@bp_tasks.route("/task/<uuid>/info", methods=["GET"])
@swag_from("{}/{}".format(YAML_PATH, "task_simple_info.yml"))
def task_simple_info(uuid):
    try:
        check_uuid_in_config(uuid)
    except Exception as e:
        return http_msg(e, FAIL_CODE)
    
    af = current_app.config[TASK][uuid].get(FRAMEWORK)
    simple_config = {
        FRAMEWORK   : af, 
        APPLICATION : current_app.config[TASK][uuid].get(APPLICATION),
        MODEL       : current_app.config[TASK][uuid].get(MODEL),
        NAME        : current_app.config[TASK][uuid].get(NAME), 
        SOURCE      : current_app.config[TASK][uuid].get(SOURCE),
        SOURCE_TYPE : current_app.config[TASK][uuid].get(SOURCE_TYPE),
        DEVICE      : current_app.config[TASK][uuid].get(DEVICE),
        STATUS      : current_app.config[TASK][uuid].get(STATUS),
        THRES       : current_app.config[TASK][uuid]["config"][af].get(THRES)
    }
    return http_msg(simple_config, PASS_CODE)
    

        
@bp_tasks.route("/task/<uuid>/label", methods=["GET"])
@swag_from("{}/{}".format(YAML_PATH, "task_label.yml"))
def task_label(uuid):
    """ Get the model label in target task """
    try:
        check_uuid_in_config(uuid)
    except Exception as e:
        return http_msg(e, FAIL_CODE)
    
    # Check if label exist
    if current_app.config[TASK][uuid].get(LABEL_PATH) in [ "", "None", None, False ]:
        return http_msg("Can't get {} in target AI task".format(LABEL_PATH), FAIL_CODE)
    
    # Label
    message = None
    with open( current_app.config[TASK][uuid][LABEL_PATH], 'r') as f:
        message = [ line.rstrip("\n") for line in f.readlines() ]

    return http_msg( message, PASS_CODE )
    
@bp_tasks.route("/task/<uuid>/<key>", methods=["GET"])
@swag_from("{}/{}".format(YAML_PATH, "universal_cmd.yml"))
def task_status(uuid, key):

    try:
        check_uuid_in_config(uuid)
    except Exception as e:
        return http_msg(e, FAIL_CODE)
    
    trg_key, org_key_list = None, current_app.config[TASK][uuid].keys()
    for org_key in org_key_list:
        if org_key == key:
            trg_key=org_key
    if trg_key==None:
        return http_msg("Unexcepted key ({})".format(org_key_list), FAIL_CODE)
    else:
        return http_msg(current_app.config[TASK][uuid][trg_key], PASS_CODE)

@bp_tasks.route("/task/<uuid>/run", methods=["GET"])
@swag_from("{}/{}".format(YAML_PATH, "task_run.yml"))
def run_task(uuid):

    # ------------------------------------
    # Checking UUID
    try:
        check_uuid_in_config(uuid)
    except Exception as e:
        return http_msg(e, FAIL_CODE)

    # ------------------------------------
    # Error Task 
    if current_app.config[TASK][uuid][STATUS] == ERROR:
        current_app.config[TASK][uuid][STATUS] = ERROR
        return http_msg('The task is not ready... {}'.format( 
            str(current_app.config[TASK][uuid][ERROR])), FAIL_CODE)

    # ------------------------------------
    # Running Task
    if current_app.config[TASK][uuid][STATUS] == RUN:
        return http_msg('The task is still running ... ', PASS_CODE)
    
    # ------------------------------------
    # Create Source Thread
    try:
        src = get_src(uuid)
        src_status, src_err = src.get_status()
        if not src_status:
            raise RuntimeError( f"Init Source Failed ( {handle_exception(e)} )" )
        
    except Exception as e:
        current_app.config[TASK][uuid][STATUS] = ERROR
        current_app.config[TASK][uuid][ERROR] = json_exception(e)
        return http_msg(e, FAIL_CODE)

    # ------------------------------------
    # Deep Copy Config to avoid modfiy ther source config
    temp_config = copy.deepcopy(current_app.config[TASK][uuid][CONFIG]) 
    
    # ------------------------------------
    # Initialize AI Model
    try:

        init_ai_model = get_api()

        # NOTE: not support at r1.1, only pose estimation in openvino have to input a frame
        # is_openvino = (current_app.config[TASK][uuid].get(FRAMEWORK)==OV)
        # is_pose = (current_app.config[TASK][uuid][CONFIG].get(TAG)=='pose')
        # input_frame = src.read()[1] if is_openvino and is_pose else None
        # current_app.config[TASK][uuid][API] = init_ai_model(temp_config, input_frame)
        current_app.config[TASK][uuid][API] = init_ai_model(temp_config)
    
    except Exception as e:
        current_app.config[TASK][uuid][STATUS] = ERROR
        current_app.config[TASK][uuid][ERROR] = json_exception(e)
        return http_msg(e, FAIL_CODE)
    
    # ------------------------------------
    # Update running status and 
    # current_app.config[TASK][uuid][STATUS] = RUN
    
    current_app.config[TASK][uuid][START_TIME]  = time.time()
    current_app.config[TASK][uuid][LIVE_TIME]   = 0
    current_app.config[TASK][uuid][FIRST_TIME]  = True
    current_app.config[TASK][uuid][FRAME_IDX]   = 0

    current_app.config[TASK_LIST]=get_tasks()
    return http_msg('Run Application ({}) !'.format(uuid), PASS_CODE)

@bp_tasks.route("/task/<uuid>/stop", methods=["GET"])
@swag_from("{}/{}".format(YAML_PATH, "task_stop.yml"))
def stop_task(uuid):
    """ Stop the task: release source, set relative object to None, set task status to stop, reload task list 
    """
    
    # ------------------------------------
    # Checking UUID
    try:
        check_uuid_in_config(uuid)
    except Exception as e:
        return http_msg(e, FAIL_CODE)
    
    # ------------------------------------
    # Stop task
    try:
        logging.info("Stopping task ...")
        stop_src(uuid, release=True)

    except Exception as e:
        current_app.config[TASK][uuid] = \
            msg = 'Stopping Task Failed ... ({})'.format(handle_exception(e))
        return http_msg(msg, FAIL_CODE)

    # ------------------------------------
    # Set relative object to None
    for key in [API, RUNTIME, DRAW_TOOLS, PALETTE, STREAM]:
        current_app.config[TASK][uuid][key] = None
        logging.debug(" - setting current_app.config[TASK][{}][{}] to None".format(
            uuid, key ))
    
    # set the status of task to STOP
    current_app.config[TASK][uuid][STATUS] = STOP

    # msg
    msg = f"Stop the task ({uuid})"
    logging.info( msg )

    # update list
    current_app.config["TASK_LIST"] = get_tasks()
    return http_msg( msg, PASS_CODE )
