import os, logging, json
from typing import Tuple
from flask import current_app, request
import numpy as np

def taskErrorHandler(title:str, content:str):
    ret = "{}: {}".format(title[0].upper() + title[1:], content)
    logging.error(ret)
    return ret 

def configError(content:str):
    return taskErrorHandler("configError", content)

def fileNotFoundError(content:str):
    return taskErrorHandler("fileNotFoundError", content)

def runtimeError(content:str):
    return taskErrorHandler("runtimeError", content)

def parse_task_info(path:str, pure_content:bool=False) -> Tuple[bool, tuple, str]:
    """
    Parsing the application informations and return the initialize status, error message and relative informations.
    
    - Input
        - path              : path to application folder
        - pure_content      : the task_cfg will merge to model_cfg when pure_content is False
    - Output
        - ret               : if application initailize failed the 'ret' will be False
        - task_cfg_path      : path to application configuration
        - model_cfg_path    : path to model configuration
        - task_cfg           : the content of application configuration with json format
        - model_cfg         : the content of model configuration with json format
        - err               : if application initailize failed the error message will push into 'err'.
    """
    # Define Variables
    null_data = (None,None,None,None)
    
    # Get the task folder and config path
    task_dir_path = os.path.join(current_app.config["TASK_ROOT"], path )
    task_cfg_path = os.path.join( task_dir_path, "task.json")

    if not os.path.exists(task_cfg_path):
        return False, null_data, \
            fileNotFoundError(f"Can't find AI Task Configuration ({task_cfg_path})")
    
    # Load AI Task Config
    task_cfg = load_json(task_cfg_path)
    framework = task_cfg["framework"]

    # Check AI Task Config Content
    if task_cfg=="" or task_cfg is None:
        return False, null_data, \
            fileNotFoundError(f"Get empty AI Task Configuration ! ({task_cfg_path})")

    # Get the model config path
    model_cfg_path = task_cfg["prim"].get("model_json")
    if model_cfg_path is None or not os.path.exists(model_cfg_path):
        return False, null_data, \
            fileNotFoundError(f"Can't find AI Model Configuration ({model_cfg_path})")
    
    # Load AI Model Configuration
    model_cfg = load_json(model_cfg_path)
    if not pure_content:
        # the python api have to merge model config and task config
        model_cfg.update(task_cfg)
    
    # Get the AI Model Path
    model_path = model_cfg[framework].get("model_path")
    if model_path is None:
        return False, null_data, \
            configError(f"Can't find `.model_path` in Configuration ({model_cfg_path})")

    if not os.path.exists(model_path):
        return False, null_data, \
            fileNotFoundError(f"Can't find AI Model ({model_path})")
    
    # Get the Label file
    label_path = model_cfg[framework].get("label_path")
    if label_path is None or not os.path.exists(label_path):
        return False, null_data, \
            fileNotFoundError(f"Can't find Label file ({label_path})")

    return True, (task_cfg_path, model_cfg_path, task_cfg, model_cfg), ""

# ------------------------------------------------------------------------------------------------------------------------------------------------------

def print_dict(input:dict):
    for key, val in input.items():
        print(key, val)

def str_to_json(val):
    if type(val) == str:
        return json.loads(val)
    return val

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
