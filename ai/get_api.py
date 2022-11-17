from flask import current_app
import logging

def get_api(af=None):
    """
    import the custom ai module for web api
    """
    init = None
    trg_af = current_app.config['AF'] if af==None else af
    logging.info("Loading AI API ({}) ...".format(trg_af))
    if trg_af in ['tensorrt', 'TensorRT', 'trt']:
        try:
            from ivit_i.web.ai.tensorrt import trt_init 
            init = trt_init
        except Exception as e:
            raise Exception(e)

    elif trg_af in ['openvino', 'OpenVINO', 'vino']:
        try:
            from ivit_i.web.ai.openvino import vino_init
            init = vino_init
        except Exception as e:
            raise Exception(e)

    elif trg_af in ['vitis-ai', 'Vitis-ai', 'Vitis', 'vitis']:
        try:
            from ivit_i.web.ai.vitis import vitis_init
            init = vitis_init
        except Exception as e:
            raise Exception(e)
    
    if None in [init]:
        msg = "Could not import framework API, please check the script in ivit_i.web.ai"
        logging.error(msg)
        raise Exception(msg)
    return init