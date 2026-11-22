from fastapi import Request
from fastapi.templating import Jinja2Templates
from app.config import ROOT, META
from app.engine import evaluate
from app import store
from app.modules.notice import service

templates=Jinja2Templates(directory=str(ROOT/'app/templates'))

def render(request:Request,key):
    from app.main import DB_PATH
    run_id=request.query_params.get('run_id')
    if run_id:
        state=store.get(DB_PATH,run_id)
    else:
        state=store.save(DB_PATH,evaluate({'dataset':request.query_params.get('dataset','dirty')}))
    if key=='notice':
        batch_id=request.query_params.get('batch_id', META['batch'])
        sheet_data=service.sheet(DB_PATH,batch_id,state)
        from app.modules.notice import store as notice_store
        for notice in sheet_data['notices']:
            notice['deliveries']=notice_store.list_deliveries(DB_PATH,notice['notice_no'])
        return templates.TemplateResponse(request=request,name='notice.html',
            context={'meta':META,'key':key,'state':state,'sheet':sheet_data})
    return templates.TemplateResponse(request=request,name=f'{key}.html',context={'meta':META,'key':key,'state':state,'view':state['views'][key]})
