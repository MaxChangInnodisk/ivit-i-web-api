import logging, os
import uuid, sys, traceback
import subprocess as sp
import socket

def get_nv_info():
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
    return ret

def get_intel_info():
    ret = {
        "CPU": {
            "id": 0,
            "name": "CPU",
            "uuid": "", 
            "load": 0, 
            "memoryUtil": 0, 
            "temperature": 0
        }
    }
    return ret

def get_xlnx_info():

    cmd = "xmutil platformstats -p | grep temperature | awk -F: {'print $2'} | awk {'print $1'}"
    temparature = sp.run(cmd, shell=True, stdout=sp.PIPE, encoding='utf8').stdout.strip().split('\n')

    ret = {
        "DPU": {
            "id": 0,
            "name": "DPU",
            "uuid": "", 
            "load": 0, 
            "memoryUtil": 0, 
            "temperature": temparature[0]
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
    ret = sp.run("ls /dev/video*", shell=True, stdout=sp.PIPE, encoding='utf8').stdout
    ret_list = ret.strip().split('\n')
    return ret_list

def handle_exception(error, title="Error", exit=False):
    
    # Get Error Class ( type )
    error_class = error.__class__.__name__ 
    
    # Get Detail
    detail = error.args[0] 

    # Get Call Stack
    cl, exc, tb = sys.exc_info() 

    # Last Data of Call Stack
    last_call_stack = traceback.extract_tb(tb)[-1] 

    # Parse Call Stack and Combine Error Message
    file_name = last_call_stack[0] 
    line_num = last_call_stack[1] 
    func_name = last_call_stack[2] 
    err_msg = "{} \nFile \"{}\", line {}, in {}: [{}] {}".format(title, file_name, line_num, func_name, error_class, detail)
    
    logging.error(err_msg)
    if exit: sys.exit()

    return err_msg