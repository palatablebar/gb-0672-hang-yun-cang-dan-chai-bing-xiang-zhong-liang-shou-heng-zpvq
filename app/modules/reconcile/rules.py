from decimal import Decimal

def reconcile(state):
    roots=set(state['graph']['roots']);root_rows=[r for r in state['records'] if r['id'] in roots]
    totals={'pieces':sum(r['pieces'] for r in root_rows),'net_kg':str(sum((Decimal(r['net_kg']) for r in root_rows),Decimal(0))),'gross_kg':str(sum((Decimal(r['gross_kg']) for r in root_rows),Decimal(0)))}
    mismatches=[k for k,v in totals.items() if Decimal(str(v))!=Decimal(str(state['context']['declaration'][k]))]
    c=state['counts'];row_total=len(state['records'])+len(state['quarantine'])+c['blank']+c['duplicate']+c['repeated_header']
    return {**totals,'input':c['input'],'accepted':len(state['records']),'quarantined':len(state['quarantine']),'row_balanced':row_total==c['input'],'declaration_differences':mismatches,'graph_errors':len(state['graph']['errors']),'weight_errors':sum(r['code']!='BALANCED' for r in state['weight_checks'])}

def apply(state):
    state['balance']=reconcile(state);state['views']['reconcile']={'title':'报关对账','rows':[state['balance']],'metrics':{'件数':state['balance']['pieces'],'净重_kg':state['balance']['net_kg'],'毛重_kg':state['balance']['gross_kg']}}
