from collections import defaultdict
from app.errors import BusinessError
from app.reasons import reject

def graph(rows):
    nodes={r['id']:r for r in rows};children=defaultdict(list);errors=[]
    for row in rows:
        parent=row['parent'].strip()
        if parent and parent not in nodes:errors.append({'id':row['id'],'code':'MISSING_PARENT','path':[parent]})
        elif parent:children[parent].append(row['id'])
    color={};stack=[];cycles=[]
    def visit(node):
        if color.get(node)==1:
            cycles.append(stack[stack.index(node):]+[node]);return
        if color.get(node)==2:return
        color[node]=1;stack.append(node)
        for child in sorted(children[node]):visit(child)
        stack.pop();color[node]=2
    for node in sorted(nodes):visit(node)
    for cycle in cycles:errors.append({'id':cycle[0],'code':'DEPENDENCY_CYCLE','path':cycle})
    roots=sorted(r['id'] for r in rows if not r['parent'].strip())
    return {'roots':roots,'children':dict(children),'errors':errors,'node_count':len(nodes)}
def apply(state):
    state['graph']=graph(state['records'])
    edges=[{'parent':p,'child':c} for p,children in state['graph']['children'].items() for c in children]
    state['views']['grouping']={'title':'拆并关系','rows':edges+state['graph']['errors'],'metrics':{'主单':len(state['graph']['roots']),'节点':state['graph']['node_count'],'图错误':len(state['graph']['errors'])}}
