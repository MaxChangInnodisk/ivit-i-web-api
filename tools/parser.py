import os, shutil, logging, copy, json
from typing import Tuple
from flask import current_app
import numpy as np
from ..ai.config import (
    cls_pattern, obj_yolo_pattern, obj_yolov4_pattern
)

def clear_config_buf(uuid):
    # Clear the UUID and TASK information
    current_app.config['UUID'].pop(uuid, None)
    current_app.config['TASK'].pop(uuid, None)

def parse_task_info(path:str, pure_content:bool=False) -> Tuple[bool, tuple, str]:
    """ Parsing the application informations and return the initialize status, error message and relative informations.
    
    - Input
        - path              : path to application folder
        - pure_content      : the task_cfg will merge to model_cfg when pure_content is False
    - Output
        - task_cfg_path      : path to application configuration
        - model_cfg_path    : path to model configuration
        - task_cfg           : the content of application configuration with json format
        - model_cfg         : the content of model configuration with json format
    """
    
    # Get the task folder and config path
    task_dir_path = os.path.join(current_app.config["TASK_ROOT"], path )
    task_cfg_path = os.path.join( task_dir_path, "task.json")

    if not os.path.exists(task_cfg_path):
        raise FileNotFoundError(f"Can't find AI Task Configuration ({task_cfg_path})")
    
    # Load AI Task Config
    task_cfg = load_json(task_cfg_path)
    framework = task_cfg["framework"] 

    # Check AI Task Config Content
    if task_cfg=="" or task_cfg is None:
        raise ValueError(f"Get empty AI Task Configuration ! ({task_cfg_path})")

    # Get the model config path
    model_cfg_path = task_cfg["prim"].get("model_json")
    if model_cfg_path is None or not os.path.exists(model_cfg_path):
        raise FileNotFoundError(f"Can't find AI Model Configuration ({model_cfg_path})")
    
    # Load AI Model Configuration
    model_cfg = load_json(model_cfg_path)
    if not pure_content:
        # the python api have to merge model config and task config
        model_cfg.update(task_cfg)
    
    # Get the AI Model Path
    model_path = model_cfg[framework].get("model_path")
    if model_path is None:
        raise KeyError(f"Can't find `.model_path` in Configuration ({model_cfg_path})")

    if not os.path.exists(model_path):
        raise FileNotFoundError(f"Can't find AI Model ({model_path})")
    
    # Get the Label file
    label_path = model_cfg[framework].get("label_path")
    if label_path is None or not os.path.exists(label_path):
        raise FileNotFoundError(f"Can't find Label file ({label_path})")

    return (task_cfg_path, model_cfg_path, task_cfg, model_cfg)

def modify_basic_params(src_data:dict, task_config:dict) -> dict:
    """ Update Basic Parameters in Task Configuration """
    logging.debug('Update Basic Parameters in Task Configuration')
    for key in ['name', 'source', 'source_type']:
        task_config[key] = src_data[ key ]
        logging.debug(f' - update ({key}): {task_config[key]} -> {src_data[key]}')
    return task_config

def modify_application_params(src_data:dict, task_config:dict) -> dict:
    """ Update Application Parameters in Task Configuration """

    app_key  = "application"

    if not (app_key in task_config):
        task_config.update( {app_key: {}} )

    app_form = str_to_json(src_data[app_key])

    # Update Each Key and Value
    trg_key = "name"
    if trg_key in app_form:    
        app_name = app_form[trg_key]
        task_config[app_key].update({ trg_key: app_name })

    trg_key = "depend_on"
    if trg_key in app_form:
        app_form[trg_key] = str_to_json(app_form[trg_key])

        if app_form[trg_key] != []:
            task_config[app_key].update( { trg_key: app_form[trg_key] } )

    trg_key = "logic"
    if trg_key in app_form:
        task_config[app_key].update( { trg_key: app_form[trg_key] } )
    
    trg_key = "logic_thres"
    if trg_key in app_form:
        task_config[app_key].update( { trg_key: int(app_form[trg_key]) } )
    
    trg_key = "alarm"
    if trg_key in app_form:
        task_config[app_key].update( { trg_key: app_form[trg_key] } )

    trg_key = "area_points"
    if trg_key in app_form:
        app_form[trg_key] = str_to_json(app_form[trg_key])

        if app_form[trg_key] != []:
            task_config[app_key].update( { trg_key: app_form[trg_key] } )

    trg_key = "area_vector"
    if trg_key in app_form:
        app_form[trg_key] = str_to_json(app_form[trg_key])

        if app_form[trg_key] != []:
            task_config[app_key].update( { trg_key: app_form[trg_key] } )

    trg_key = "sensitivity"
    if trg_key in app_form:
        task_config[app_key].update( { trg_key: app_form[trg_key] } )
    
    logging.debug("Update Application Parameters in Task Configuration: \n{}".format(task_config[app_key]))
    
    return task_config

