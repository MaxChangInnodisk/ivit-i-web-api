import requests, json, logging, os, sys
sys.path.append(os.getcwd())
from ivit_i.utils.err_handler import handle_exception

from .common import get_address

TB_KEY_NAME     = "name" 
TB_KEY_TYPE     = "type" 
TB_KEY_ALIAS    = "alias"

TB_KEY_TIME_CREATE  = "createdTime"
TB_KEY_TOKEN_TYPE   = "credentialsType"
TB_KEY_ID           = "id"
TB_KEY_TOKEN        = "accessToken"

TB_TYPE         = "iVIT-I"
TB_NAME         = "iVIT-I-{}".format(get_address())
TB_ALIAS        = TB_NAME

HEAD_MAP = {
    "json": {'Content-type': 'application/json'}
}

def post_api(tb_url, data, h_type='json', timeout=10, stderr=True):
    """ Using request to simulate POST method """
    headers     = HEAD_MAP[h_type]
    
    try:
        resp = requests.post(tb_url, data=json.dumps(data), headers=headers, timeout=timeout)
        code = resp.status_code

        # Convert Json
        try: data = json.loads(resp.text)
        except Exception as e: data = resp.text
        print(code, resp)
        return code, { 
            "data": data,
            "status": code
        }

    except requests.Timeout:
        return 400, "Request Time Out !!! ({})".format(tb_url)

    except requests.ConnectionError:
        return 400, "Connect Error !!! ({})".format(tb_url)
    
def get_api(tb_url, h_type='json', timeout=10):
    """ Using request to simulate GET method """
    headers     = HEAD_MAP[h_type]

    try:
        resp = requests.get(tb_url, headers=headers, timeout=10)
        code = resp.status_code
        
        # Convert Json
        try: data = json.loads(resp.text)
        except Exception as e: data = resp.text
        
        # Update Status Code into Response
        return code, { 
            "data": data,
            "status": code
        }
        
    except Exception as e: 
        return 400, { "data": handle_exception(e) }
    
def register_tb_device(tb_url):
    """
    Register Thingsboard Device
    ---
    - Web API: http://10.204.16.110:3000/api/v1/devices
    - Method: POST
    - Data:
        - Type: JSON
        - Content: {
                "name"  : "ivit-i-{IP}",
                "type"  : "iVIT-I",
                "alias" : "ivit-i-{IP}"
            }
    - Response:
        - Type: JSON
        - Content: {
                "data": {
                    "createdTime": 1662976363031,
                    "credentialsType": "ACCESS_TOKEN",
                    "id": "a5636270-3280-11ed-a9c6-9146c0c923c4",
                    "accessToken": "auWZ5o6exyX9eWEmm7p3"
                }
            }
    """

    
    create_time, device_id, device_token = "", "", ""

    data = { 
        TB_KEY_NAME  : TB_NAME,
        TB_KEY_TYPE  : TB_TYPE,
        TB_KEY_ALIAS : TB_ALIAS
    }

    header = "http://"
    if ( not header in tb_url ): tb_url = header + tb_url

    timeout = 3
    logging.warning("[ iCAP ] Register Thingsboard Device ... ( Time Out: {}s ) \n{}".format(timeout, data))
    print('')
    
    ret, data    = post_api(tb_url, data, timeout=timeout, stderr=False)

    if(ret):
        logging.warning("[ iCAP ] Register Thingsboard Device ... Pass ! \n{}".format(data))
        logging.warning("Get Response: {}".format(data))

        data            = data["data"]
        create_time     = data[TB_KEY_TIME_CREATE]
        device_id       = data[TB_KEY_ID]
        device_token    = data[TB_KEY_TOKEN]
    else:
        logging.warning("[ iCAP ] Register Thingsboard Device ... Failed !")

    return ret, (create_time, device_id, device_token)

if __name__ == "__main__":
    register_tb_device("http://10.204.16.110:3000/api/v1/devices")