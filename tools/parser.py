import os, logging, json
from typing import Tuple
from flask import current_app, request
import numpy as np
from ivit_i.utils.err_handler import handle_exception

DIV = "-"*3 + "\n"
FRAMEWORK_LIST = ['tensorrt', 'openvino' ]

def special_situation(model_cfg):
    """
    define custom situation for model_path and label path
    """
    def get_framework(model_cfg):
        if ("framework" in model_cfg.keys()):
            return model_cfg["framework"]
        else:
            for framework in FRAMEWORK_LIST:
                if framework in model_cfg.keys():
                    return framework
    
    return True if get_framework(model_cfg)=="openvino" and model_cfg['tag']=="pose" else False    

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
    # placeholder for each variable
    ret, task_cfg_path, model_cfg_path, task_cfg, model_cfg, err = False, None, None, None, None, ""
    
    # get the configuration path
    try:
        task_cfg_path = os.path.join( os.path.join(current_app.config["TASK_ROOT"], path), current_app.config["TASK_CFG_NAME"])
        
        # checking the application path
        if os.path.exists(task_cfg_path):
            
            task_cfg = load_json(task_cfg_path)
            framework = task_cfg["framework"]
            logging.debug(task_cfg)
            if task_cfg=="":
                logging.error("Configuration Error, please check again ...")

            # capturing the model config path
            if "prim" in task_cfg.keys():
                model_cfg_path = task_cfg["prim"]["model_json"] if "model_json" in task_cfg["prim"] else None
            else:
                model_cfg_path = task_cfg["model_json"] if "model_json" in task_cfg else None
            if model_cfg_path != None:

                # cheching the model config path
                if os.path.exists(model_cfg_path):
                    model_cfg = load_json(model_cfg_path)
                    
                    # the python api have to merge each config
                    if not pure_content:
                        model_cfg.update(task_cfg)
                    
                    # checking the model path
                    if "model_path" in model_cfg[framework]:
                        
                        if os.path.exists(model_cfg[framework]["model_path"]):
                            
                            # checking the label path
                            if special_situation(model_cfg):
                                ret=True
                            else:
                                if os.path.exists(model_cfg[framework]["label_path"]):
                                    ret=True
                                else:
                                    err = "Could not find the path to label ({})".format(model_cfg['label_path'])
                        else:
                            err = "Could not find the path to model ({})".format(model_cfg[framework]['model_path']) 
                    else:
                        err = "Could not find the key of the model_path"
                else:
                    err = "Could not find the model configuration's path ({})".format(model_cfg_path)
            else:
                err = "Could not find the key of the model configuration ({})".format("model_path")    
        else:
            err = "Could not find the path to application's configuration ({})".format(task_cfg_path)
    except Exception as e:
        err = handle_exception(e)

    if err != "": logging.error(err)
    return ret, (task_cfg_path, model_cfg_path, task_cfg, model_cfg), err

# ------------------------------------------------------------------------------------------------------------------------------------------------------

def print_dict(input:dict):
    for key, val in input.items():
        print(key, val)


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

def print_route():
    logging.info("Call WEB API -> {}".format(request.path))

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
