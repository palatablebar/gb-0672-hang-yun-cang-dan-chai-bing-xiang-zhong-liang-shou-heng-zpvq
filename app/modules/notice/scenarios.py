"""通知签收演示场景：基于平衡舱单构造连续修订的整批重发链。"""
from app.config import ROOT
from app.engine import evaluate

SCENARIOS = {
    'v2_weight': {
        'label': '修订V2：M002毛重变化（部分受影响）',
        'replace': ('M002,,40,carton,400,440,kg', 'M002,,40,carton,400,448,kg'),
        'fail': False,
    },
    'v3_relation': {
        'label': '修订V3：M003新增拆并子单（关系变化）',
        'replace': ('M003-P2-2,M003-P2,1,pallet,0.1,0.11,t,none,,C003,1',
                    'M003-P2-2,M003-P2,1,pallet,0.1,0.11,t,none,,C003,1\n'
                    'M003-P3,M003,10,carton,100,110,kg,none,,C003,1'),
        'fail': False,
    },
    'v4_fail': {
        'label': '修订V4：M004净重变化（发布失败，保留未送达记录）',
        'replace': ('M004,,40,carton,400,440,kg', 'M004,,40,carton,420,440,kg'),
        'fail': True,
    },
    'v4_weight': {
        'label': '修订V4：M004净重变化（重试恢复后同版重发）',
        'replace': ('M004,,40,carton,400,440,kg', 'M004,,40,carton,420,440,kg'),
        'fail': False,
    },
}


def base_csv():
    return (ROOT / 'sample_data' / 'clean.csv').read_text()


def run_from_csv(csv_text):
    return evaluate({'dataset': 'clean', 'csv_text': csv_text})


def base_run():
    return run_from_csv(base_csv())


def scenario_run(key):
    spec = SCENARIOS[key]
    old, new = spec['replace']
    if old not in base_csv():
        raise KeyError(key)
    return run_from_csv(base_csv().replace(old, new)), spec
