import json, urllib.request
url='http://localhost:11434'
def post(path,body):
    request=urllib.request.Request(url+path,data=json.dumps(body).encode(),headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(request,timeout=120) as response: return json.load(response)
data=post('/api/show',{'model':'qwen3:4b'})
template=data['template'].replace('<|im_start|>assistant\n<think>','<|im_start|>assistant\n<think>\n</think>\n')
print(post('/api/create',{'model':'qwen3-duty:4b','from':'qwen3:4b','template':template,'stream':False}))
