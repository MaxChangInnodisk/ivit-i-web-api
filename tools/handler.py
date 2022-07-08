from pyexpat import model
import sys, os, shutil, time, logging, copy, json
from typing import Tuple
from flask import current_app

from .parser import parse_task_info, write_json, check_src_type
from .common import gen_uuid
from init_i.app.handler import get_tag_app_list, get_app_list

DIV = '-'*30
APP_KEY = 'APPLICATION'
MODEL_KEY = 'MODEL'
MODEL_APP_KEY = 'MODEL_APP'
APP_MODEL_KEY = 'APP_MODEL'
TAG_APP = 'TAG_APP'
SRC_KEY = "SRC"



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

def modify_task_json(src_uuid:str, trg_an:str, form:dict, need_copy:bool=False):
    try:
        af = current_app.config['AF']
        # Pasre the old verions of task.json and model_config file
        [ src_an, src_path ] = [ current_app.config['TASK'][src_uuid][_key] for _key in ['name', 'path'] ]
        trg_path = src_path.replace(src_an, trg_an, 1)

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
        app_cfg_path = org_app_cfg_path.replace(src_an, trg_an, 1)
        model_cfg_path = org_model_cfg_path.replace(src_an, trg_an, 1)
        [ logging.debug(f' - update {key}: {org} -> {trg}') for (key, org, trg) in [ ("app_path", org_app_cfg_path, app_cfg_path), ("model_path", org_model_cfg_path, model_cfg_path) ] ]

        # Update app information
        logging.debug('Update information in {}'.format(app_cfg_path))
        form["thres"] = float(form["thres"])
        app_cfg["prim"]["model_json"] = app_cfg["prim"]["model_json"].replace(src_an, trg_an, 1)
        
        for key in ['name', 'source', 'source_type']:
            # the source key is different with configuration ( source )
            logging.debug(f' - update ({key}): {app_cfg[key]} -> {form[key]}')
            app_cfg[key] = form[ key ]
        
        # Update application with correct pattern
        tag_app_list = current_app.config[TAG_APP] if not ( TAG_APP in current_app.config ) else get_tag_app_list()
        
        available_app_list = [ app for apps in tag_app_list.values() for app in apps  ]

        # check if dictionary in string
        dict_app = False
        try:
            form["application"] = json.loads(form["application"])
            dict_app = True
            logging.info("Application is an string json ... ")
        except:
            form["application"] = form["application"]
            logging.info("Application is an dictionary")

        app_key = "application"
        
        if not dict_app:
            app_name = form[app_key]
            app_cfg[app_key] = { "name": app_name if app_name in available_app_list else "default" }

        else:

            trg_key = "name"
            if trg_key in form[app_key]:
                app_name = form[app_key][trg_key]
                if app_name in available_app_list:
                    
                    app_cfg['application'] = { trg_key: app_name }
                else:
                    logging.warning("Could not found application ({}) in available list ({})".format(app_name, available_app_list))
                    app_cfg['application'] = { trg_key: "default" } 

            trg_key = "area_points"
            if trg_key in form[app_key]:
                if type(form[app_key][trg_key])==str:
                    form[app_key][trg_key] = json.loads(form[app_key][trg_key])

                if form[app_key][trg_key] != []:
                    logging.debug("Found area_points")
                    app_cfg['application'].update( { trg_key: form[app_key][trg_key] } )

            trg_key = "depend_on"
            if trg_key in form[app_key]:
                
                if type(form[app_key][trg_key])==str:
                    form[app_key][trg_key] = json.loads(form[app_key][trg_key])

                logging.debug("Found depend_on ... {}".format( form[app_key][trg_key]))
                if form[app_key][trg_key] != []:
                    logging.debug("Update depend_on ... ")
                    app_cfg['application'].update( { trg_key: form[app_key][trg_key] } )

        logging.warning("Update Application Setting: {}".format(app_cfg['application']))

        # Update model information
        logging.debug('Update information in {}'.format(model_cfg_path))
        for key, val in model_cfg[af].items():
            if key in ['model_path', 'label_path']: 
                if model_cfg["tag"]=='pose' and key=="label_path":
                    pass
                else:
                    model_cfg[af][key] = val.replace(src_an, trg_an, 1) 
            if key in ['device', 'thres']:
                model_cfg[af][key] = form[key]  
            logging.debug(f' - update ({key}): {val} -> { model_cfg[af][key] if key in model_cfg[af] else val}')
        
        # Update json file
        write_json(app_cfg_path, app_cfg)
        write_json(model_cfg_path, model_cfg)
    except Exception as e:
        exc_type, exc_obj, exc_tb = sys.exc_info()
        fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
        msg = 'Modify JSON Error: \n{}\n{} ({}:{})'.format(exc_type, exc_obj, fname, exc_tb.tb_lineno)
        logging.error(msg)
        raise Exception(msg)
        # logging.raiseExceptions(msg)

        
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
                raise Exception(e)

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
    trg_an = form['name']
    
    modify_task_json(   src_uuid=src_uuid,
                        trg_an=trg_an,
                        form=form   )

    # Update UUID and TASK
    return init_tasks(trg_an, src_uuid)

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
    af, trg_an = current_app.config['AF'], form['name']
    task_path = os.path.join( current_app.config['TASK_ROOT'] , trg_an )
    if os.path.exists(task_path):
        msg="Task is already exist !!! ({})".format(task_path)
        raise Exception(msg)
    else:
        logging.info('The new application path: {}'.format(task_path))

    src_uuid = current_app.config['MODEL'][form['model']][0] if form['model'] in current_app.config['MODEL'].keys() else None
            
    if src_uuid==None:
        msg="Could not found the task which using the same model ..."
        logging.error(msg)
        raise Exception(msg)

    modify_task_json(   src_uuid=src_uuid,
                        trg_an=trg_an,
                        form=form,
                        need_copy=True   )

    # Update UUID and TASK
    return init_tasks(trg_an)

