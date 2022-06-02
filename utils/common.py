import GPUtil, logging, os
import uuid
import subprocess
import socket

def get_gpu_info():
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
    ret = subprocess.run("ls /dev/video*",  text=True, shell=True, stdout=subprocess.PIPE).stdout
    ret_list = ret.strip().split('\n')
    return ret_list
