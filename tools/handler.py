from pyexpat import model
import sys, os, shutil, time, logging, copy, json
from typing import Tuple
from flask import current_app

from .parser import parse_task_info, write_json, check_src_type
from .common import gen_uuid, handle_exception


from ivit_i.app.handler import get_tag_app_list, get_app_list

DIV             = '-'*30
APP_KEY         = 'APPLICATION'
MODEL_KEY       = 'MODEL'
MODEL_APP_KEY   = 'MODEL_APP'
APP_MODEL_KEY   = 'APP_MODEL'
TAG_APP         = 'TAG_APP'
SRC_KEY         = "SRC"
UUID            = "UUID"
TASK            = "TASK"
APPLICATION     = "APPLICATION"
MODEL           = "MODEL"
SRC             = "SRC"

SRC_PROC        = "proc"

MODEL_EXT       = [ '.trt', '.engine', '.xml', '.xmodel' ] 


def init_task_app(task_uuid):
    """
    Initial application , app_model in configuration
        - application: relationship between the application and the task ( uuid ) 
        - app_model: relationship between the application and the model 
    """
    # initialize 
    task_app_key = APP_KEY.lower()
    task_apps = current_app.config['TASK'][task_uuid]['application']['name']
    info_table = {
        APP_KEY: task_uuid,
        APP_MODEL_KEY: current_app.config['TASK'][task_uuid]['model']
    } 
    
    # create key in config if needed
    for KEY in [APP_KEY, APP_MODEL_KEY, TAG_APP]:
        if not ( KEY in current_app.config ):
            current_app.config.update({ KEY: dict() })    

    # update information in app.config[...]
    if (task_apps != []) or (task_apps != None) or (task_apps != ""):
        # capture the application information and make sure list and string both are work like a charm
        apps = [task_apps] if type(task_apps)==str else task_apps
        for app in apps:
            # update each KEY about application
            for KEY in [APP_KEY, APP_MODEL_KEY]:
                if not (app in current_app.config[KEY]): 
                    current_app.config[KEY].update( { app : list() } )    
                # update infomration
                info = info_table[KEY]
                if not (info in current_app.config[ KEY ][app]): 
                    current_app.config[ KEY ][app].append(info)
    
    if not bool(current_app.config[TAG_APP]):
        current_app.config[TAG_APP] = get_tag_app_list()

