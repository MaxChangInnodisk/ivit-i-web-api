import sys, os, shutil, time, logging, copy
from typing import Tuple
from flask import current_app

from .parser import parse_task_info, write_json, check_src_type
from .common import gen_uuid

DIV = '-'*30
APP_KEY = 'APPLICATION'
MODEL_KEY = 'MODEL'
SRC_KEY = "SRC"

def init_task_app(task_uuid, app_cfg):
    if not ( APP_KEY in current_app.config ):
        # update app.config['APPLICATION'] if needed
        current_app.config.update({ APP_KEY: dict() })                            
    if app_cfg[APP_KEY.lower()] != []:
        for app in app_cfg[APP_KEY.lower()]:
            if not (app in current_app.config[APP_KEY]): 
                current_app.config[APP_KEY].update( { app : list() } )          # update app.config['APPLICATION'][ {application}] 
            if not (task_uuid in current_app.config[APP_KEY][app]): 
                current_app.config[APP_KEY][app].append(task_uuid)              # update app.config['APPLICATION'][ {application}][ {UUID}] 

def init_task_model(task_uuid, model_cfg):
    task_framework = current_app.config['AF']
    model_name = model_cfg[task_framework]['model_path'].split('/')[-1]
    if not ( MODEL_KEY in current_app.config.keys()):
        current_app.config.update( {MODEL_KEY:dict()} )
    if not (model_name in current_app.config[MODEL_KEY].keys()):
        current_app.config[MODEL_KEY].update( {model_name:list()} )
    if not (task_uuid in current_app.config[MODEL_KEY][model_name]):
        current_app.config[MODEL_KEY][model_name].append(task_uuid)

def init_task_src(task_uuid, source, source_type=None):
    """ 
    Initialize Source: 
        1. Update to app.config['SRC']
        2. Append the uuid into app.config['SRC'][{source}]["proc"]         # means process
        3. Check is the source is exist ( support v4l2 and any file, but excepted rtsp ... )
    """
    
    if not (source in current_app.config[SRC_KEY].keys()):
        logging.info("Update source information")
        # Update information
        current_app.config[SRC_KEY].update({ 
            f"{source}" : { 
                "status": "stop",
                "proc": [],
                "type": source_type if source_type != None else check_src_type(source),
                "object": None,
                "detail": "",
            }
        })
    else:
        logging.info("Source is already exists ({})".format(source))
    # Add process into config
    if not ( task_uuid in current_app.config['SRC'][ source ]['proc'] ):
        logging.debug("Update process into source config")
        current_app.config[SRC_KEY][ source ]['proc'].append(task_uuid)
    
    # Clear process which unused
    [ current_app.config[SRC_KEY][ source ]['proc'].remove(uuid) for uuid in current_app.config[SRC_KEY][ source ]['proc'] if not (uuid in current_app.config['UUID']) ]
    
