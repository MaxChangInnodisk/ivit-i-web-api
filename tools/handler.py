import sys, os, shutil, time, logging, copy, json
from typing import Tuple
from flask import current_app

from .parser import (
    modify_task_json, 
    parse_task_info, check_src_type, 
    gen_task_model_config, get_support_model_name,
    get_model_tag_from_arch
)
from .common import gen_uuid, handle_exception, simple_exception, json_exception
from ivit_i.app.handler import get_tag_app_list

DIV             = '-'*30
APP_KEY         = 'APPLICATION'
MODEL_KEY       = 'MODEL'
MODEL_TASK_KEY  = "MODEL_TASK"
MODEL_APP_KEY   = 'MODEL_APP'
APP_MODEL_KEY   = 'APP_MODEL'
MODEL_DIR       = "MODEL_DIR"
TAG_APP         = 'TAG_APP'
SRC_KEY         = "SRC"
UUID            = "UUID"
TASK            = "TASK"
APPLICATION     = "APPLICATION"
SRC             = "SRC"
SRC_PROC        = "proc"

# Platform
NV = 'nvidia'
JETSON = 'jetson'
INTEL = 'intel'
XLNX = 'xilinx'

# Define extension for ZIP file form iVIT-T
DARK_LABEL_EXT  = CLS_LABEL_EXT = ".txt"        # txt is the category list
DARK_JSON_EXT   = CLS_JSON_EXT  = ".json"       # json is for basic information like input_shape, preprocess
DARK_MODEL_EXT  = ".weights"    
DARK_CFG_EXT    = ".cfg"
CLS_MODEL_EXT   = ".onnx"
XLNX_MODEL_EXT  = ".xmodel"
IR_MODEL_EXT    = ".xml"
IR_MODEL_EXTS   = [ ".bin", ".mapping", ".xml" ]

MODEL_EXTS = [ DARK_MODEL_EXT, CLS_MODEL_EXT, IR_MODEL_EXT, XLNX_MODEL_EXT ]

# Define key for ZIP file from iVIT-T
LABEL_NAME          = "classes"
CLS                 = "cls"
OBJ                 = "obj"
DARKNET             = "darknet"
CLASSIFICATION_KEY  = "classification"
YOLO_KEY            = "yolo"

def get_task_uuid(task_name, fix_uuid=None):
    """ Return Task UUID """
    # Generate by name
    task_uuid = gen_uuid(name=task_name, len=8)

    # Return UUID generated by name
    if (task_name in current_app.config["UUID"].values()) and ( fix_uuid == None ):
        logging.debug("UUID ({}) had already exist.".format(task_uuid))
        return task_uuid

    # Update task_uuid 
    task_uuid = fix_uuid if fix_uuid else task_uuid

    logging.debug("{} UUID hash table! {}:{}".format( 
        "Fixed" if fix_uuid !=None else "Update", task_uuid, task_name ))
    
    # if not in app.config then update
    if (not task_uuid in current_app.config['UUID'].keys()):
        current_app.config["UUID"].update( { task_uuid: task_name } )

    return task_uuid 


def init_task_src(task_uuid):
    """ 
    Initialize Source
        1. Update to app.config['SRC']
        2. Append the uuid into app.config['SRC'][{source}]["proc"]         # means process
        3. Check is the source is exist ( support v4l2 and any file, but excepted rtsp ... )
    """
    # get source and source type
    [ source, source_type ] = [ current_app.config['TASK'][task_uuid][key] for key in ['source', 'source_type'] ]
    # update information
    if not (source in current_app.config[SRC_KEY].keys()):
        logging.debug("Update source information")
        current_app.config[SRC_KEY].update({ 
            f"{source}" : { 
                "status": "stop",
                "proc": [],
                "type": source_type,
                "object": None,
                "detail": "",
            }})
    # Add process into config
    if not ( task_uuid in current_app.config['SRC'][ source ]['proc'] ):
        logging.debug("Update process into source config")
        current_app.config[SRC_KEY][ source ]['proc'].append(task_uuid)
    # Clear process which unused
    for uuid in current_app.config[SRC_KEY][ source ]['proc']:
        if not (uuid in current_app.config['UUID']):
            current_app.config[SRC_KEY][ source ]['proc'].remove(uuid)