def init_task_model(task_uuid):
    """
    Initial model , model_app in configuration
        - model: relationship between the model and the task ( uuid ) 
        - model_app: relationship between the model and the application
    """
    task_framework = current_app.config['AF']
    task_tag = current_app.config['TASK'][task_uuid]['tag']
    task_model = current_app.config['TASK'][task_uuid]['model']
    task_apps = current_app.config['TASK'][task_uuid]['application']['name']
    # update the key in config
    for KEY in [MODEL_KEY, MODEL_APP_KEY]:
        if not ( KEY in current_app.config.keys()):
            current_app.config.update( {KEY:dict()} )
        if not (task_model in current_app.config[KEY].keys()):
            current_app.config[KEY].update( {task_model:list()} )
    # update task uuid in model
    
    if not (task_uuid in current_app.config[MODEL_KEY][task_model]):
        current_app.config[MODEL_KEY][task_model].append(task_uuid)

    # update application in model_app
    tag_app_list = current_app.config[TAG_APP] if ( TAG_APP in current_app.config ) else get_tag_app_list()

    for app in tag_app_list[task_tag]:
        if not (app in current_app.config[MODEL_APP_KEY][task_model]):
            current_app.config[MODEL_APP_KEY][task_model].append( app )
    
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
    """ 
    Initialize each application, the UUID, application will be generated.
    """
    [ logging.info(cnt) for cnt in [ DIV, f"[{index:02}] Start to initialize application ({name})"] ]

    # Name
    name = name
    # UUID
    task_path = os.path.join( current_app.config["TASK_ROOT"], name )
    task_uuid = gen_uuid(name=name, len=8)
    if (name in current_app.config["UUID"].values()) and ( fix_uuid == None ):             
        # no need to initialize application if UUID is already exists
        logging.debug("UUID ({}) had already exist.".format(task_uuid))
    else:
        task_uuid = fix_uuid if fix_uuid != None else task_uuid 
        logging.debug("{} UUID hash table! {}:{}".format( 
            "Fixed" if fix_uuid !=None else "Update", task_uuid, name ))
        # if not in app.config then update
        if (not task_uuid in current_app.config['UUID'].keys()):
            current_app.config["UUID"].update( { task_uuid: name } )

    # Parse the information about this task
    ret, (app_cfg_path, model_cfg_path, app_cfg, model_cfg), err = parse_task_info(name)
    task_status = "stop" if ret else "error"
    task_framework = app_cfg["framework"] if ret else None

    # Update basic information
    current_app.config["TASK"].update({ 
        task_uuid:{ 
            "name": name,
            "framework": task_framework, 
            "path": task_path,
            "status": task_status, 
            "error": err,
    }})
    
    # If initialize success
    if task_status != "error":
        # Update information
        logging.debug("Update information to uuid ({})".format(task_uuid))

        # Double check application
        application_pattern = { "name": model_cfg["application"] } if type(model_cfg["application"])==str else model_cfg["application"]

        current_app.config["TASK"][task_uuid].update({    
            "tag": model_cfg["tag"],
            "application": application_pattern,
            "model": f"{model_cfg[task_framework]['model_path'].split('/')[-1]}",     # path to model
            "model_path": f"{model_cfg[task_framework]['model_path']}",     # path to model
            "label_path": f"{model_cfg[task_framework]['label_path']}",     # path to label 
            "config_path": f"{model_cfg_path}",             # path to model config
            "device": f"{model_cfg[task_framework]['device']}",
            "source" : f"{app_cfg['source']}",
            "source_type": f"{app_cfg['source_type'] if 'source_type' in app_cfg.keys() else check_src_type(app_cfg['source'])}",
            "output": None,
            "api" : None,       # api
            "runtime" : None,   # model or trt_obj
            "config" : model_cfg,    # model config
            "draw_tools" : None,
            "palette" : None, 
            "status" : "stop", 
            "cur_frame" : 0,
            "fps": None,
            "stream": None 
        })

        # Create new source if source is not in global variable
        try:
            init_task_src(   task_uuid )
        except Exception as e:
            logging.error(e)
        # Update the model list which could compare to the uuid who using this model
        try:
            init_task_model( task_uuid )   
        except Exception as e:
            logging.error(e)
        # Update the application mapping table: find which UUID is using the application
        try:
            init_task_app( task_uuid ) 
        except Exception as e:
            logging.error(e)

        logging.info('Create the global variable for "{}" (uuid: {}) '.format(name, task_uuid))
    else:
        logging.error('Failed to create the application ({})'.format(name))
    
    return (task_status, task_uuid, current_app.config['TASK'][task_uuid])

def str_to_json(val):
    if type(val) == str:
        return json.loads(val)
    return val

def modify_application_json(form, app_cfg):
    """
    Update the application parameters
    """


    # check if dictionary in string
    try:
        form["application"] = json.loads(form["application"])
        logging.info("Application is an string json ... ")
    except:
        form["application"] = form["application"]
        logging.info("Application is an dictionary")

    app_key  = "application"
    app_form = form[app_key]
    
    # Update Each Key and Value
    trg_key = "name"
    if trg_key in app_form:    
        app_name = app_form[trg_key]
        app_cfg[app_key] = { trg_key: app_name }
        
        # Update application with correct pattern
        # tag_app_list = current_app.config[TAG_APP] if not ( TAG_APP in current_app.config ) else get_tag_app_list()
        # available_app_list = [ app for apps in tag_app_list.values() for app in apps  ]        
        # if not (app_name in available_app_list):
        #     logging.warning("Could not found application ({}) in available list ({})".format(app_name, available_app_list))
        #     app_name = "default"
        
        # app_cfg[app_key] = { trg_key: app_name }

    trg_key = "depend_on"
    if trg_key in app_form:
        app_form[trg_key] = str_to_json(app_form[trg_key])

        if app_form[trg_key] != []:
            app_cfg[app_key].update( { trg_key: app_form[trg_key] } )

    trg_key = "logic"
    if trg_key in app_form:
        app_cfg[app_key].update( { trg_key: app_form[trg_key] } )
    
    trg_key = "logic_thres"
    if trg_key in app_form:
        app_cfg[app_key].update( { trg_key: int(app_form[trg_key]) } )
    
    trg_key = "alarm"
    if trg_key in app_form:
        app_cfg[app_key].update( { trg_key: app_form[trg_key] } )

    trg_key = "area_points"
    if trg_key in app_form:
        app_form[trg_key] = str_to_json(app_form[trg_key])

        if app_form[trg_key] != []:
            app_cfg[app_key].update( { trg_key: app_form[trg_key] } )

    trg_key = "area_vector"
    if trg_key in app_form:
        app_form[trg_key] = str_to_json(app_form[trg_key])

        if app_form[trg_key] != []:
            app_cfg[app_key].update( { trg_key: app_form[trg_key] } )

    trg_key = "sensitivity"
    if trg_key in app_form:
        app_cfg[app_key].update( { trg_key: app_form[trg_key] } )
    

    logging.warning("Update Application Setting: {}".format(app_cfg[app_key]))
    
    return app_cfg