def init_tasks(name:str, fix_uuid:str=None, index=0) -> Tuple[bool, str]:
    """ 
    Initialize each application, the UUID, application will be generated.
    """
    [ logging.info(cnt) for cnt in [ DIV, f"[{index:02}] Start to initialize application ({name})"] ]

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
    #   * parse the category and application
    #   * model have to relative with application
    #   * so, we have to capture the model information, which model is been used by which uuid.
    if task_status != "error":

        # Update information
        logging.debug("Update information to uuid ({})".format(task_uuid))
        current_app.config["TASK"][task_uuid].update({    
            "application": model_cfg["application"],
            "model_path": f"{model_cfg[task_framework]['model_path']}",     # path to model
            "label_path": f"{model_cfg[task_framework]['label_path']}",     # path to label 
            "config_path": f"{model_cfg_path}",             # path to model config
            "device": f"{model_cfg[task_framework]['device']}",
            "source" : f"{app_cfg['source']}",
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
        init_task_src(   task_uuid, 
                    app_cfg['source'], 
                    app_cfg['source_type'] if 'source_type' in app_cfg.keys() else None   )
        
        # Update the application mapping table: find which UUID is using the application
        init_task_app( task_uuid,  app_cfg ) 

        # Update the model list which could compare to the uuid who using this model
        init_task_model( task_uuid, model_cfg )

        logging.info('Create the global variable for "{}" (uuid: {}) '.format(name, task_uuid))
    else:
        logging.error('Failed to create the application ({})'.format(name))
    
    return (task_status, task_uuid, current_app.config['TASK'][task_uuid])

def modify_task_json(src_uuid:str, trg_an:str, form:dict, need_copy:bool=False):
    af = current_app.config['AF']
    # Pasre the old verions of task.json and model_config file
    [ src_an, src_path ] = [ current_app.config['TASK'][src_uuid][_key] for _key in ['name', 'path'] ]
    trg_path = src_path.replace(src_an, trg_an)

    ret, (org_app_cfg_path, org_model_cfg_path, app_cfg, model_cfg), err = parse_task_info(src_an, pure_content=True)
    
    if need_copy:
        shutil.copytree(src_path, trg_path)    
    else:
        shutil.move(src_path, trg_path)
        # Clear the UUID and TASK information
        current_app.config['UUID'].pop(src_uuid, None)
        current_app.config['TASK'].pop(src_uuid, None)

    app_cfg_path = org_app_cfg_path.replace(src_an, trg_an)
    model_cfg_path = org_model_cfg_path.replace(src_an, trg_an)
    [ logging.debug(f' - update {key}: {org} -> {trg}') for (key, org, trg) in [ ("app_path", org_app_cfg_path, app_cfg_path), ("model_path", org_model_cfg_path, model_cfg_path) ] ]

    # Update app information
    logging.debug('Update information in {}'.format(app_cfg_path))
    app_cfg["prim"]["model_json"] = app_cfg["prim"]["model_json"].replace(src_an, trg_an)
    for key in ['name', 'application', 'source', 'source_type']:
        # the source key is different with configuration ( source )
        logging.debug(f' - update ({key}): {app_cfg[key]} -> {form[key]}')
        app_cfg[key] = form[ key ]
    
    # Update model information
    logging.debug('Update information in {}'.format(model_cfg_path))
    for key, val in model_cfg[af].items():
        if key in ['model_path', 'label_path']: 
            model_cfg[af][key] = val.replace(src_an, trg_an) 
        if key in ['device', 'thres']:
            model_cfg[af][key] = form[key]  
        logging.debug(f' - update ({key}): {val} -> { model_cfg[af][key] if key in model_cfg[af] else val}')
    
    # Update json file
    write_json(app_cfg_path, app_cfg)
    write_json(model_cfg_path, model_cfg)

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

    for task_uuid in current_app.config['UUID']:
        task_info = current_app.config['TASK'][task_uuid]
        task_status = task_info['status']
        # parse ready and failed applications
        ret["ready" if task_status!="error" else "failed"].append({
            "framework": task_info['framework'], 
            "name": task_info['name'], 
            "uuid": task_uuid, 
            "status": task_status, 
            "error": task_info['error'], 
            "model_path": task_info['model_path'] if "model_path" in task_info else None,
            "application": task_info['application'] if "application" in task_info else None,
        })
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

    # Copy file from the other folder which has same model_path
    logging.info('Copy all files from the same application folder')

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
    
    task_path = current_app.config['TASK'][task_uuid]['path']
    
    logging.debug(' - update APPLICATION')
    task_application = current_app.config['TASK'][task_uuid]['application']
    [ current_app.config['APPLICATION'][app].remove(task_uuid) for app in task_application ]
        
    logging.debug(' - update SOURCE')
    task_src = current_app.config['TASK'][task_uuid]['source']
    current_app.config['SRC'][ task_src ]['proc'].remove(task_uuid)

    logging.debug(' - update MODEL')
    task_model = current_app.config['TASK'][task_uuid]['model_path'].split('/')[-1]
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