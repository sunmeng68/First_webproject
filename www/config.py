# -*- coding: utf-8 -*-
import config_default

class Dict(dict):
    '''
    Simple dict but support access as x.y style.
    '''
    def __init__(self, names=(), values=(), **kw):
        super(Dict, self).__init__(**kw)
        for k, v in zip(names, values):
            self[k] = v

    def __getattr__(self, key):
        try:
            return self[key]
        except KeyError:
            raise AttributeError(r"'Dict' object has no attribute '%s'" % key)

    def __setattr__(self, key, value):
        self[key] = value

def merge(defaults,override):
    r={}
    for name,value in defaults.items():
        if name in override:#覆盖文件有此参数
            if isinstance(value,dict): #判断是否其value为dict
                r[name]=merge(value,override[name])#是的话，则创建新的字典后，调用原函数（递归）
            else:
                r[name]=override[name]#否则把覆盖配置文件的值导入
        else:
            r[name]=defaults[name]#如果覆盖文件没有，就继续使用默认值
    return r
def toDict(d):
    D = Dict()
    for k, v in d.items():
        D[k] = toDict(v) if isinstance(v, dict) else v
    return D

configs=config_default.configs

try:
    import config_override
    merge(configs,config_override.configs)
#    print(merge(config,config_override.configs))
except ImportError:
    pass

configs=toDict(configs)