def remove_task(task_uuid):
    logging.warning("Delete {}".format(task_uuid))
    task_path = current_app.config['TASK'][task_uuid]['path']
    
    logging.debug(' - update APPLICATION')
    if 'application' in current_app.config['TASK'][task_uuid]:
        task_application = current_app.config['TASK'][task_uuid]['application']['name']
        if type(task_application)==str:
            task_application = [ task_application ]
        for app in task_application:
            current_app.config['APPLICATION'][app].remove(task_uuid)
    
    logging.debug(' - update SOURCE')
    if 'source' in current_app.config['TASK'][task_uuid]:
        task_src = current_app.config['TASK'][task_uuid]['source']
        current_app.config['SRC'][ task_src ]['proc'].remove(task_uuid)

    logging.debug(' - update MODEL')
    if 'model_path' in current_app.config['TASK'][task_uuid]:
        task_model = current_app.config['TASK'][task_uuid]['model_path'].split('/')[-1]
        if task_model in current_app.config['MODEL']:
            current_app.config['MODEL'][task_model].remove(task_uuid)

    logging.debug(' - update UUID')
    current_app.config['UUID'].pop(task_uuid, None)

    logging.debug(' - remove TASK')
    current_app.config['TASK'].pop(task_uuid, None)

    logging.debug(' - remove META DATA ({})'.format(task_path))
    if os.path.exists(task_path):
        shutil.rmtree(task_path)                     
    else:
        logging.warning('Folder is not found')

    return True

