import cv2, time, logging, base64, threading, os, copy, sys, json
from flask import Blueprint, abort, jsonify, request, send_file
from werkzeug.utils import secure_filename
from flasgger import swag_from

# Load Module from `web/api`
from .common import frame2btye, get_src, stop_src, stop_task_thread, check_uuid_in_config
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
YAML_PATH   = "/workspace/web/docs/stream"
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
STREAM_DRAW = "draw"
STREAM_INFER = "infer"
STREAM_WS   = "ws"

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

# Define Socket Parameters
SOCK_ENDPOINT   = "ivit_i"
SOCK_POOL       = "SOCK_POOL"
SOCK_SYS        = "sys"
SOCK_RES        = "result"

# App - Basic
APP_HANDLER     = "APP_HANDLER"
APP_KEY         = "application"
APP_KEY_NAME    = "name"


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
    
    # Prepare Parameters
    ret_info, info  = dict(), None
    model_conf      = app.config[TASK][task_uuid][CONFIG]
    trg             = app.config[TASK][task_uuid][API]
    platform        = app.config[PLATFORM]

    # 
    if app.config[TASK][task_uuid].get(STREAM_DRAW) is None:
        app.config[TASK][task_uuid].update( {STREAM_DRAW: True} )
    
    if app.config[TASK][task_uuid].get(STREAM_INFER) is None:
        app.config[TASK][task_uuid].update( {STREAM_INFER: True} )
    
    # Get application executable function if has application
    temp_model_conf = copy.deepcopy(model_conf)

    # Define Application
    try:
        # Version 1.0.4
        app_name = temp_model_conf[APP_KEY][APP_KEY_NAME]
        app_module = app.config[APP_HANDLER].get_all_apps()[app_name]
        application = app_module(
            config=temp_model_conf[APP_KEY],
            label=temp_model_conf['openvino']['label_path']
        )
    except:
        # Version 1.0.3
        application = get_application(temp_model_conf)
    
    # Async Mode
    trg.set_async_mode()

    # Define RTSP pipeline
    src_name    = app.config[TASK][task_uuid][SOURCE]
    (src_hei, src_wid), src_fps = src.get_shape(), src.get_fps()

    # Define RTSP
    rtsp_url = f"rtsp://localhost:8554/{task_uuid}"
    gst_pipeline = define_gst_pipeline(
        src_wid, src_hei, src_fps, rtsp_url, platform
    )
    out = cv2.VideoWriter(  gst_pipeline, cv2.CAP_GSTREAMER, 0, 
                            src_fps, (src_wid, src_hei), True )

    logging.info('Gstreamer Pipeline: {}\n\n{}'.format(gst_pipeline, rtsp_url))

    # start looping
    try:
        
        cv_show = True
        cur_info, temp_info, app_info = None, None, None
        cur_fps, fps_pool = 30, []
        temp_socket_time = 0

        while(app.config[SRC][src_name][STATUS]==RUN):
            
            t1 = time.time()

            # Get the frame from source
            success, frame = src.read()   
             
            # Check frame
            if not success:
                if src.get_type() == 'v4l2': 
                    raise RuntimeError('USB Camera Error')
                else:
                    application.reset()
                    src.reload()
                    continue    
                                
            # If got frame then add the frame index
            app.config[TASK][task_uuid][FRAME_IDX] += 1
            
            # Copy frame for drawing
            draw = frame.copy()

            # Start to Inference and update info
            cur_info = trg.inference( frame )

            # Update temp_info
            if(cur_info is not None):
                if cur_info.get(DETS) is not None:
                    temp_info = cur_info

            t3 = time.time()

            # Draw something
            if (temp_info is not None):
                draw, app_info = application(draw, temp_info)

            # Send RTSP
            out.write(draw)

            # Select Information to send
            info = temp_info.get(DETS) if (temp_info is not None) else ''


            # Combine the return information
            ret_info = {
                IDX         : int(app.config[TASK][task_uuid][FRAME_IDX]),
                DETS        : info,
                FPS         : cur_fps,
                LIVE_TIME   : round((time.time() - app.config[TASK][task_uuid][START_TIME]), 5),
            }
            
            # Update Sending Information
            target_result = { task_uuid: json.dumps(get_pure_jsonify(ret_info)) }
            app.config[SOCK_POOL][SOCK_RES].update( target_result )

            # Delay to fix in 30 fps
            t_cost, t_expect = (time.time()-t1), (1/src_fps)
            time.sleep(t_expect-t_cost if(t_cost<t_expect) else 1e-5)
            
            # Update Live Time and FPS
            app.config[TASK][task_uuid][LIVE_TIME] = int((time.time() - app.config[TASK][task_uuid][START_TIME]))
            
            # Average FPS
            if(cur_info):
                fps_pool.append(int(1/(time.time()-t1)))
                cur_fps = sum(fps_pool)//len(fps_pool) if len(fps_pool)>10 else cur_fps
                 

        logging.info('Stop streaming')

    except Exception as e:
        app.config[TASK][task_uuid][ERROR] = \
            err = handle_exception(e, "Stream Error")
        stop_task_thread(task_uuid, err)
        raise Exception(err)
    
    finally:
        trg.release()