def modify_model_params(src_data, model_config):
    """ Update Parameters in Model Configuration """

    logging.debug('Update Parameters in Model Configuration')

    af = current_app.config['AF']
    src_data["thres"] = float(src_data["thres"])
    
    for key, val in model_config[af].items():
        if key in ['device', 'thres']:
            model_config[af][key] = src_data[key]  
        logging.debug(f' - update ({key}): {val} -> { model_config[af][key] if key in model_config[af] else val}')

    return model_config

def modify_task_json(src_uuid:str, task_name:str, form:dict, need_copy:bool=False):
    """ Modify AI Task Configuration, could be using on Add AI Task and Edit AI Task
    
    - args
        - src_uuid  : reference UUID ( AI Task )
        - task_name : target task name
        - form      : target task configuration
        - need_copy : if in ADD mode then need copy whole folder from reference uuid 
    
    - workflow
        1. Get reference task information
        2. Copy or Move to target path by task_name
        3. Update new configuration via `form`
    """
    mode = "ADD" if need_copy else "EDIT"
    logging.info('Modify Task Configuration in [{}] mode'.format(mode))

    # --------------------------------------------------------
    # Pasre the old verions of task.json and model_config file
    src_name = current_app.config['TASK'][src_uuid]['name']
    src_path = current_app.config['TASK'][src_uuid]['path']

    ( src_task_config_path, src_model_config_path, task_cfg, model_cfg ) = \
        parse_task_info(src_name, pure_content=True)

    # --------------------------------------------------------
    # Update Task Path, Application Path and Model Path
    # Copy or Move Whole Folder depend on ADD or EDIT

    trg_path = src_path.replace(src_name, task_name, 1)
    task_cfg_path = src_task_config_path.replace(src_name, task_name, 1)
    model_cfg_path = src_model_config_path.replace(src_name, task_name, 1)
    task_cfg["prim"]["model_json"] = task_cfg["prim"]["model_json"].replace(src_name, task_name, 1)

    if need_copy:
        shutil.copytree(src_path, trg_path)        
    else:
        clear_config_buf(src_uuid)
        shutil.move(src_path, trg_path)

    # --------------------------------------------------------
    # Update Configuration
    logging.info(form)
    task_cfg = modify_basic_params(src_data = form, task_config = task_cfg)
    task_cfg = modify_application_params(form, task_cfg)
    model_cfg = modify_model_params(src_data = form, model_config = model_cfg)

    # --------------------------------------------------------
    # Update Configuration File
    write_json(task_cfg_path, task_cfg)
    write_json(model_cfg_path, model_cfg)

def get_task_json_pattern() -> dict:
    """ Define the Task Configuration Pattern """
    return {
        "application": {
            "name": "",
            "depend_on": []
        },
        "framework": current_app.config["AF"],
        "name": "",
        "source": "",
        "source_type": "",
        "prim": {
            "model_json": ""
        }
    }

def get_support_model_name(base_name):
    """ In order to fit legacy version, 
    the model content of the form data is the base name of the model file.
    for example: /workspace/model/yolov4.xml, the content in form is /yolov4.xml
    It's not compare with MODEL information in app.config, so we have to parse by ourself. """

    base_name = base_name.strip()

    if os.path.splitext(base_name)[1] == '':
        return base_name
    
    trg_model_name = None
    for model_name, model_data in current_app.config["MODEL"].items():
        if os.path.basename(model_data["model_path"]) == base_name:
            trg_model_name = model_name

    if not trg_model_name:
        raise KeyError("Can't find the target model ({}), support is [{}]".format(
            base_name, ', '.join(current_app.config["MODEL"].keys())
        ))
    return trg_model_name

def get_model_config(tag, arch=None):
    """ Get the basic configuration from web.ai.config """
    tag = tag.lower()
    ret_config = None
    if tag == 'cls':
        ret_config = cls_pattern
    
    elif tag == 'obj':
        
        assert arch, "Get Model Conifg Error, if you want to get obj config you have to provide arch ( [ yolo, yolov4 ] )"

        if 'yolov4' in arch:
            ret_config = obj_yolov4_pattern
        else:
            ret_config = obj_yolo_pattern
        
    else:
        raise KeyError('Get unkown tag: {}, support tag is [ cls, obj ]')

    # Change Framework
    framework = current_app.config.get('AF')
    
    temp = ret_config["framework"]
    ret_config.pop("framework", None)
    ret_config.update({framework: temp})
    
    return ret_config

def get_model_tag_from_arch(arch):
    """ Get tag ( [ resnet, yolo ] ) from training configuration """
    if "resnet" in arch:
        return 'cls'
    elif "yolo" in arch:
        return 'obj'