def modify_task_json(src_uuid:str, task_name:str, form:dict, need_copy:bool=False):
    try:
        af = current_app.config['AF']
        # Pasre the old verions of task.json and model_config file
        [ src_an, src_path ] = [ current_app.config['TASK'][src_uuid][_key] for _key in ['name', 'path'] ]
        trg_path = src_path.replace(src_an, task_name, 1)

        ret, (org_app_cfg_path, org_model_cfg_path, app_cfg, model_cfg), err = parse_task_info(src_an, pure_content=True)

        # Check is Add or Edit        
        if need_copy:
            # Copy file from the other folder which has same model_path
            logging.debug('Copy all files from the same application folder')
            shutil.copytree(src_path, trg_path)    
        else:
            shutil.move(src_path, trg_path)
            # Clear the UUID and TASK information
            current_app.config['UUID'].pop(src_uuid, None)
            current_app.config['TASK'].pop(src_uuid, None)

        # Get path
        app_cfg_path = org_app_cfg_path.replace(src_an, task_name, 1)
        model_cfg_path = org_model_cfg_path.replace(src_an, task_name, 1)
        [ logging.debug(f' - update {key}: {org} -> {trg}') for (key, org, trg) in [ ("app_path", org_app_cfg_path, app_cfg_path), ("model_path", org_model_cfg_path, model_cfg_path) ] ]

        # Update Basic Parameters
        logging.debug('Update information in {}'.format(app_cfg_path))
        form["thres"] = float(form["thres"])
        app_cfg["prim"]["model_json"] = app_cfg["prim"]["model_json"].replace(src_an, task_name, 1)
        
        for key in ['name', 'source', 'source_type']:
            # the source key is different with configuration ( source )
            logging.debug(f' - update ({key}): {app_cfg[key]} -> {form[key]}')
            app_cfg[key] = form[ key ]
        
        # Update application
        app_cfg = modify_application_json(form, app_cfg)

        # Update model information
        logging.debug('Update information in {}'.format(model_cfg_path))
        for key, val in model_cfg[af].items():
            # if key in ['model_path', 'label_path']: 
            #     if model_cfg["tag"]=='pose' and key=="label_path":
            #         pass
            #     else:
            #         model_cfg[af][key] = val.replace(src_an, task_name, 1) 
            if key in ['device', 'thres']:
                model_cfg[af][key] = form[key]  
            logging.debug(f' - update ({key}): {val} -> { model_cfg[af][key] if key in model_cfg[af] else val}')
        
        # Update json file
        write_json(app_cfg_path, app_cfg)
        write_json(model_cfg_path, model_cfg)
    except Exception as e:
        msg = handle_exception(e, 'Modify JSON Error')
        logging.error(msg); raise Exception(msg)
        
