import cv2, time, logging, base64, threading, os, copy, sys
from flask import Blueprint, abort, jsonify, app, request
from werkzeug.utils import secure_filename

# Get Application Module From iVIT-I
sys.path.append("/workspace")

# Load Module from `web/api`
from .common import frame2btye, get_src, stop_src, socketio, app, stop_task_thread
from ..tools.handler import get_tasks
from ..tools.parser import get_pure_jsonify
from ..ai.get_api import get_api

from ivit_i.common.pipeline import Source, Pipeline
from ivit_i.utils import handle_exception

from ivit_i.app.handler import get_application
from flasgger import swag_from


# Define API Docs yaml
YAML_PATH   = ""
BP_NAME     = "stream"
DIV         = "-" * 20
YAML_PATH   = "/workspace/ivit_i/web/docs/stream"
bp_stream   = Blueprint(BP_NAME, __name__)

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
    ret_info, info  = dict(), None
    model_conf      = app.config[TASK][task_uuid][CONFIG]
    trg             = app.config[TASK][task_uuid][API]
    runtime         = app.config[TASK][task_uuid][RUNTIME]
    draw            = app.config[TASK][task_uuid][DRAW_TOOLS]
    palette         = app.config[TASK][task_uuid][PALETTE]
    
    # deep copy the config to avoid changing the old one when do inference
    temp_model_conf = copy.deepcopy(model_conf)
    # Get application executable function if has application
    application = get_application(temp_model_conf)
    
    # Define RTSP pipeline
    src_name    = app.config[TASK][task_uuid][SOURCE]
    (src_hei, src_wid), src_fps = src.get_shape(), src.get_fps()

    gst_pipeline = 'appsrc is-live=true block=true format=GST_FORMAT_TIME ' + \
            f'caps=video/x-raw,format=BGR,width={src_wid},height={src_hei},framerate={src_fps}/1 ' + \
            ' ! videoconvert ! video/x-raw,format=I420 ' + \
            ' ! queue' + \
            ' ! x264enc bitrate=2048 speed-preset=0 key-int-max=15' + \
            f' ! rtspclientsink location=rtsp://127.0.0.1:8554/{task_uuid}'

    out = cv2.VideoWriter(  gst_pipeline, cv2.CAP_GSTREAMER, 0, 
                            src_fps, (src_wid, src_hei), True )

    if not out.isOpened():
        raise Exception("can't open video writer")

    # start looping
    try:
        
        cv_show = True
        cur_info, temp_info = None, None
        cur_fps, temp_fps = 30, 30
        temp_socket_time = 0

        while(app.config[SRC][src_name][STATUS]==RUN):
            
            t1 = time.time()

            # Get the frame from source
            success, frame = src.read()            
            # Check frame
            if not success:
                if src.get_type() == 'v4l2': break
                else:
                    application.reset()
                    src.reload()
                    continue    
                                
            # If got frame then add the frame index
            app.config[TASK][task_uuid][FRAME_IDX] += 1
            
            t2 = time.time()

            # Start to Inference and update info
            temp_info = app.config[TASK][task_uuid][API].inference( frame )

            if(temp_info):
                cur_info, cur_fps = temp_info, temp_fps

            t3 = time.time()

            # Draw something
            if(cur_info):
                frame, app_info = application(frame, cur_info)
            
            # Combine the return information
            ret_info            = copy.deepcopy(RET_INFO)
            ret_info[IDX]       = app.config[TASK][task_uuid][FRAME_IDX]
            ret_info[DETS]      = info[DETS] if info is not None else None
            ret_info[INFER]     = round((t3-t2)*1000, 3)
            ret_info[FPS]       = cur_fps
            ret_info[LIVE_TIME] = int((time.time() - app.config[TASK][task_uuid][START_TIME]))
            ret_info[G_TEMP]    = ""
            ret_info[G_LOAD]    = ""

            # Send RTSP
            out.write(frame)

            # # Convert to base64 format
            # frame_base64 = base64.encodebytes(cv2.imencode(BASE64_EXT, frame)[1].tobytes()).decode(BASE64_DEC)
            # Send socketio to client
            # socketio.emit(IMG_EVENT, frame_base64, namespace=namespace)

            if(time.time() - temp_socket_time >= 1):
                socketio.emit(RES_EVENT, get_pure_jsonify(ret_info, json_format=False), namespace=namespace)
                temp_socket_time = time.time()
            socketio.sleep(0)

            # Delay to fix in 30 fps
            t_cost, t_expect = (time.time()-t1), (1/src_fps)
            if(t_cost<t_expect):
                time.sleep(t_expect-t_cost)
                # socketio.sleep(t_expect-t_cost)
            
                
            # Update Live Time and FPS
            app.config[TASK][task_uuid][LIVE_TIME] = int((time.time() - app.config[TASK][task_uuid][START_TIME]))
            
            if(temp_info):
                temp_fps = int(1/(time.time()-t1))


        logging.info('Stop streaming')

    except Exception as e:
        err = handle_exception(e, "Stream Error")
        stop_task_thread(task_uuid, err)
        raise Exception(err)

