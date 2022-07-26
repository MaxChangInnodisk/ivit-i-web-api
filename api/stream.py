from sre_constants import SUCCESS
import cv2, time, logging, base64, threading, os, sys, copy, json
from flask import Blueprint, abort, jsonify, app, request
from werkzeug.utils import secure_filename

from .. import socketio, app
from ..tools.handler import get_tasks
from ..tools.parser import get_pure_jsonify
from ..tools.common import handle_exception
from ..ai.pipeline import Source
from ..ai.get_api import get_api

from ivit_i.app.handler import get_application

# Define API Docs yaml
YAML_PATH   = ""
BP_NAME     = "stream"
DIV         = "-" * 20

# Define Status
RUN         = "run"
STOP        = "stop"
ERROR       = "error"
STATUS      = "status"

# Define Key which in app.config
TASK        = "TASK"
TASK_LIST   = "TASK_LIST"
UUID        = "UUID"
TAG         = "tag"

# Define Key which declared in app.config[SRC]
SRC         = "SRC"
OBJECT      = "object"
TYPE        = "type"
PROC        = "proc"

# Define Key which declared in each task
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
START_TIME  = "start_time"
DETS        = "detections"


# Define AI Inference Parameters
API         = "api"
RUNTIME     = "runtime"
DRAW_TOOLS  = "draw_tools"
PALETTE     = "palette"
FRAME_IDX   = "frame_index"
STREAM      = "stream"

# Define SocketIO Event
IMG_EVENT   = "images"
RES_EVENT   = "results"

# Define SocketIO Parameters
IDX         = "idx"
INFER       = "inference"
FPS         = "fps"
FIRST_TIME  = "first_time_flag"
LIVE_TIME   = "live_time"
G_TEMP      = "gpu_temp"
G_LOAD      = "gpu_load"

RET_INFO = {
    IDX         : None,
    DETS        : None,
    INFER       : None,
    FPS         : None,
    LIVE_TIME   : None,
    G_TEMP      : None,
    G_LOAD      : None,
}

# Define Stream Type
RTSP        = 'rtsp'
VIDEO       = 'video'
BASE64_EXT  = '.jpg'
BASE64_DEC  = "utf-8"
PASS_CODE   = 200
FAIL_CODE   = 400

# Brand & Framework Info
NV          = "nvidia"
TRT         = "tensorrt"
INTEL       = "intel"
OV          = "openvino"
XLNX        = "xilinx"
VTS         = "vitis-ai"

bp_stream = Blueprint(BP_NAME, __name__)

def frame2btye(frame):
    """
    Convert the image with numpy array format to btye ( base64 )

    - Arguments
        - frame
            - type: numpy.array
    - Output
        - ret
            - type: dict
            - parameters
                - image
                    - type: btye
                    - desc: the image which format is btye
                - height
                    - type: int
                    - desc: the orginal image height
                - width
                    - type: int
                    - desc: the orginal image width
                - channel
                    - type: int
                    - desc: the orginal image channel
    """
    ret, (h,w,c) = None, frame.shape
    frame_base64 = base64.encodebytes(
        cv2.imencode('.jpg', frame)[1].tobytes()
    ).decode("utf-8")

    ret = {
        "image"     : frame_base64,
        "height"    : h,
        "width"     : w,
        "channel"   : c
    }
    return ret

def get_src(task_uuid, reload_src=False):
    """ 
    Setup the source object and run 

    - Arguments
        - task_uuid
            - type: string
        - reload_src
            - type: bool
            - desc: reset the source object
    - Output
        - source_object
            - type: object
            - desc: the source object same with app.config["SRC"][{src_name}][object]
    """

    # get the target source name
    src_name = app.config[TASK][task_uuid][SOURCE]
    
    # if source is None or reload_src==True then create a new source
    if ( app.config[SRC][src_name][OBJECT] == None ) or reload_src:
        logging.info('Initialize a new source.')
        app.config[SRC][src_name][OBJECT] = Source(src_name, app.config[SRC][src_name][TYPE])
    
    # setup status and error message in source config
    status, err = app.config[SRC][src_name][OBJECT].get_status()
    app.config[SRC][src_name][STATUS], app.config[SRC][src_name][ERROR] = RUN if status else ERROR, err
    
    # return object
    return app.config[SRC][src_name][OBJECT]

def stop_src(task_uuid, release=False):
    """ 
    Stop the source and release it if needed, but if the source still be accesed by process, then it won't be stopped. 
    
    - Argument
        - task_uuid
            - type: string
        - release
            - type: bool
            - desc: release the source object
    """
    
    # initialize
    src_name, stop_flag, access_proc = app.config[TASK][task_uuid][SOURCE], True, []
    
    # checking all process
    for _uuid in app.config[SRC][src_name][PROC]:
        
        if _uuid in app.config[TASK].keys():
            
            # if any task with same source is still running, then set stop_flag to False
            if ( task_uuid!=_uuid) and (app.config[TASK][_uuid][STATUS]==RUN): 
                access_proc.append(_uuid)
                stop_flag = False           
        else:
            # clean unused uuid
            app.config[SRC][src_name][PROC].remove(_uuid)
    
    # clear source object
    if stop_flag:
        logging.info('Stopping source object ...')
        app.config[SRC][src_name][STATUS] = STOP

        if app.config[SRC][src_name][OBJECT] != None: 
            # need release source
            if release:
                logging.warning('Release source ...')
                app.config[SRC][src_name][OBJECT].release() 
                app.config[SRC][src_name][OBJECT] = None 
            else:
                app.config[SRC][src_name][OBJECT].stop()
        logging.info('Stop the source.')
    else:
        logging.warning("Stop failed, source ({}) accessed by {} ".format(src_name, access_proc))

