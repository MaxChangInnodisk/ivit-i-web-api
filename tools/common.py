import logging, os
import uuid, sys, traceback, json
import subprocess as sp
import socket
from flask import jsonify
from ivit_i.utils.err_handler import handle_exception, simple_exception

K_MESG  = "message"
K_CODE  = "status_code"
K_DATA  = "data"
K_TYPE  = "type"

def json_exception(content):
    err_type, err_detail = simple_exception(content)
    
    if not err_type in [ "ImageOpenError", "VideoOpenError", "RtspOpenError", "UsbCamOpenError" ]:
        err_type = "RuntimeError"
    
    return { 
        K_MESG: json.dumps(err_detail),
        K_TYPE: err_type 
    }

def http_msg(content, status_code):

    # Checking Input Type
    if not isinstance(status_code, int):
        raise TypeError(f"Status Code should be integer, but got {type(status_code)}")

    # Define Basic Format
    ret = {
        K_CODE: status_code,
        K_DATA: {},
        K_MESG: "",
        K_TYPE: ""
    }

    # If is Exception
    if isinstance(content, Exception):
        ret.update(json_exception(content=content))
        
    # If not Exception, check input content is String or Object
    elif isinstance(content, str):
        ret[K_MESG] = content

    else:
        ret[K_DATA] = content
    
    return jsonify(ret), status_code
    
def get_devcie_info():
    ret  = {}
    try:
        from ivit_i.utils.devices import get_device_info as get_info
        ret.update(get_info())
    except Exception as e:
        raise Exception(handle_exception(e))

    return ret 

def get_mac_address():
    macaddr = uuid.UUID(int = uuid.getnode()).hex[-12:]
    return ":".join([macaddr[i:i+2] for i in range(0,11,2)])

def get_address():
    st = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:       
        st.connect(('10.255.255.255', 1))
        IP = st.getsockname()[0]
    except Exception:
        IP = '127.0.0.1'
    finally:
        st.close()
    return IP

def gen_uuid(name:str, len:int=8) -> str:
    """
    Generate uuid for each application
    """
    return str(uuid.uuid4())[:len]

def get_v4l2() -> list:

    ret_status, ret_message = True, []

    # Get V4L2 Camera
    command = sp.run("ls /dev/video*", shell=True, stdout=sp.PIPE, encoding='utf8')
    
    # 0 means success
    if command.returncode == 0:

        # Parse Each Camera to a list
        ret_message = command.stdout.strip().split('\n')
        logging.debug("{}, {}".format(ret_message, type(ret_message)))
        
        # Check is failed_key in that information
        for msg in ret_message.copy():
            if int(msg.split("video")[-1])%2==1:
                # if N is even it's not available for opencv
                ret_message.remove(msg)
    
    # else not success
    else:
        ret_status  = False
        ret_message = "Camera not found"

    return ret_status, ret_message