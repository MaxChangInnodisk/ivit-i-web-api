import requests, json, logging, os, sys
sys.path.append(os.getcwd())
from ivit_i.utils.err_handler import handle_exception

from .common import get_address

HEAD_MAP = {
    "json": {'Content-type': 'application/json'}
}

def response_status(code):
    """ Return the response is success or not """
    return (str(code)[0] not in [ '4', '5' ])

def send_post_api(tb_url, data, h_type='json', timeout=10, stderr=True):
    """ Using request to simulate POST method """
    
    headers = HEAD_MAP[h_type]

    try:
        resp = requests.post(tb_url, data=json.dumps(data), headers=headers, timeout=timeout)
        code = resp.status_code
        data = { "status": code }

        # Convert Json
        try: resp_data = json.loads(resp.text)
        except Exception as e: resp_data = { "data": resp.text }
        
        # Update content of the response into data variable
        data.update(resp_data)
        return response_status(code), data

    except requests.Timeout:
        return False, { "data": f"Request Time Out !!! ({tb_url})", "status": 400 }

    except requests.ConnectionError:
        return False, { "data": f"Connect Error !!! ({tb_url})", "status": 400 }

    except Exception as e: 
        return False, { "data": f"Unxepected Error !!! ({handle_exception(e)})", "status": 400 }
    
def send_get_api(tb_url, h_type='json', timeout=10):
    """ Using request to simulate GET method """

    headers     = HEAD_MAP[h_type]

    try:
        resp = requests.get(tb_url, headers=headers, timeout=10)
        code = resp.status_code
        data = { "status": code }

        # Convert Json
        try: resp_data = json.loads(resp.text)
        except Exception as e: resp_data = { "data": resp.text }
        
        # Update content of the response into data variable
        data.update(resp_data)
        return response_status(code), data
    
    except requests.Timeout:
        return False, { "data": f"Request Time Out !!! ({tb_url})", "status": 400 }

    except requests.ConnectionError:
        return False, { "data": f"Connect Error !!! ({tb_url})", "status": 400 }
    
    except Exception as e: 
        return False, { "data": f"Unxepected Error !!! ({handle_exception(e)})", "status": 400 }