def stream_task(task_uuid, src, namespace, infer_function):
    '''
    Stream event: sending 'image' and 'result' to '/app/<uuid>/stream' via socketio
    
    - Arguments
        - task_uuid
        - src
        - namespace
        - infer_function
    '''
    
    # get all the ai inference objects
    ret_info, info = dict(), None
    do_inference = infer_function
    model_conf = app.config[TASK][task_uuid][CONFIG]
    trg = app.config[TASK][task_uuid][API]
    runtime = app.config[TASK][task_uuid][RUNTIME]
    draw = app.config[TASK][task_uuid][DRAW_TOOLS]
    palette = app.config[TASK][task_uuid][PALETTE]
    
    # deep copy the config to avoid changing the old one when do inference
    temp_model_conf = copy.deepcopy(model_conf)

    # Get application executable function if has application
    has_application=False
    try:
        application = get_application(temp_model_conf)
        has_application = False if application == None else True
            
    except Exception as e:
        handle_exception(e)
    
    # start looping
    try:
        SRC_NAME = app.config[TASK][task_uuid][SOURCE]
        while(app.config[SRC][SRC_NAME][STATUS]==RUN):
            
            # Get the frame from source
            ret_frame, frame = src.get_frame()
            t1 = time.time()
            
            # If no frame, wait a new frame when source type is rtsp and video
            if not ret_frame: 
                logging.debug('Reconnect source ... ')
                if src.get_type().lower() in [RTSP, VIDEO]:
                    src = get_src(task_uuid, reload_src=True) 
                    continue
                else:
                    err_msg ="Couldn't get the frame data."
                    app.config[SRC][ app.config[TASK][task_uuid][SOURCE] ][ERROR]= err_msg
                    app.config[TASK][task_uuid][ERROR]= err_msg
                    app.config[TASK][task_uuid][STATUS]= ERROR
                    break

            # If got frame then add the frame index
            app.config[TASK][task_uuid][FRAME_IDX] += 1

            # Check is all ai object is exist
            if (None in [ temp_model_conf, trg, runtime, draw, palette ]):
                logging.error('None in [ temp_model_conf, trg, runtime, draw, palette ]')
                abort(404)
            
            # Start to Inference
            t2 = time.time()
            org_frame = frame.copy()

            # Update frame_draw when finished the inference
            ret, info, frame_draw = do_inference(   
                org_frame, 
                task_uuid, 
                temp_model_conf, 
                trg, 
                runtime, 
                draw, 
                palette, 
                ret_draw=(not has_application) 
            ) 
            
            # Start to draw
            t3 = time.time()
            if ret and has_application :
                frame_draw = application(org_frame, info)

            # Convert to base64 format
            frame_base64 = base64.encodebytes(cv2.imencode(BASE64_EXT, frame_draw)[1].tobytes()).decode(BASE64_DEC)
            
            # Combine the return information
            ret_info = copy.deepcopy(RET_INFO)
            ret_info[IDX] = app.config[TASK][task_uuid][FRAME_IDX]
            ret_info[DETS] = info[DETS] if info is not None else None
            ret_info[INFER] = round((t3-t2)*1000, 3)
            ret_info[FPS] = int(1/( time.time() - t1 ))
            ret_info[LIVE_TIME] = int((time.time() - app.config[TASK][task_uuid][START_TIME]))
            ret_info[G_TEMP] = ""
            ret_info[G_LOAD] = ""

            # Send socketio to client
            socketio.emit(IMG_EVENT, frame_base64, namespace=namespace)
            socketio.emit(RES_EVENT, get_pure_jsonify(ret_info, json_format=False), namespace=namespace)
            socketio.sleep(0)

            # Update Live Time
            app.config[TASK][task_uuid][LIVE_TIME] = int((time.time() - app.config[TASK][task_uuid][START_TIME]))
        
        logging.info('Stop streaming')

    except Exception as e:
        err = handle_exception(e, "Stream Error")
        return jsonify(err), 400

@bp_stream.route("/update_src/", methods=["POST"])
def update_src():
    """ Get the first frame when upload a new file """

    # Get data: support form data and json
    data = dict(request.form) if bool(request.form) else request.get_json()

    # Source: If got new source
    if bool(request.files):
        # Saving file
        file = request.files[SOURCE]
        file_name = secure_filename(file.filename)
        file_path = os.path.join(app.config["DATA"], file_name)
        file.save( file_path )
        # Update data information
        data["source"]=file_path

    src = Source(
        input_data = data["source"], 
        intype=data["source_type"]
    )
    ret = frame2btye(src.get_first_frame())

    return jsonify( ret )

