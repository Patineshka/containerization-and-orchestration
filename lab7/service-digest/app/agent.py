import asyncio, json, time, uuid, re, logging
logging.basicConfig(level=logging.INFO)
log=logging.getLogger("digest")
from datetime import datetime, timezone
from contextlib import AsyncExitStack
from pathlib import Path
import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
app=FastAPI()
count=Counter('digest_runs_total','Digest runs',['scenario','status'])
latency=Histogram('digest_duration_seconds','Complete workflow duration',buckets=(1,5,15,30,60,120,300,600))
tools_count=Counter('digest_tool_calls_total','MCP tool calls',['tool','status'])
lock=asyncio.Lock()
class Request(BaseModel):
    scenario: str='healthy'
@app.get('/metrics')
def metrics(): return Response(generate_latest(),media_type=CONTENT_TYPE_LATEST)
@app.get('/health')
def health(): return {'status':'ok'}
@app.post('/digest')
async def digest(req: Request):
    if req.scenario not in ('healthy','outage','stale'): raise HTTPException(400,'Unknown scenario')
    if lock.locked(): raise HTTPException(429,'Another digest is running')
    async with lock:
        started=time.monotonic(); run_id=uuid.uuid4().hex[:10]
        filename=f'{req.scenario}-{run_id}.md'; trace=[]; called=set()
        log.info('START run=%s scenario=%s',run_id,req.scenario)
        try:
            async with AsyncExitStack() as stack:
                sessions={}; specs=[]
                for url in ('http://status-mcp:8000/mcp','http://runbooks-mcp:8000/mcp'):
                    streams=await stack.enter_async_context(streamablehttp_client(url))
                    session=await stack.enter_async_context(ClientSession(streams[0],streams[1]))
                    await session.initialize()
                    for tool in (await session.list_tools()).tools:
                        sessions[tool.name]=session
                        specs.append({'type':'function','function':{'name':tool.name,'description':tool.description,'parameters':tool.inputSchema}})
                messages=[{'role':'system','content':Path('/skills/duty-digest.md').read_text()}, {'role':'user','content':json.dumps({'scenario':req.scenario,'current_time_utc':datetime.now(timezone.utc).isoformat(),'filename':filename},ensure_ascii=False)}]
                async with httpx.AsyncClient(timeout=120) as client:
                    for step in range(10):
                        if time.monotonic()-started > 480: raise RuntimeError("Digest exceeded 8 minutes")
                        log.info("MODEL run=%s step=%s",run_id,step+1)
                        response=await client.post('http://host.docker.internal:11434/api/chat',json={'model':'qwen3-duty:4b','stream':False,'think':False,'messages':messages,'tools':specs,'options':{'temperature':0,'num_ctx':8192,'num_predict':1800}})
                        response.raise_for_status(); payload=response.json(); message=payload['message']
                        log.info('MODEL_DONE run=%s step=%s calls=%s tokens=%s',run_id,step+1,len(message.get('tool_calls',[])),payload.get('eval_count'))
                        messages.append(message)
                        calls=message.get('tool_calls',[])
                        if not calls:
                            required={'get_service_checks','get_oncall_contacts','get_runbook','save_digest'}
                            if not required.issubset(called):
                                messages.append({'role':'user','content':'Выполни оставшиеся обязательные инструменты: '+', '.join(sorted(required-called))})
                                continue
                            count.labels(req.scenario,'success').inc()
                            return {'run_id':run_id,'scenario':req.scenario,'file':filename,'summary':re.sub(r'<think>.*?</think>','',message.get('content',''),flags=re.S),'tool_calls':trace}
                        for call in calls:
                            name=call['function']['name']; args=call['function'].get('arguments',{})
                            if isinstance(args,str): args=json.loads(args)
                            if name=='get_service_checks': args={'scenario':req.scenario}
                            if name=='save_digest':
                                args['filename']=filename
                                if not {'get_service_checks','get_oncall_contacts','get_runbook'}.issubset(called):
                                    messages.append({'role':'tool','tool_name':name,'content':'Сначала успешно вызови get_runbook(service=shop-postgres), get_service_checks и get_oncall_contacts. После этого сохрани сводку.'}); continue
                            log.info('TOOL run=%s name=%s',run_id,name)
                            result=await asyncio.wait_for(sessions[name].call_tool(name,args),timeout=30)
                            ok=not result.isError
                            tools_count.labels(name,'success' if ok else 'error').inc()
                            trace.append({'tool':name,'arguments':args,'success':ok})
                            log.info('TOOL_DONE run=%s name=%s success=%s',run_id,name,ok)
                            if ok: called.add(name)
                            if ok and name=='save_digest':
                                log.info('SAVED run=%s file=%s',run_id,filename)
                                count.labels(req.scenario,'success').inc()
                                return {'run_id':run_id,'scenario':req.scenario,'file':filename,'summary':args.get('content',''),'tool_calls':trace}
                            text='\n'.join(getattr(x,'text','') for x in result.content)
                            messages.append({'role':'tool','tool_name':name,'content':text})
                    raise RuntimeError('Agent did not complete within 10 steps')
        except Exception as e:
            log.exception('FAILED run=%s',run_id)
            count.labels(req.scenario,'error').inc()
            raise HTTPException(502,str(e))
        finally:
            latency.observe(time.monotonic()-started)
            Path('/reports').mkdir(exist_ok=True)
            (Path('/reports')/f'{run_id}-trace.json').write_text(json.dumps(trace,ensure_ascii=False,indent=2))

if __name__=='__main__':
    import uvicorn
    uvicorn.run(app,host='0.0.0.0',port=8000,access_log=False)
