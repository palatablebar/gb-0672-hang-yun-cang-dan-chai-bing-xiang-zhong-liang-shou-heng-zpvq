from decimal import Decimal

def check_weights(rows,graph):
    nodes={r['id']:r for r in rows};results=[]
    for parent,children in sorted(graph['children'].items()):
        if not children:continue
        p=nodes[parent]
        sums={'pieces':sum(nodes[c]['pieces'] for c in children),'net_kg':sum((Decimal(nodes[c]['net_kg']) for c in children),Decimal(0)), 'gross_kg':sum((Decimal(nodes[c]['gross_kg']) for c in children),Decimal(0))}
        for field,total in sums.items():
            declared=Decimal(str(p[field]));difference=declared-Decimal(str(total))
            results.append({'id':parent,'field':field,'declared':str(declared),'children_sum':str(total),'difference':str(difference),'code':'BALANCED' if not difference else 'WEIGHT_MISMATCH'})
    return results

def apply(state):
    state['weight_checks']=check_weights(state['records'],state['graph'])
    state['views']['weight']={'title':'逐层守恒','rows':state['weight_checks'],'metrics':{'检查项':len(state['weight_checks']),'差异项':sum(r['code']!='BALANCED' for r in state['weight_checks'])}}