def init_tasks(name:str, fix_uuid:str=None, index=0) -> Tuple[bool, str]:
    """  Initialize each AI Task.
    * args
        - name: task name
        - fix_uuid: if not setup, it will generated automatically 
    """
    [ logging.info(cnt) for cnt in [ DIV, f"[{index:02}] Start to initialize application ({name})"] ]

    # UUID
    task_path = os.path.join( current_app.config["TASK_ROOT"], name )
    task_uuid = get_task_uuid(task_name = name, fix_uuid = fix_uuid)

    # Parse the information about this task
    error, task_config, model_config = {}, {}, {} 
    try:
        (task_config_path, model_config_path, task_config, model_config) = parse_task_info(name)
        task_status = "stop"

    except Exception as e:
        task_status = "error"
        logging.exception(e)
        error = json_exception(e)

    # -------------------------------------------------------------------------
    # Update basic information
    task_framework = task_config.get("framework", current_app.config.get("AF"))
    current_app.config["TASK"].update({ 
        task_uuid:{ 
            "name": name,
            "framework": task_framework, 
            "path": task_path,
            "status": task_status, 
            "error": error,
    }})

    if task_status == "error":
        logging.error('Initialize AI Task ({}) ... Failed'.format(name))
        return (task_status, task_uuid, current_app.config['TASK'][task_uuid])

    # -------------------------------------------------------------------------
    # Update information
    logging.debug("Update information to uuid ({})".format(task_uuid))

    # Double check application
    application_pattern = { "name": model_config["application"] } if type(model_config["application"])==str else model_config["application"]

    # NOTE: new version ( r1031 )
    model_name = get_support_model_name(
        model_config[task_framework]['model_path'].split('/')[-1] )

    current_app.config["TASK"][task_uuid].update({    
        "tag": model_config["tag"],
        "application": application_pattern,
        "model": model_name,     # path to model
        "model_path": f"{model_config[task_framework]['model_path']}",     # path to model
        "label_path": f"{model_config[task_framework]['label_path']}",     # path to label 
        "config_path": f"{model_config_path}",             # path to model config
        "device": f"{model_config[task_framework]['device']}",
        "source" : f"{task_config['source']}",
        "source_type": f"{task_config['source_type'] if 'source_type' in task_config.keys() else check_src_type(app_cfg['source'])}",
        "output": None,
        "api" : None,       # api
        "runtime" : None,   # model or trt_obj
        "config" : model_config,    # model config
        "draw_tools" : None,
        "palette" : None, 
        "status" : "stop", 
        "cur_frame" : 0,
        "fps": None,
        "stream": None 
    })

    # -------------------------------------------------------------------------
    # Create new source if source is not in global variable
    init_task_src(   task_uuid )

    logging.info('Initialize AI Task ({}:{}) ... Success'.format(name, task_uuid))
    
    return (task_status, task_uuid, current_app.config['TASK'][task_uuid])


def get_model_tag(tag:str):
    """ Get the tag of the model, the available value is [ cls, obj ]"""
    tags = {
        CLASSIFICATION_KEY  : CLS,
        YOLO_KEY            : DARKNET \
            if current_app.config['AF'] == 'tensorrt' else OBJ }
    return tags[tag]


