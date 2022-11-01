import sys, os, time, copy, logging
from flask import Blueprint, current_app
sys.path.append(os.getcwd())
try:
    from ivit_i.utils.draw_tools import Draw as vitis_draw
    from ivit_i.utils.draw_tools import get_palette
except Exception as e:
    logging.error(e)
# ------------------------------------------------------------------------
# Vitis-AI
""" 初始化 Vitis-AI """
def vitis_init(prim_conf, first_frame=None):
    logging.info('Init Vitis-AI')
    try:
        if 'obj' in prim_conf['tag']:
            from ivit_i.obj.yolov3 import YOLOv3 as trg
        if "cls" in prim_conf['tag']:
            from ivit_i.cls.classification import Classification as trg
        
        trg = trg(prim_conf)
        draw = vitis_draw()
        palette = get_palette(prim_conf)

        trg.init_model()

        runtime, palette = "Temp", palette
    
    except Exception as e:
        trg = e
        logging.error(e)
        runtime, palette, draw = None, None, None

    return trg, runtime, draw, palette

""" 進行 AI 辨識 """
def vitis_inference(frame, uuid, model_conf, trg, runtime, draw, palette, ret_draw=True):
    
    ret, info = False, None
    
    try:
        info = trg.inference(frame)
            
        if info is not None:
                
                if ret_draw:
                    info.update( { "frame": frame} )
                    frame = draw.draw_detections(info, palette, model_conf)
                ret = True
                info.pop('frame', None) # original
                info.pop('output_transform', None)    
                
                if not ('detections' in info.keys()):
                    logging.error('unexcepted key {}, should be "detections" in Vitis-AI'.format(info.keys()))
                else:
                    logging.debug('parse the results')
                    
                    for idx, det in enumerate(info['detections']): 
                        if model_conf['tag'] in ['cls', 'obj']:
                            # convert bounding box from float to int
                            for key in ['xmin', 'xmax', 'ymin', 'ymax']:
                                det[key] = int(float(det[key])) if det[key]!=None else det[key]
                            info['detections'][idx]=det
                        else:
                            logging.debug('not classification and object detection')
    
    except Exception as e:
        ret = False
        logging.error(e)

    return ret, info, frame
   