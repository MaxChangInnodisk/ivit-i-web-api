from flask import current_app
import logging
from ivit_i.utils.err_handler import handle_exception
def get_api(af=None):
    """
    import the custom ai module for web api
    """
    init = None
    trg_af = current_app.config['AF'] if af==None else af
    logging.info("Loading AI API ({}) ...".format(trg_af))
    
    try:
        if trg_af in ['tensorrt', 'TensorRT', 'trt']:
            from ivit_i.web.ai.tensorrt import trt_init 
            init = trt_init

        elif trg_af in ['openvino', 'OpenVINO', 'vino']:
            from ivit_i.web.ai.openvino import vino_init
            init = vino_init

        elif trg_af in ['vitis-ai', 'Vitis-ai', 'Vitis', 'vitis']:
            from ivit_i.web.ai.vitis import vitis_init
            init = vitis_init

    except Exception as e:
        logging.error(handle_exception(e))
        raise Exception(e)
                
    if init == None:
        msg = "Could not import framework API, please check the script in ivit_i.web.ai"
        logging.error(msg)
        raise Exception(msg)
    
    return init