def import_task(form):
    """
    新增新的應用
    1. 根據選擇的 Application，去複製對應的模型、標籤、配置檔案
    2. 修改配置檔案的內容
    ---
    Form 
    Key: name, path, model_path, label_path, config_path, json_path, tag, application, device, source, thres, source_type
    """
    # model extension for double check
    MODEL_EXT = [ '.trt', '.engine', '.xml' ] 
    
    # get task_name and task_path
    framework = current_app.config['AF']
    task_name = form['name'].strip()
    src_path = form["path"]
    src_config_path = form["config_path"]
    src_json_path = form["json_path"]

    task_path = os.path.join( current_app.config['TASK_ROOT'] , task_name )

    # something, we could not store the model_path
    if form["model_path"]=="":
        logging.warning("Something went wrong in model_path, auto search again ...")
        for f in os.listdir(src_path):
            name, ext = os.path.splitext(f)
            if ext in MODEL_EXT:
                form["model_path"] = f
                logging.debug("Find the model path ({})".format(form["model_path"]))

    task_model_path = os.path.join( task_path, form["model_path"].split("/")[-1] )
    task_label_path = os.path.join( task_path, form["label_path"].split("/")[-1] )
    
    model_config_path = os.path.join( task_path, "{}.json".format( os.path.splitext(form["model_path"].split("/")[-1])[0] ))
    task_config_path = os.path.join( task_path, "task.json")

    task_tag = form["tag"]
    task_device = form["device"]
    task_source = form["source"]
    task_source_type = form["source_type"]
    task_thres = float(form["thres"])

    # create the folder for new task
    if os.path.exists(task_path):
        msg="Task is already exist !!! ({})".format(task_path)
        raise Exception(msg)
    else:
        os.makedirs(task_path)
        logging.info('The new task path: {}'.format(task_path))

    # move the file and rename
    os.rename( form["model_path"], task_model_path )
    os.rename( form["label_path"], task_label_path )
    
    # if is openvino model, we have to copy the .bin and .mapping file
    if current_app.config["AF"] == "openvino":
        org_path, trg_path = os.path.splitext(form["model_path"])[0], os.path.splitext(task_model_path)[0]
        ext_list = [ ".bin", ".mapping"]
        for ext in ext_list:
            org_file_path = "{}{}".format(org_path, ext)
            trg_file_path = "{}{}".format(trg_path, ext)
            os.rename( org_file_path, trg_file_path )
    
    # generate model config json
    try:
        # if you have different key in configuration, you have to add 
        logging.debug("Generate Model Config ... ")
        logging.debug("Detect TAG: {}".format(task_tag))
        try:
            if task_tag == "cls":
                from init_i.cls.config_template import TEMPLATE as model_config
            elif task_tag == "darknet":
                from init_i.darknet.config_template import TEMPLATE as model_config
            elif task_tag == "obj":
                from init_i.obj.config_template import TEMPLATE as model_config
        except Exception as e:
            logging.error(e)
            
        # modify the content
        model_config["tag"] = task_tag
        model_config[framework]["model_path"] = task_model_path
        model_config[framework]["label_path"] = task_label_path
        model_config[framework]["device"] = task_device
        model_config[framework]["thres"] = task_thres

        # log the training config to caputre the input_shape and preprocess
        with open( src_json_path, "r" ) as f:
            train_config = json.load(f)

        # update input shape
        h, w, c = train_config["model_config"]["input_shape"][:]
        model_config[framework]["input_size"] = "{},{},{}".format( c, h, w )
        
        # update preprocess
        if "process_mode" in train_config["train_config"]["datagenerator"] and framework != "openvino":
            model_config[framework]["preprocess"] = train_config["train_config"]["datagenerator"]["preprocess_mode"]
        else:
            # if no preprocess than set to caffe
            model_config[framework]["preprocess"] = "caffe"

        # update anchor
        anchor_key = "anchors"
        if anchor_key in train_config:
            anchors = [ float(anchor.strip(" "))  for anchor in train_config[anchor_key].split(",") ]
            logging.debug("Update anchor: {}".format(anchors))
            model_config[framework][anchor_key] = anchors
            model_config[framework]["architecture_type"] = "yolov4"

        # write information into model config file
        with open( model_config_path, "w" ) as out_file:
            json.dump( model_config, out_file )

    except Exception as e:
        raise Exception(e)

    # generate task config json
    try:
        task_config = {
            "framework": framework,
            "name": task_name,
            "source": task_source,
            "source_type": task_source_type,
            "application": { },
            "prim": {
                "model_json": model_config_path
            }
        }

        # check if dictionary in string
        dict_app = False
        try:
            logging.warning("Dict in application")
            form["application"] = json.loads(form["application"])
            dict_app = True
        except:
            form["application"] = form["application"]

        # update application
        tag_app_list = current_app.config[TAG_APP] if ( TAG_APP in current_app.config ) else get_tag_app_list()
        available_app_list = [ app for apps in tag_app_list.values() for app in apps  ]
        
        app_key = "application"
        if not dict_app:
            logging.info("detect string application")
            app_name = form[app_key]
            task_config['application'].update({ trg_key: app_name if app_name in available_app_list else "default" })
        else:

            trg_key = "name"
            if trg_key in form[app_key]:
                app_name = form[app_key][trg_key]
                task_config['application'].update({ trg_key: app_name if app_name in available_app_list else "default" })

            trg_key = "area_points"
            if trg_key in form[app_key]:
                form[app_key][trg_key] = json.loads(form[app_key][trg_key])
                if form[app_key][trg_key] != []:
                    logging.debug("Found area_points")
                    task_config['application'].update( { trg_key: form[app_key][trg_key] } )
            
            trg_key = "depend_on"
            if trg_key in form[app_key]:
                form[app_key][trg_key] = json.loads(form[app_key][trg_key])
                if form[app_key][trg_key] != []:
                    logging.debug("Found depend_on")
                    task_config['application'].update( { trg_key: form[app_key][trg_key] } )

        logging.warning("Update Application Setting: {}".format(task_config['application']))

        # write task config
        with open( task_config_path, "w") as out_file:
            json.dump( task_config, out_file)
    except Exception as e:
        raise Exception(e)

    # remove temperate file
    shutil.rmtree( src_path )

    return init_tasks( task_name )
    