@bp_stream.route("/update_src/", methods=["POST"])
@swag_from("{}/{}".format(YAML_PATH, "update_src.yml"))
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
        data[SOURCE]=file_path

    # src = Source(
    #     input_data = data[SOURCE], 
    #     intype=data[SOURCE_TYPE]
    # )
    src = Pipeline( data[SOURCE], data[SOURCE_TYPE] )
    src.start()

    ret = frame2btye(src.get_first_frame())

    return jsonify( ret )

@bp_stream.route("/task/<uuid>/get_frame")
@swag_from("{}/{}".format(YAML_PATH, "get_frame.yml"))
def get_first_frame(uuid):
    """ Get target task first frame via web api """
    src = get_src(uuid)
    ret = frame2btye(src.get_first_frame())
    # return '<img src="data:image/jpeg;base64,{}">'.format(frame_base64)
    return jsonify( ret )
    
@bp_stream.route("/task/<uuid>/stream/start/", methods=["GET"])
@swag_from("{}/{}".format(YAML_PATH, "stream_start.yml"))
def start_stream(uuid):      

    [ logging.info(cnt) for cnt in [DIV, f'Start stream ... destination of socketio event: "/task/{uuid}/stream"', DIV] ]

    # create stream object
    do_inference = get_api()[1]
    if app.config[TASK][uuid][STREAM]==None:
        logging.info('Create a new stream thread')
        app.config[TASK][uuid][STREAM] = threading.Thread(
            target=stream_task, 
            args=(uuid, get_src(uuid), f'/task/{uuid}/stream', do_inference ), 
            name=f"{uuid}",
        )
        app.config[TASK][uuid][STREAM].daemon = True
        time.sleep(1)

    # check if thread is alive
    if app.config[TASK][uuid][STREAM].is_alive():
        logging.info('Stream is running')
        return jsonify('Stream is running'), 200

    try:
        app.config[TASK][uuid][STREAM].start()
        logging.info('Stream is created')
        return jsonify('Stream is created, The results is display in /task/<uuid>/stream'), PASS_CODE

    except Exception as e:
        app.config[TASK][uuid][STREAM].join()
        if app.config[TASK][uuid]["error"] == "":
            app.config[TASK][uuid]["error"] = handle_exception(e)
            app.config[TASK][uuid]["status"] = STOP
        return jsonify(app.config[TASK][uuid]["error"]), FAIL_CODE

@bp_stream.route("/task/<uuid>/stream/stop/", methods=["GET"])
@swag_from("{}/{}".format(YAML_PATH, "stream_stop.yml"))
def stop_stream(uuid):
    
    if app.config[TASK][uuid][STATUS]!=ERROR:
        # stop_src(uuid)
        if app.config[TASK][uuid][STREAM]!=None:
            # if app.config[TASK][uuid][STREAM].is_alive():
            try:
                
                app.config[TASK][uuid][STREAM].join()
                logging.warning('Stopped stream ...')
            except Exception as e:
                logging.warning(e)

        app.config[TASK][uuid][STREAM]=None
        logging.warning('Clear Stream ...')
        return jsonify('Stop stream success ! '), 200