def get_tasks(need_reset=False) -> list:
    """ 
    取得所有 APP：這邊會先進行 INIT 接著在透過 ready 這個 KEY 取得是否可以運行，最後回傳 ready, failed 兩個 List 
    """
    ret = { 
            "ready": [],
            "failed": [] 
        }
    # init all apps
    if need_reset:
        for idx, task in enumerate(os.listdir(current_app.config['TASK_ROOT'])):
            try:
                task_status, task_uuid, task_info = init_tasks(task, index=idx)
            except Exception as e:
                raise Exception(handle_exception(e))

    try:
        for task_uuid in current_app.config['UUID']:
            task_info = current_app.config['TASK'][task_uuid]
            
            task_status = task_info['status']
            # parse ready and failed applications
            ret["ready" if task_status!="error" else "failed"].append({
                "tag": task_info['tag'] if 'tag' in task_info else "",
                "framework": task_info['framework'], 
                "name": task_info['name'], 
                "uuid": task_uuid, 
                "status": task_status, 
                "error": task_info['error'], 
                "model": task_info['model'] if "model" in task_info else None,
                "application": task_info['application'] if "application" in task_info else None,
            })

    except Exception as e:
        exc_type, exc_obj, exc_tb = sys.exc_info()
        fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
        msg = 'Stream Error: \n{}\n{} ({}:{})'.format(exc_type, exc_obj, fname, exc_tb.tb_lineno)
        logging.error(msg)

    return ret

def edit_task(form, src_uuid):
    """
    編輯應用
    1. 取得該 TASK 的 UUID
    2. 找到 該 TASK 的路徑與相關檔案
    3. 根據相關資訊修改 app 與 config 內容
    4. 更新 HASH table 的 key （不更新 uuid 會被洗掉）
    4. 重新 initial 一次
    ---
    Form 
    Key: name, category, application, framework, device, source, thres
    """
    logging.info("Start to edit the task ({})".format(src_uuid))
    # Get original path and information
    src_an = current_app.config['TASK'][src_uuid]['name']
    src_path = current_app.config['TASK'][src_uuid]['path']

    # Get new path
    task_name = form['name']
    
    modify_task_json(   src_uuid=src_uuid,
                        task_name=task_name,
                        form=form   )

    # Update UUID and TASK
    return init_tasks(task_name, src_uuid)

def check_exist_task(task_path, need_create=False):
    """
    Double check task path and create it if need.
    """
    if os.path.exists(task_path):
        msg="Task is already exist !!! ({})".format(task_path)
        raise Exception(msg)
    else:
        if need_create: os.makedirs(task_path)
        logging.info('The new task path: {}'.format(task_path))

def add_task(form):
    """
    新增新的應用
    1. 根據選擇的 Application，去複製對應的模型、標籤、配置檔案
    2. 修改配置檔案的內容
    ---
    Form 
    Key: name, model, application, device, source, thres
    """
    # key_list = ['name', 'model', 'application', 'device', 'source', 'thres']
    
    # create the folder for new application
    task_name   = form['name']
    task_path   = os.path.join( current_app.config['TASK_ROOT'] , task_name )
    src_uuid    = current_app.config['MODEL'][form['model']][0] if form['model'] in current_app.config['MODEL'].keys() else None

    # Double check task and source
    check_exist_task(task_path)
    if src_uuid==None:
        msg="Could not found the task which using the same model ..."
        logging.error(msg); raise Exception(msg)

    # Modify task config
    modify_task_json(   src_uuid    = src_uuid,
                        task_name   = task_name,
                        form        = form,
                        need_copy   = True   )

    # Update UUID and TASK
    return init_tasks(task_name)