def gen_task_model_config(form:dict):
    """ Generate a AI Task and AI Model Configuration 
    1. Combine the correct path
    2. Create a new AI Task Folder
    3. Generate Model Config which pattern is from ivit.web.ai.config
    4. Generate Task Config
    """

    # Define Basic Parameters
    framework = current_app.config.get('AF')
    task_conf_name = 'task.json'
    model_conf_name = "model.json"
    
    # Get Basic Parameters from input
    task_name   = form['name']
    task_model  = form['model']
    
    # Get the target path of Task and Model Configuration
    task_path   = os.path.join( current_app.config['TASK_ROOT'] , task_name )
    task_conf_path = os.path.join(task_path, task_conf_name)
    model_conf_path = os.path.join(task_path, model_conf_name)
    
    # -------------------------------------------------------------------------------------
    # Create a new model folder
    if not os.path.exists(task_path): 
        os.makedirs( task_path )
        logging.info('  - Create a folder for new AI Task ({})'.format(task_path))

    # -------------------------------------------------------------------------------------
    # Generate a Model Configuration
    model_data = current_app.config["MODEL"][task_model]
    model_conf = get_model_config( tag = model_data['tag'], arch = model_data['arch']  )

    model_conf["tag"] = model_data['tag']
    model_conf[framework]["model_path"]   = model_data['model_path']
    model_conf[framework]["label_path"]   = model_data['label_path']
    model_conf[framework]["anchors"]   = model_data['anchors']

    # -------------------------------------------------------------------------------------
    # Generate & Modify Task Configuration
    task_conf = get_task_json_pattern()
    task_conf["prim"]["model_json"] = model_conf_path
    task_conf = modify_basic_params(src_data = form, task_config = task_conf)
    task_conf = modify_application_params(form, task_conf)
    model_conf = modify_model_params(src_data = form, model_config = model_conf)

    # -------------------------------------------------------------------------------------
    # Update Configuration File
    write_json(task_conf_path, task_conf)
    write_json(model_conf_path, model_conf)

    logging.info(f" - Generate new AI Task configuration: {task_conf_path}")
    logging.info(f" - Generate new AI Model configuration: {model_conf_path}")

def print_dict(input:dict):
    for key, val in input.items():
        print(key, val)

def str_to_json(val):
    if type(val) == str:
        return json.loads(val)
    return val

def form_to_json(form):
    """ Convert form data to json """
    try:
        return json.loads(form)
    except Exception:
        return form

def load_json(path:str) -> dict:
    # --------------------------------------------------------------------
    # debug
    data = None
    if not os.path.exists(path):
        logging.error('File is not exists ! ({})'.format(path))
    elif os.path.splitext(path)[1] != '.json':
        logging.error("It's not a json file ({})".format(path))
    else:
        with open(path) as file:
            data = json.load(file)  # load is convert dict from json "file"
    return data

def write_json(path:str, data:dict):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)    # 縮排是4

def check_src_type(src:str) -> str:
    
    ret = ""
    map_table = {
        "V4l2":['dev', 'video'],
        "Video":['mp4', 'avi'],
        "Image":['jpg', 'png'],
        "RTSP":['rtsp'],
    }

    for key, val in map_table.items():
        for ext in val:
            if ext in src:
                ret = key
    logging.debug("The source type is {}".format(ret))
    return ret

def check_json(s):
    try:
        json.decode(s)
        return True
    except json.JSONDecodeError:
        return False

def pure_jsonify_2(in_dict, ret_dict, exclude_key:list=['api', 'runtime', 'palette', 'drawer', 'draw_tools'], include_key=[dict, list, str, int, float, bool]):    
    for key, val in in_dict.items():
        try:
            if (key in exclude_key):
                ret_dict[key]=str(type(val)) if val!=None else None
                continue
            if (type(val) in include_key ):
                ret_dict[key] = val
                pure_jsonify_2(in_dict[key], ret_dict[key])
            else:
                ret_dict[key] = str(type(val))
        except:
            continue

# ------------------------------------------------------------------------------------------------------------------------------------------------------
# 搭配 pure_jsonify 使用，由於該方法會將變數改變，所以透過 deepcopy 取得一個新的，只用於顯示 
def get_pure_jsonify(in_dict:dict, json_format=True)-> dict:
    ret_dict = dict()
    # temp_in_dict = copy.deepcopy(in_dict)
    temp_in_dict = in_dict
    pure_jsonify_2(temp_in_dict, ret_dict)
    # return ret_dict
    ret = json.dumps(ret_dict, cls=NumpyEncoder, indent=4)
    return json.loads(ret) if json_format else ret

class NumpyEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        elif isinstance(obj, np.float32):
            return float(obj)
        elif isinstance(obj, np.float64):
            return float(obj)
        elif isinstance(obj, np.int64):
            return int(obj)
        return json.JSONEncoder.default(self, obj)
