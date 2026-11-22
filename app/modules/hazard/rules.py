from collections import defaultdict
import re

def inspect(rows,context):
    issues=[];containers=defaultdict(set)
    for row in rows:
        category=row['hazard'].strip()
        if category=='none':continue
        if category not in context['hazards']:
            issues.append({'id':row['id'],'line':row['_line'],'code':'UNKNOWN_HAZARD'});continue
        if not re.fullmatch(r'UN\d{4}',row['un_code']):issues.append({'id':row['id'],'line':row['_line'],'code':'MISSING_UN'})
        containers[row['container']].add(category)
    for container,categories in sorted(containers.items()):
        for a,b in context['incompatible']:
            if a in categories and b in categories:issues.append({'id':container,'code':'INCOMPATIBLE','classes':f'{a}/{b}'})
    return issues

def apply(state):
    state['hazard_issues']=inspect(state['records'],state['context'])
    state['views']['hazard']={'title':'危险品核验','rows':state['hazard_issues'],'metrics':{'危险类':len({r['hazard'] for r in state['records'] if r['hazard']!='none'}),'阻断项':len(state['hazard_issues'])}}