def remove_task(task_uuid):

    try:
        # Get target task's basic information
        logging.warning("Delete {}".format(task_uuid))
        task_path   = current_app.config[TASK][task_uuid]['path']
        task_name   = current_app.config[UUID][task_uuid]

        # If target task is an error task it would not have model_path
        task_model  = ""
        if "model_path" in current_app.config[TASK][task_uuid]:
            task_model  = current_app.config[TASK][task_uuid]["model_path"].split('/')[-1]
        
        # Update Application
        if 'application' in current_app.config[TASK][task_uuid]:
            
            task_app = current_app.config[TASK][task_uuid]['application']['name']
            task_app = [ task_app ] if type(task_app)==str else task_app

            # Delete UUID in each application ( Multi Application is supported )
            for app in task_app:
                current_app.config[APPLICATION][app].remove(task_uuid)
                logging.debug(' - remove {} from app.config[{}][{}], check /application'.format(
                    task_uuid,
                    APPLICATION,
                    app
                ))

        # Update Source
        if 'source' in current_app.config[TASK][task_uuid]:

            task_src = current_app.config[TASK][task_uuid]['source']
            current_app.config[SRC][ task_src ][SRC_PROC].remove(task_uuid)

            logging.debug(' - remove {} from app.config[{}][{}][{}], check /src'.format(
                task_uuid,
                SRC,
                task_src,
                SRC_PROC
            ))

        # Remove UUID in config[UUID]
        logging.debug(' - update UUID')
        current_app.config[UUID].pop(task_uuid, None)

        # Remove task in config[TASK]
        logging.debug(' - remove TASK')
        current_app.config[TASK].pop(task_uuid, None)

        # Update Model
        if task_model in current_app.config[MODEL]:
            logging.debug(' - update MODEL')
            current_app.config[MODEL][task_model].remove(task_uuid)


        # Update MODEL_APP
        if task_model in current_app.config[MODEL]:
            if current_app.config[MODEL][task_model] == []:
                current_app.config[MODEL_APP_KEY].pop(task_model, None)

                logging.debug(' - remove {} from app.config[{}], check /model_app'.format(
                    task_model,
                    MODEL_APP_KEY
                ))

        logging.debug(' - remove DATA ({})'.format(task_path))
        if os.path.exists(task_path): shutil.rmtree(task_path)
        
        return True, "Remove Task ({}) Successed!".format(task_uuid)
    
    except Exception as e:

        return False, handle_exception(e, "Remove error")

def get_model_config_template(task_tag):
    model_config = None
    logging.debug("Detect TAG: {}".format(task_tag))
    try:
        if task_tag == "cls":
            from ivit_i.cls.config_template import TEMPLATE as model_config
        elif task_tag == "darknet":
            from ivit_i.darknet.config_template import TEMPLATE as model_config
        elif task_tag == "obj":
            from ivit_i.obj.config_template import TEMPLATE as model_config
    except Exception as e:
        msg = handle_exception(e, "Could not get model configuration templates")
        logging.error(msg); raise ImportError(msg)

    return model_config

def copy_model_event(src_model_path, task_model_path):
    
    logging.info('Copy Model Event: From {} to {}'.format(src_model_path, task_model_path))

    os.rename( src_model_path, task_model_path )
    
    # if is openvino model, we have to copy the .bin and .mapping file
    if current_app.config["AF"] == "openvino":
        org_path = os.path.splitext(src_model_path)[0]
        trg_path = os.path.splitext(task_model_path)[0]

        ext_list = [ ".bin", ".mapping"]
        for ext in ext_list:
            org_file_path = "{}{}".format(org_path, ext)
            trg_file_path = "{}{}".format(trg_path, ext)
            
            if not os.path.exists(org_file_path):
                logging.error("Could not find {}, make sure the ZIP file is for Intel".format(org_file_path))
                return False

            os.rename( org_file_path, trg_file_path )
            logging.info("\t- Rename: {} -> {}".format(org_file_path, trg_file_path))

    return True

def copy_label_event(src, trg):
    
    logging.info('Copy Label Event')

    ret = True
    os.rename( src, trg )
    logging.info('\t- Rename: {} -> {}'.format(src, trg))
    return ret

def parse_train_config(train_config):
    """
    Parsing Train Configuration From iVIT-T ( input_size, preprocess, anchors, architecture_type).
    """

    # Init
    ret_dict = {}
    
    # Update Input Size
    h, w, c = train_config["model_config"]["input_shape"][:]
    ret_dict["input_size"] = "{},{},{}".format( c, h, w )

    # Set default pre-process
    ret_dict["preprocess"] = "caffe"
    
    # Update preprocess
    if "preprocess_mode" in train_config["train_config"]["datagenerator"] and train_config["platform"] != "openvino":
        ret_dict["preprocess"] = train_config["train_config"]["datagenerator"]["preprocess_mode"]
        logging.warning('Detect pre-process mode, set to: {}'.format(ret_dict["preprocess"]))
        
    # Update anchor
    if "anchors" in train_config:
        anchors = [ float(anchor.strip(" "))  for anchor in train_config["anchors"].split(",") ]
        ret_dict["anchors"] = anchors        
        ret_dict["architecture_type"] = "yolov4"

        logging.debug("Update anchor: {}".format(anchors))
        logging.debug("Update architecture: {}".format(ret_dict["architecture_type"]))

    return ret_dict

