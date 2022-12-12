import cv2, time, logging, base64, threading, os, copy, sys, json
from flask import Blueprint, abort, jsonify, app, request
from werkzeug.utils import secure_filename
from flasgger import swag_from

# Load Module from `web/api`
from .common import frame2btye, get_src, stop_src, stop_task_thread
from .common import sock, app
from ..tools.handler import get_tasks
from ..tools.parser import get_pure_jsonify
from ..ai.get_api import get_api

# Get Application Module From iVIT-I
sys.path.append(os.getcwd())
from ivit_i.common.pipeline import Source, Pipeline
from ivit_i.utils.err_handler import handle_exception
from ivit_i.app.handler import get_application

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
AF = FRAMEWORK   = "framework"
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
SOCK        = "SOCK"
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
PLATFORM    = "PLATFORM"
NV          = "nvidia"
TRT         = "tensorrt"
INTEL       = "intel"
OV          = "openvino"
XLNX        = "xilinx"
VTS         = "vitis-ai"

# def send_socketio(frame, socketio, namespace):
#     # Convert to base64 format
#     frame_base64 = base64.encodebytes(cv2.imencode(BASE64_EXT, frame)[1].tobytes()).decode(BASE64_DEC)
#     # Send socketio to client
#     socketio.emit(IMG_EVENT, frame_base64, namespace=namespace)

def define_gst_pipeline(src_wid, src_hei, src_fps, rtsp_url, platform='intel'):
    base = 'appsrc is-live=true block=true format=GST_FORMAT_TIME ' + \
            f'caps=video/x-raw,format=BGR,width={src_wid},height={src_hei},framerate={src_fps}/1 ' + \
            ' ! videoconvert ! video/x-raw,format=I420 ' + \
            ' ! queue' + \
            ' ! x264enc bitrate=4096 speed-preset=0 key-int-max=20' + \
            f' ! rtspclientsink location={rtsp_url}'

    xlnx =  'videomixer name=mix sink_0::xpos=0 sink_0::ypos=0 ! omxh264enc prefetch-buffer=true ' + \
            'control-rate=2 target-bitrate=3000 filler-data=false constrained-intra-prediction=true ' + \
            'periodicity-idr=120 gop-mode=low-delay-p aspect-ratio=3 low-bandwidth=true default-roi-quality=4 ' + \
            '! video/x-h264,alignment=au ' + \
            f'! rtspclientsink location={rtsp_url} ' + \
            'appsrc ' + \
            f'caps=video/x-raw,format=BGR,width={src_wid},height={src_hei},framerate={src_fps}/1 ' + \
            '! videoconvert ! mix.sink_0'

    maps = {
        'intel': base,
        'nvidia': base,
        'jetson': base,
        'xilinx': xlnx
    }
    logging.info(f'Parse {platform} Gstreamer Pipeline ')
    return maps.get(platform)

def stream_task(task_uuid, src, namespace):
    '''
    Stream event: sending 'image' and 'result' to '/app/<uuid>/stream' via socketio
    
    - Arguments
        - task_uuid
        - src
        - namespace
    '''
    
    # get all the ai inference objects
    ret_info, info  = dict(), None
    model_conf      = app.config[TASK][task_uuid][CONFIG]
    trg             = app.config[TASK][task_uuid][API]
    runtime         = app.config[TASK][task_uuid][RUNTIME]
    draw            = app.config[TASK][task_uuid][DRAW_TOOLS]
    platform        = app.config[PLATFORM]

    # deep copy the config to avoid changing the old one when do inference
    temp_model_conf = copy.deepcopy(model_conf)

    # Get application executable function if has application
    application = get_application(temp_model_conf)
    
    # Define RTSP pipeline
    src_name    = app.config[TASK][task_uuid][SOURCE]
    (src_hei, src_wid), src_fps = src.get_shape(), src.get_fps()

    rtsp_url = f"rtsp://localhost:8554/{task_uuid}"

    gst_pipeline = define_gst_pipeline(
        src_wid, src_hei, src_fps, rtsp_url, platform
    )

    out = cv2.VideoWriter(  gst_pipeline, cv2.CAP_GSTREAMER, 0, 
                            src_fps, (src_wid, src_hei), True )

    logging.info('Gstreamer Pipeline: {}\n\n{}'.format(gst_pipeline, rtsp_url))

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

            # Copy frame for drawing
            draw = frame.copy()

            # Start to Inference and update info
            temp_info = trg.inference( frame )

            if(temp_info):
                cur_info, cur_fps = temp_info, temp_fps

            t3 = time.time()

            # Draw something
            if(cur_info):
                draw, app_info = application(draw, cur_info)
            
            # Send RTSP
            out.write(draw)

            # Combine the return information
            ret_info = {
                IDX         : int(app.config[TASK][task_uuid][FRAME_IDX]),
                DETS        : temp_info[DETS] if temp_info is not None else None,
                INFER       : round((t3-t2)*1000, 3),
                FPS         : cur_fps,
                LIVE_TIME   : round((time.time() - app.config[TASK][task_uuid][START_TIME]), 5),
            }
            # Send Information
            if(time.time() - temp_socket_time >= 1):                
                app.config[SOCK].update({ task_uuid: json.dumps(get_pure_jsonify(ret_info)) })
                temp_socket_time = time.time()

            # Delay to fix in 30 fps
            t_cost, t_expect = (time.time()-t1), (1/src_fps)
            
            time.sleep(t_expect-t_cost if(t_cost<t_expect) else 1e-5)
            
            # Update Live Time and FPS
            app.config[TASK][task_uuid][LIVE_TIME] = int((time.time() - app.config[TASK][task_uuid][START_TIME]))
            
            if(temp_info):
                temp_fps = int(1/(time.time()-t1))

        logging.info('Stop streaming')

    except Exception as e:
        err = handle_exception(e, "Stream Error")
        stop_task_thread(task_uuid, err)
        raise Exception(err)
    
    finally:
        trg.release()
        # out.releaes()

@sock.route(f'/{RES_EVENT}')
def message(sock):
    while(True):
        ret = app.config[SOCK]
        sock.send( json.dumps(ret) )
        time.sleep(1)

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

    if data[SOURCE] in app.config[SRC]:
        src = app.config[SRC][data[SOURCE]][OBJECT]
        if src.t.is_alive():
            ret = src.get_first_frame()
        else:
            src.start()
            ret = src.get_first_frame()
            src.stop()
    else:
        src = Pipeline( data[SOURCE], data[SOURCE_TYPE] )
        src.start()
        ret = src.get_first_frame()
        src.release()

    return jsonify( frame2btye(ret) )

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

    [ logging.info(cnt) for cnt in [DIV, f'Start stream ... destination of socket event: "/task/{uuid}/stream"', DIV] ]

    # create stream object
    if app.config[TASK][uuid][STREAM]==None:
        logging.info('Create a new stream thread')
        app.config[TASK][uuid][STREAM] = threading.Thread(
            target  = stream_task, 
            args    = (uuid, get_src(uuid), f'/task/{uuid}/stream', ), 
            name    = f"{uuid}",
            daemon  = True
        )
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
    
    if app.config[TASK][uuid][STATUS]==ERROR:
        return jsonify('Stream Error ! '), 400
        
    if app.config[TASK][uuid][STREAM]!=None:
        try:        
            app.config[TASK][uuid][STREAM].join()
            logging.warning('Stopped stream !')
        except Exception as e:
            logging.warning(e)

    app.config[TASK][uuid][STREAM]=None
    logging.warning('Clear Stream ...')
    return jsonify('Stop stream success ! '), 200