@bp_stream.route("/task/<uuid>/get_frame")
def get_first_frame(uuid):
    """ Get target task first frame via web api """
    src = get_src(uuid)
    ret = frame2btye(src.get_first_frame())
    # return '<img src="data:image/jpeg;base64,{}">'.format(frame_base64)
    return jsonify( ret )

@bp_stream.route("/task/<uuid>/run/", methods=["GET"])
def run_task(uuid):
    
    # check if the task is ready to inference
    if app.config[TASK][uuid][STATUS] == ERROR:
        msg  = 'The task is not ready... {}'.format( app.config[TASK][uuid][ERROR])
        return msg, FAIL_CODE

    if app.config[TASK][uuid][STATUS] == RUN:
        msg  = 'The task is still running ... '
        code = 200
        return msg, PASS_CODE
    
    # create a source object if it is not exist
    src = get_src(uuid)
    src_status, src_err = src.get_status()
    if not src_status:
        logging.error('get source error')
        app.config[TASK][uuid][ERROR] = src_err
        return src_err, PASS_CODE
    
    # avoid changing the configuration data during initailization ( init)
    temp_config = copy.deepcopy(app.config[TASK][uuid][CONFIG]) 
    
    # get ai objects
    init, _ = get_api()
    
    # only pose estimation in openvino have to input a frame
    is_openvino = (app.config[TASK][uuid][FRAMEWORK]==OV)
    is_pose = (app.config[TASK][uuid][CONFIG][TAG]=='pose')
    input_frame = src.get_frame()[1] if is_openvino and is_pose else None
        
    ai_objects = init(temp_config, input_frame)
    
    # if no object then return error message
    if None in ai_objects:
        msg = '{}\n( {} )'.format( ai_objects[0], "Auto restart the service" )    
        logging.critical(msg)
        return msg, FAIL_CODE
    else:
        (   app.config[TASK][uuid][API], 
            app.config[TASK][uuid][RUNTIME], 
            app.config[TASK][uuid][DRAW_TOOLS], 
            app.config[TASK][uuid][PALETTE]  ) = ai_objects
    
    # send socketio and update app.config
    app.config[TASK][uuid][STATUS] = RUN
    
    # set initialize time
    app.config[TASK][uuid][START_TIME]  = time.time()
    app.config[TASK][uuid][LIVE_TIME]   = 0
    app.config[TASK][uuid][FIRST_TIME]  = True
    
    # set frame information
    app.config[TASK][uuid][FRAME_IDX]   = 0

    # update list
    app.config[TASK_LIST]=get_tasks()

    msg = 'Run Application ({}) !'.format(uuid)
    return jsonify(msg), PASS_CODE

@bp_stream.route("/task/<uuid>/stop/", methods=["GET"])
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
            app.config[TASK][uuid][key] = None
            logging.debug(" - setting app.config[TASK][{}][{}] to None".format(
                uuid,
                key ))
        
        # set the status of task to STOP
        app.config[TASK][uuid][STATUS] = STOP

        # update list
        app.config["TASK_LIST"] = get_tasks()
        
        # msg
        msg = f"Stop the task ({uuid})"
        logging.info( msg )
        return jsonify( msg ), PASS_CODE

    except Exception as e:
        return jsonify(handle_exception(e)), FAIL_CODE
    
@bp_stream.route("/task/<uuid>/stream/start/", methods=["GET"])
def start_stream(uuid):      

    [ logging.info(cnt) for cnt in [DIV, f'Start stream ... destination of socketio event: "/task/{uuid}/stream"', DIV] ]

    # create stream object
    _, do_inference = get_api()
    if app.config[TASK][uuid][STREAM]==None:
        app.config[TASK][uuid][STREAM] = threading.Thread(
            target=stream_task, 
            args=(uuid, get_src(uuid), f'/task/{uuid}/stream', do_inference ), 
            name=f"{uuid}",
        )
        app.config[TASK][uuid][STREAM].daemon = True
    # check if thread is alive
    if app.config[TASK][uuid][STREAM].is_alive():
        logging.info('Stream is running')
        return jsonify('Stream is running'), 200
    try:
        app.config[TASK][uuid][STREAM].start()
        logging.info('Stream is created')
        return jsonify('Stream is created, The results is display in /task/<uuid>/stream'), 200
    except Exception as e:
        logging.error('Start thread error: {}'.format(e))
        return jsonify('Start thread error: {}'.format(e)), 400

@bp_stream.route("/task/<uuid>/stream/stop/", methods=["GET"])
def stop_stream(uuid):

    if app.config[TASK][uuid][STATUS]!=ERROR:
        stop_src(uuid)
        if app.config[TASK][uuid][STREAM]!=None:
            # if app.config[TASK][uuid][STREAM].is_alive():
            try:
                logging.warning('Stopping stream ...')
                app.config[TASK][uuid][STREAM].join()
            except Exception as e:
                logging.warning(e)
        app.config[TASK][uuid][STREAM]=None
        return jsonify('Stop stream success ! '), 200