def import_task(form):
    """
    Import new task according to the dictionaray data
    """
    logging.info('Import Task')

    # get task_name and task_path
    task_name       = form['name'].strip()
    src_path        = form["path"]
    src_config_path = form["config_path"]
    src_json_path   = form["json_path"]
    src_model_path  = form["model_path"]
    src_label_path  = form["label_path"]
    
    framework       = current_app.config['AF']
    task_dir        = current_app.config['TASK_ROOT']
    model_dir       = current_app.config['MODEL_DIR']
    
    src_model_name  = src_model_path.strip().split('/')[-1]
    src_label_name  = src_label_path.strip().split('/')[-1]
    src_model_pure_name   = os.path.splitext(src_model_name)[0]

    dst_model_dir   = os.path.join( model_dir, src_model_pure_name )
    if( not os.path.exists(dst_model_dir) ): os.makedirs( dst_model_dir )
    
    task_path = os.path.join( task_dir , task_name )

    # create the folder for new task
    check_exist_task(task_path, need_create=True)

    # double check file
    if src_model_path=="":
        raise Exception('Import Error: no model path in form data and could not find model in temporary folder ({}) ... '.format(src_path))

    # define configuration path
    model_config_path = os.path.join( task_path, "{}.json".format( src_model_pure_name ))
    task_config_path = os.path.join( task_path, "task.json")

    # define task config parameters
    task_tag            = form["tag"]
    task_device         = form["device"]
    task_source         = form["source"]
    task_source_type    = form["source_type"]
    task_thres          = float(form["thres"])

    # concate target path
    dst_model_path = os.path.join( dst_model_dir, src_model_name )
    dst_label_path = os.path.join( dst_model_dir, src_label_name )
    
    # move the file and rename
    copy_model_flag = copy_model_event( src_model_path, dst_model_path )
    copy_label_flag = copy_label_event( src_label_path, dst_label_path )

    if( not ( copy_label_flag or copy_model_flag ) ):
        msg = "Something went wrong when copy file, please check log file. auto remove {}".format(task_path)
        shutil.rmtree( task_path ); raise Exception(msg)
    
    # generate model config json

    # if you have different key in configuration, you have to add 
    logging.info("Start to Generate Model Config ... ")
    
    # Get configuration template
    model_config = get_model_config_template(task_tag)    
    
    # modify the content
    model_config["tag"] = task_tag
    model_config[framework]["model_path"]   = dst_model_path
    model_config[framework]["label_path"]   = dst_label_path
    model_config[framework]["device"]       = task_device
    model_config[framework]["thres"]        = task_thres
    
    try:
        # update input_size, preprocess, anchors
        with open( src_json_path, "r" ) as f:
            train_config = json.load(f)
        model_config[framework].update( parse_train_config(train_config) )

        # write information into model config file
        with open( model_config_path, "w" ) as out_file:
            json.dump( model_config, out_file )
        logging.info("Generated Model Config \n{}".format(model_config))
    except Exception as e:
        raise Exception(handle_exception(e, 'Generated Modal Config Error'))

    # generate task config json

    logging.info("Start to Generate Task Config ... ")

    task_config = {}
    task_config["framework"]    = framework
    task_config["name"]         = task_name
    task_config["source"]       = task_source
    task_config["source_type"]  = task_source_type
    task_config["prim"] = { "model_json": model_config_path }

    # Update Application
    task_config.update( modify_application_json(form, {} ) )
    try:
        # write task config
        with open( task_config_path, "w") as out_file:
            json.dump( task_config, out_file)
        logging.info("Generated Task Config \n{}".format(task_config))
    except Exception as e:
        raise Exception(handle_exception(e, 'Generated Task Config Error'))

    # remove temperate file
    shutil.rmtree( src_path )
    logging.warning(f'Clear temperate task folder ({src_path})')
    
    logging.info("Finished Import Task !!!")
    return init_tasks( task_name )
    