def parse_model_folder(model_dir):
    """ Parsing ZIP folder which extracted from ZIP File """
    ret = {
        "tag": "",
        "arch": "",
        "framework": "",
        "model_dir": model_dir,
        "model_path": "",
        "label_path": "",
        "json_path": "",
        "config_path": "",
        "meta_data": [],
        "anchors": []
    }
    model_exts = [ DARK_MODEL_EXT, CLS_MODEL_EXT, IR_MODEL_EXT, XLNX_MODEL_EXT ]
    framework = [ NV, NV, INTEL, XLNX  ]
    assert len(framework)==len(model_exts), "Code Error, Make sure the length of model_exts and framework is the same "

    model_dir = os.path.realpath(model_dir)
    ret['model_dir'] = model_dir

    for fname in os.listdir(model_dir):
                    
        fpath = os.path.join(model_dir, fname)
        name, ext = os.path.splitext(fpath)
        
        if ext in model_exts:
            # print("\t- Detected {}: {}".format("Model", fpath))
            ret['model_path']= fpath
            
            ret['framework'] = framework[ model_exts.index(ext) ]

        elif ext in [ DARK_LABEL_EXT, CLS_LABEL_EXT, ".names" ]:
            # print("\t- Detected {}: {}".format("Label", fpath))
            ret['label_path']= fpath

        elif ext in [ DARK_JSON_EXT, CLS_JSON_EXT ]:
            # print("\t- Detected {}: {}".format("JSON", fpath))
            ret['json_path']= fpath
            
            # get tag
            with open(fpath, newline='') as jsonfile:
                train_config = json.load(jsonfile)
                ret['arch'] = train_config['model_config']['arch']                
                ret['tag'] = get_model_tag_from_arch( ret['arch'] )  

                if 'anchors' in train_config:
                    ret['anchors'] = [ int(val.strip()) \
                        for val in train_config['anchors'].strip().split(',')
                    ]

        elif ext in [ DARK_CFG_EXT ]:
            # print("\t- Detected {}: {}".format("Config", fpath))
            ret['config_path']= fpath

        else:
            # print("\t- Detected {}: {}".format("Meta Data", fpath))
            ret['meta_data'].append(fpath)

    return ret


def update_model_app():
    """ Reset MODEL_APP relationship in app.config """

    tag_app_list = current_app.config[TAG_APP] if ( TAG_APP in current_app.config ) else get_tag_app_list()

    for model_name, model_data in current_app.config[MODEL_KEY].items():
        
        current_app.config[MODEL_APP_KEY].update( { 
            model_name: tag_app_list[ model_data['tag'] ] })
        
    logging.info('Updated MODEL_APP list !')


def update_model_task():
    """ Reset MODEL_TASK relationship in app.config """

    # Update MODEL_TASK        
    for task_uuid, task_data in current_app.config['TASK'].items():

        model_name = get_support_model_name(task_data['model'])

        if not ( model_name in current_app.config[MODEL_TASK_KEY] ):
            current_app.config[MODEL_TASK_KEY].update({
                model_name: []
            })
        
        current_app.config[MODEL_TASK_KEY][model_name].append(task_uuid)


def update_model_relation():
    """ Update MODEL_<RELATION> Parameters
    1. MODEL_APP: The relationship between MODEL and APP
    2. MODEL_TASK: The relationship between MODEL and TASK
    """
    update_model_app()
    update_model_task()


def init_model():
    """ Initialize Model Information """
    
    # Get Model Folder and All Model
    model_root = os.path.realpath( current_app.config[MODEL_DIR] )
    model_dirs = [ os.path.join(model_root, model) for model in os.listdir( model_root ) ]

    logging.info(f'Get All Models: {", ".join(model_dirs) }')

    # Update key in app.config
    with current_app.app_context():

        # Clear and add MODEL key in config
        current_app.config.update({ MODEL_KEY: {} })        

        # Parse all file 
        for model_dir in model_dirs:

            try:
                current_app.config[MODEL_KEY].update({  
                    os.path.basename(model_dir): parse_model_folder(model_dir) })
                
            except Exception as e:
                logging.exception(e)

        update_model_relation()


def get_tasks(need_reset=False) -> list:
    """ Return Dictionary with `ready` and `failed` Task
    
    Args
        - need_reset: initialize each Task if need_reset=True 
    
    Workflow
        1. If need rest
            a. Initailize all Models
            b. Initsilzie each AI Task
        2. Update each AI task to TASK_LIST ( Simplier data )
    """

    ret = { "ready": [], "failed": [] }
    
    if need_reset:
        
        # Update Model information
        init_model()
        
        for idx, task in enumerate(os.listdir(current_app.config['TASK_ROOT'])):
            task_status, task_uuid, task_config = init_tasks(task, index=idx)

    for task_uuid in current_app.config['UUID']:

        task_config = current_app.config['TASK'][task_uuid]
        task_status = task_config['status']
        ret_status = "ready" if task_status!="error" else "failed"
        
        # parse ready and failed applications
        ret[ret_status].append({
            "tag": task_config.get('tag', ""),
            "framework": task_config['framework'], 
            "name": task_config['name'], 
            "uuid": task_uuid, 
            "status": task_status, 
            "error": task_config['error'], 
            "model": task_config.get('model'),
            "model_path": task_config.get('model_path'),
            "application": task_config.get('application')
        })

    return ret