@bp_stream.route("/add_src/", methods=["POST"])
@swag_from("{}/{}".format(YAML_PATH, "add_src.yml"))
def add_src():
    """ Get the first frame when upload a new file """

    # Get data: support form data and json
    data = dict(request.form) if bool(request.form) else request.get_json()

    # Source: If got new file
    if bool(request.files):
        # Saving file
        file = request.files[SOURCE]
        file_name = secure_filename(file.filename)
        file_path = os.path.join(app.config["DATA"], file_name)
        file.save( file_path )
        # Update data information
        data[SOURCE]=file_path

    # Check If the source is already exist 
    if data[SOURCE] in app.config[SRC]:

        # If exist and initialize
        src = app.config[SRC][data[SOURCE]].get(OBJECT)
        if src is not None:
            ret = None

            # If Alive
            if src.t.is_alive():
                ret = src.get_first_frame()
            
            # Not Alive
            else:
                src.start()
                ret = src.get_first_frame()
                src.stop()
                src.release()

            # Return Frame
            if ret:
                return jsonify( frame2btye(ret) )

    # If not exist then create a new Source
    src = Pipeline( data[SOURCE], data[SOURCE_TYPE] )
    src.start()
    ret = src.get_first_frame()
    src.release()
    return jsonify( frame2btye(ret) )

@bp_stream.route("/add_src_test/", methods=["POST"])
def add_src_test():
    """ Get the first frame when upload a new file """

    # Get data: support form data and json
    data = dict(request.form) if bool(request.form) else request.get_json()
    
    # Source: If got new file
    if bool(request.files):
        
        # Check the file is not empty
        file = request.files[SOURCE]
        if (bool(file)):
            file_name = secure_filename(file.filename)
            file_path = os.path.join(app.config["DATA"], file_name)
            file.save( file_path )
            
            data[SOURCE]=file_path
            logging.info('Get New Source: {}'.format(data[SOURCE]))

    # Check If the source is already exist 
    if data[SOURCE] in app.config[SRC]:

        # If exist and initialize
        src = app.config[SRC][data[SOURCE]].get(OBJECT)
        if src is not None:
            
            ret = None
            
            # If Alive
            if src.t.is_alive():
                ret = src.get_first_frame()
            
            # Not Alive
            else:
                src.start()
                ret = src.get_first_frame()
                src.stop()
                src.release()

            # Return Frame
            if ret:
                return send_file(ret_path)

    # If not exist then create a new Source
    src = Pipeline( data[SOURCE], data[SOURCE_TYPE] )
    src.start()
    ret = src.get_first_frame()
    
    ret_path = '/workspace/data/test.jpg'
    cv2.imwrite(ret_path, ret)
    src.release()
    return send_file(ret_path)
    
@bp_stream.route("/task/<uuid>/get_frame")
@swag_from("{}/{}".format(YAML_PATH, "get_frame.yml"))
def get_first_frame(uuid):
    """ Get target task first frame via web api """

    if not check_uuid_in_config(uuid):
        return 'Support Task UUID is ({}) , but got {}.'.format(
            ', '.join(app.config[UUID].keys()), uuid ), FAIL_CODE
        
    src = get_src(uuid)
    ret = frame2btye(src.get_first_frame())
    # return '<img src="data:image/jpeg;base64,{}">'.format(frame_base64)
    return jsonify( ret )
    
