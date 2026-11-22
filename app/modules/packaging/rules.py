from app.coerce import number
from app.errors import BusinessError
from app.reasons import reject

def normalize(row,context):
    units=context['packages'];weights={'kg':1,'t':1000}
    if row['package_unit'] not in units or row['weight_unit'] not in weights:raise BusinessError('BAD_UNIT','包装或重量单位无效')
    count=number(row['packages'])*number(units[row['package_unit']]);net=number(row['net'])*weights[row['weight_unit']];gross=number(row['gross'])*weights[row['weight_unit']]
    revision=number(row['revision'])
    if count<0 or count%1 or net<0 or gross<net or revision<1 or revision%1:raise BusinessError('INVALID_RANGE','件数或净毛重越界')
    return {**row,'pieces':int(count),'net_kg':str(net),'gross_kg':str(gross),'revision':int(revision)}
def apply(state):
    good=[]
    for row in state['records']:
        try:good.append(normalize(row,state['context']))
        except BusinessError as e:reject(state,row,e.code,e.message)
    state['records']=good;state['views']['packaging']={'title':'包装换算','rows':good,'metrics':{'映射行':len(good),'包装类型':len(state['context']['packages'])}}