def check_exist_task(task_name):
    """ Check the task is exist or not """

    task_path   = os.path.join( current_app.config['TASK_ROOT'] , task_name )

    if current_app.config['TASK'].__contains__(task_name):
        raise KeyError('AI Task ({}) already exist !!!'.format(task_name))
    
    if os.path.exists(task_path):
        raise FileExistsError("Can't create new AI Task ({}), path already exist !!!".format(task_path))


def edit_task(form, src_uuid):
    """ Edit AI Task: Modify configuration and initalize again.
    - args
        - form: input data from request
        - src_uuid: to fix the uuid
    
    - return
        - init_tasks(...)
    """

    logging.info("Start to edit the task ({})".format(src_uuid))
    
    modify_task_json(   src_uuid = src_uuid,
                        task_name = form['name'],
                        form = form,
                        need_copy = False   )

    # Update UUID and TASK
    return init_tasks(form['name'], src_uuid)


def add_task(form):
    """ New Add Task Event which will generate Task and Model Config
    1. Checking the task name is exists or not.
    2. Generate Task and Model Configuration.
    3. Initialize Task.
    """

    check_exist_task(task_name=form['name'])

    gen_task_model_config(form)

    return init_tasks(form['name'])


def remove_task(task_uuid):
    """ Remove AI Task with UUID """

    # Get target task's basic information
    task_path   = current_app.config[TASK][task_uuid]['path']

    # ---------------------------------------------------------------------
    # Remove Model Information
    # Get Model Path = If target task is an error task it would not have model_path
    task_model  = ""
    if current_app.config[TASK][task_uuid].__contains__("model_path"):
        task_model  = current_app.config[TASK][task_uuid]["model_path"].split('/')[-1]

    # Remove model-task relation
    if task_model in current_app.config[MODEL_TASK_KEY]:
        current_app.config[MODEL_TASK_KEY][task_model].remove(task_uuid)
        logging.warning(' - Remove {} in app.config[{}][{}]'.format(task_uuid, MODEL_TASK_KEY, task_model))

        # Check the current model is not using
        if current_app.config[MODEL_TASK_KEY][task_model] == []:
            current_app.config[MODEL_APP_KEY].pop(task_model, None)

            logging.warning(' - Remove {} from app.config[{}], please check /model_app'.format(
                task_model, MODEL_APP_KEY ))

    # ---------------------------------------------------------------------
    # Remove Application from app.config
    if current_app.config[TASK][task_uuid].__contains__(APPLICATION):
        task_app = current_app.config[TASK][task_uuid][APPLICATION]['name']
        task_app = [ task_app ] if type(task_app)==str else task_app

        # Delete UUID in each application ( Multi Application is supported )
        for app in task_app:
            current_app.config[APPLICATION][app].remove(task_uuid)
            logging.warning(' - Remove {} from app.config[{}][{}]'.format(
                task_uuid, APPLICATION, app
            ))

    # ---------------------------------------------------------------------
    # Remove UUID in app.config[source]
    if SRC in current_app.config[TASK][task_uuid]:
        task_src = current_app.config[TASK][task_uuid][SRC]
        current_app.config[SRC][ task_src ][SRC_PROC].remove(task_uuid)

        logging.warning(' - Remove {} from app.config[{}][{}][{}], check /src'.format(
            task_uuid,
            SRC,
            task_src,
            SRC_PROC
        ))

    # Remove UUID in config[UUID]
    current_app.config[UUID].pop(task_uuid, None)
    logging.warning(' - Pop out {} from app.config[{}]'.format(
        task_uuid, UUID ))
    
    # Remove task in config[TASK]
    current_app.config[TASK].pop(task_uuid, None)
    logging.warning(' - Pop out {} from app.config[{}]'.format(
        task_uuid, TASK ))
    
    # ---------------------------------------------------------------------
    # Remove Whole Task
    if os.path.exists(task_path): 
        shutil.rmtree(task_path)
        logging.warning(' - Remove Whole Task File ({})'.format(task_path))
    
    logging.info("Deleted AI Task: {}".format(task_uuid))