@bp_stream.route("/task/<uuid>/stream/start/", methods=["GET"])
@swag_from("{}/{}".format(YAML_PATH, "stream_start.yml"))
def start_stream(uuid):      

    if not check_uuid_in_config(uuid):
        return 'Support Task UUID is ({}) , but got {}.'.format(
            ', '.join(app.config[UUID].keys()), uuid ), FAIL_CODE

    [ logging.info(cnt) for cnt in [DIV, f'Start stream ... destination of socket event: "/task/{uuid}/stream"', DIV] ]

    # create stream object
    if app.config[TASK][uuid][STREAM] is None:
        app.config[TASK][uuid][STREAM] = threading.Thread(
            target  = stream_task, 
            args    = (uuid, get_src(uuid), f'/task/{uuid}/stream', ), 
            name    = f"{uuid}",
            daemon  = True
        )
        logging.info('Created a new stream thread ( {} )'.format(app.config[TASK][uuid][STREAM]))
    
    # wait stream thread
    while(app.config[TASK][uuid][STREAM] == None):
        print('wait')
        time.sleep(1)

    # check if thread is alive
    if app.config[TASK][uuid][STREAM].is_alive():
        logging.info('Stream is running')
        return jsonify(f'rtsp://localhost:8554/{uuid}'), PASS_CODE

    try:
        # wait for thread
        while(app.config[TASK][uuid][STREAM] is None):
            time.sleep(1)
        
        # start the thread
        app.config[TASK][uuid][STREAM].start()
        logging.info('Stream is created')
        return jsonify(f'rtsp://localhost:8554/{uuid}'), PASS_CODE

    except Exception as e:
        
        if app.config[TASK][uuid][STREAM] is not None:  
            if app.config[TASK][uuid][STREAM].is_alive():
                os.kill(app.config[TASK][uuid][STREAM])
        
        app.config[TASK][uuid][ERROR] = msg = handle_exception(e)
        app.config[TASK][uuid]["status"] = STOP
        return jsonify(msg), FAIL_CODE

@bp_stream.route("/task/<uuid>/stream/stop/", methods=["GET"])
@swag_from("{}/{}".format(YAML_PATH, "stream_stop.yml"))
def stop_stream(uuid):

    if not check_uuid_in_config(uuid):
        return 'Support Task UUID is ({}) , but got {}.'.format(
            ', '.join(app.config[UUID].keys()), uuid ), FAIL_CODE

    print(app.config[TASK][uuid][API])

    if app.config[TASK][uuid][STATUS]==ERROR:
        return jsonify('Stream Error ! '), 400
        
    if app.config[TASK][uuid][STREAM]!=None:
        try:        
            src_name = app.config[TASK][uuid][SOURCE]
            app.config[SRC][src_name][STATUS] = STOP
            app.config[TASK][uuid][STREAM].join()
            logging.warning('Stopped stream !')
        except Exception as e:
            logging.warning(e)

    print(app.config[TASK][uuid][API])
    app.config[TASK][uuid][STREAM]=None
    logging.warning('Clear Stream ...')
    return jsonify('Stop stream success ! ( {}:{} ) '.format(uuid, app.config[TASK][uuid]['name'])), 200

@bp_stream.route("/task/<uuid>/stream/draw", methods=["PUT"])
def stream_draw(uuid):
    
    # Get Data
    data = dict(request.form) if bool(request.form) else request.get_json()

    # Double Check
    if not data['data'] in [ True, False ]:
        return jsonify( 'Excepted [ True, False ] , but got "{}"'.format(data['data']) ), 400
    
    # Update Key
    app.config[TASK][uuid].update( { STREAM_DRAW: data['data'] } )
    
    return jsonify('Updated {} to {}'.format(STREAM_DRAW, app.config[TASK][uuid][STREAM_DRAW]))

@bp_stream.route("/task/<uuid>/stream/infer", methods=["PUT"])
def stream_infer(uuid):
    
    # Get Data
    data = dict(request.form) if bool(request.form) else request.get_json()

    # Double Check
    if not data['data'] in [ True, False ]:
        return jsonify( 'Excepted [ True, False ] , but got "{}"'.format(data['data']) ), 400
    
    # Update Key
    app.config[TASK][uuid].update( { STREAM_INFER: data['data'] } )
    
    return jsonify('Updated {} to {}'.format(STREAM_INFER, app.config[TASK][uuid][STREAM_INFER]))
