import logging, os
import uuid, sys, traceback
import subprocess as sp
import socket

from ivit_i.utils.err_handler import handle_exception

def get_devcie_info():
    ret  = {}
    try:
        from ivit_i.utils.devices import get_device_info as get_info
        ret.update(get_info())
    except Exception as e:
        raise Exception(handle_exception(e))

    return ret 

def get_nv_info():
    ret  = {
        "GPU": {
            "id": -1,
            "name": "GPU",
            "uuid": "", 
            "load": 0, 
            "memoryUtil": 0, 
            "temperature": 0
        }
    }
    try:
        import GPUtil
        gpus = GPUtil.getGPUs()
        ret = dict()
        for gpu in gpus:
            ret.update({ gpu.name: {
                    "id": gpu.id,
                    "name": gpu.name, 
                    "uuid": gpu.uuid, 
                    "load": round(gpu.load*100, 3), 
                    "memoryUtil": round(gpu.memoryUtil*100, 3), 
                    "temperature": gpu.temperature
            }})
    except Exception as e:
        handle_exception(e, "Get temperature error")
    
    return ret

def get_intel_info():
    avg = 0
    ret = {}
    try:
        import psutil
        KEY  ="coretemp"
        res  = psutil.sensors_temperatures() 
        temp = [ float(core.current) for core in res[KEY] ]
        avg  = sum(temp)/len(temp)
    except Exception as e:
        handle_exception(e, "Get temperature error")
        avg = 0

    cpu_info  = {
        "id": 0,
        "name": "CPU",
        "uuid": "", 
        "load": 0, 
        "memoryUtil": 0, 
        "temperature": avg
    }
    
    # Copy CPU infor to GPU
    gpu_info = cpu_info.copy()
    gpu_info['name'] = 'GPU'

    # Update information
    ret.update( { "CPU": cpu_info, "GPU": gpu_info } )    
    return ret

def get_xlnx_info():
    avg = 0
    try:
        cmd  = "xmutil platformstats -p | grep temperature | awk -F: {'print $2'} | awk {'print $1'}"
        temp = sp.run(cmd, shell=True, stdout=sp.PIPE, encoding='utf8').stdout.strip().split('\n')
        temp = [ float(val) for val in temp ]
        avg  = sum(temp)/len(temp)
    except Exception as e:
        handle_exception(e, "Get temperature error")
        avg = 0
        
    ret  = {
        "DPU": {
            "id": 0,
            "name": "DPU",
            "uuid": "", 
            "load": 0, 
            "memoryUtil": 0, 
            "temperature": avg
        }
    }
    return ret
    
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