# -*- coding: utf-8 -*-
import asyncio, os, inspect, logging, functools

from urllib import parse

from aiohttp import web

from API import *


#定义@get()
def get(path):
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args,**kw):
            return func(*args,**kw)
        wrapper.__method__='GET'
        wrapper.__route__=path
        return wrapper
    return decorator
#定义@post()
def post(path):
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args,**kw):
            return func(*args,**kw)
        wrapper.__method__='POST'
        wrapper.__route__=path
        return wrapper
    return decorator
#用inspect模块，创建几个函数用来获取URL处理函数与request参数之间的关系
def get_required_kw_args(fn):#收集没有默认值的命名关键字参数
    args =[]
    #返回传入的可调用函数的所有参数
    params=inspect.signature(fn).parameters#inspect模块是用来分析
    for name,param in params.items():
        if str(param.kind)=='KEYWORD_ONLY' and param.default == inspect.Parameter.empty:
            args.append(name)
    return tuple(args)
#获取命名关键字参数
def get_named_kw_args(fn):
    args=[]
    params = inspect.signature(fn).parameters
    for name, param in params.items():
        if str(param.kind) == 'KEYWORD_ONLY':
            args.append(name)
    return tuple(args)

def has_named_kw_arg(fn): #判断有没有命名关键字参数
    params = inspect.signature(fn).parameters
    for name,param in params.items():
        if str(param.kind) == 'KEYWORD_ONLY':
            return True

def has_var_kw_arg(fn): #判断有没有关键字参数
    params = inspect.signature(fn).parameters
    for name,param in params.items():
        if str(param.kind) == 'VAR_KEYWORD':
            return True

def has_request_arg(fn): #判断是否含有名叫'request'参数，且该参数是否为最后一个参数
    params = inspect.signature(fn).parameters
    sig = inspect.signature(fn)
    found = False
    for name,param in params.items():
        if name == 'request':
            found = True
            continue #跳出当前循环，进入下一个循环
        if found and (str(param.kind) != 'VAR_POSITIONAL' and str(param.kind) != 'KEYWORD_ONLY' and str(param.kind != 'VAR_KEYWORD')):
            raise ValueError('request parameter must be the last named parameter in function: %s%s'%(fn.__name__,str(sig)))
    return found


#RequestHandler目的就是从URL函数中分析其需要接收的参数，从request中获取必要的参数，调用URL函数，然后把结果转换为web.Response对象
class RequestHandler(object):
    #初始化类
    def __init__(self,app,fn):
        self._app=app
        self._fn=fn
        self._required_kw_args =get_required_kw_args(fn)
        self._named_kw_args=get_named_kw_args(fn)
        self._has_named_kw_arg=has_named_kw_arg(fn)
        self._has_var_kw_arg=has_var_kw_arg(fn)
        self._has_request_arg=has_request_arg(fn)

    async def __call__(self, request):
        kw=None
        if self._has_named_kw_arg or self._has_var_kw_arg:
            print(request.method)
            if request.method=='POST':
                #查询数据提交格式
                if not request.content_type:
                    return web.HTTPBadRequest(text='Missing Content_Type')
                ct=request.content_type.lower()#小写
                #检查字符串开头和结尾
                if ct.startswith('application/json'):
                    params = await request.json()
                    if not isinstance(params,dict):
                        return web.HTTPBadRequest(text='JSON body must be object')
                    kw=params
                elif ct.startswith('application/x-www-form-urlencoded')or ct.startswith('multipart/form-data'):
                    params =await request.post()
                    kw=dict(**params)

                else:
                    return web.HTTPBadRequest(text='Unsupported Content_Type:%s'%(request.content_type))
            if request.method=='GET':
                qs=request.query_string
                if qs:
                    kw=dict()
                    for k,v in parse.parse_qs(qs,True).items():
                        kw[k]=v[0]
        if kw is None:
            kw = dict(**request.match_info)
        else:
            if not self._has_var_kw_arg and self._named_kw_args:#当函数参数没有关键字,移去request除命名关键字参数所有的参数信息
                copy=dict()
                for name in self._named_kw_args:
                    if name in kw:
                        copy[name]=kw[name]
                kw=copy
            for k,v in request.match_info.items():#检查命名关键参数
                if k in kw:
                    logging.warning('Duplicate arg name in named arg and kw args:%s'%k)
                kw[k]=v
        if self._has_request_arg:
            kw['request']=request
        if self._required_kw_args:#假如命名关键字参数(没有附加默认值)，request没有提供相应的数值，报错
            for name in self._required_kw_args:
                if name not in kw:
                    return web.HTTPBadRequest(text='Missing argument: %s ' %name)

        logging.info('call with args: %s'%str(kw))

        try:
            r=await self._fn(**kw)
            return r
        except APIError as e:
            return dict(error=e.error,data=e.data,message=e.message)

def add_route(app,fn):
    method=getattr(fn,'__method__',None)
    path = getattr(fn,'__route__',None)
    if method is None or path is None:
        return ValueError('@get or @post not defined in %s.' %str(fn))
    if not asyncio.iscoroutinefunction(fn) and not inspect.isgeneratorfunction(fn):
        fn=asyncio.coroutine(fn)
    logging.info('add route %s %s =>%s(%s)'%(method,path,fn.__name__,','.join(inspect.signature(fn).parameters.keys())))
    app.router.add_route(method,path,RequestHandler(app,fn))

def add_routes(app,moudle_name):
    n=moudle_name.rfind('.')#从右向左查询，返回字符串首次出现的位置；如果没有匹配项则返回-1
    if n ==-1:
        #__import__() 函数用于动态加载类和函数,返回元组列表
        mod=__import__(moudle_name,globals(),locals())
    else:
        name=moudle_name[n+1:]
        mod=getattr(__import__(moudle_name[:n],globals(),locals(),[name],0),name)
    for attr in dir(mod):
        if attr.startswith('_'):
            continue
        fn = getattr(mod, attr)
        #检测是否可调用
        if callable(fn):
            method = getattr(fn, '__method__', None)
            path = getattr(fn, '__route__', None)
            if path and method:  # 这里要查询path以及method是否存在而不是等待add_route函数查询，因为那里错误就要报错了
                add_route(app, fn)

def add_static(app):
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)),'static')#输出当前文件夹中'static'的路径
    app.router.add_static('/static/',path)#prefix (str) – URL path prefix for handled static files
    logging.info('add static %s => %s'%('/static/',path))


