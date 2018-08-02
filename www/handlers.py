# -*- coding: utf-8 -*-
import asyncio
from coroweb import get,post
from models import User,Blog,next_id
from API import *
from aiohttp import web
from config import configs
import time,re,hashlib,logging
import json

#编写用于测试的URL处理函数
@get('/test')
async def handler_url_blog(request):
    body='<h1>Awesome</h1>'
    return body
@get('/greeting')
async def handler_url_greeting(*,name,request):
    body='<h1>Awesome: /greeting %s</h1>'%name
    return body

@get('/')
async def index(request):
    summary = 'Hello,World.'
    blogs = await Blog.findAll()
    return {
        '__template__': 'blogs.html',
        'blogs': blogs,
        'user': request.__user__,
    }
#显示注册页面
@get('/register')
async def register():
    return {'__template__':'register.html'}

COOKIE_NAME = 'awesession'#用来在set_cookie中命名
_COOKIE_KEY = configs.session.secret #导入默认设置

#制作cookie的数值，即set_cookie的value
def user2cookie(user, max_age):
    # build cookie string by: id-expires-sha1（id-到期时间-摘要算法）
    expires = str(time.time()+max_age)
    s = '%s-%s-%s-%s'%(user.id, user.passwd, expires, _COOKIE_KEY)#s的组成：id, passwd, expires, _COOKIE_KEY
    L = [user.id, expires, hashlib.sha1(s.encode('utf-8')).hexdigest()]#再把s进行摘要算法
    return '-'.join(L)


#正则表达式我是参考这里的(http://www.cnblogs.com/vs-bug/archive/2010/03/26/1696752.html)
_RE_EMAIL = re.compile(r'^(\w)+(\.\w)*\@(\w)+((\.\w{2,3}){1,3})$')
_RE_PASSWD = re.compile(r'^[\w\.]{40}')#对老师这里的密码正则表达式也做了点修改

@post('/api/users')
async def api_register_users(*,name,email,passwd):
    if not name or not name.strip():
        raise APIValueError('name')
    if not email or not _RE_EMAIL.match(email):
        raise APIValueError('email')
    if not passwd and not _RE_PASSWD.match(passwd):
        raise APIValueError('passwd')
    users=await User.findAll(where='email=?',args=[email])
    if len(users)>0:
        raise APIError('register:failed','email','Email is already in use.')
    #将注册信息保存到数据库
    uid=next_id()
    sha1_passwd='%s:%s'%(uid,passwd)
    user=User(id=uid,name=name.strip(),email=email,passwd=hashlib.sha1(sha1_passwd.encode('utf-8')).hexdigest(), image='http://www.gravatar.com/avatar/%s?d=mm&s=120' % hashlib.md5(email.encode('utf-8')).hexdigest())
    await user.save()
    #制作cookie返回浏览器客户端
    r=web.Response()
    r.set_cookie(COOKIE_NAME,user2cookie(user,86400),max_age=86400,httponly=True)
    user.passwd='*******'
    r.content_type='application/json'
    r.body=json.dumps(user,ensure_ascii=False).encode('utf-8')
    return r

@get('/signin')
def signin():
    return {'__template__':'signin.html'}

@get('/signout')
def signout(request):
    referer = request.headers.get('Referer')
    r = web.HTTPFound(referer or '/')
    r.set_cookie(COOKIE_NAME, '-deleted-', max_age=0, httponly=True)
    logging.info('user signed out.')
    return r

@post('/api/authenticate')
async def authenticate(*,email,passwd):
    if not email:
        raise APIValueError('email')
    if not passwd:
        raise APIValueError('passwd')
    users = await User.findAll(where='email=?',args=[email])
    if len(users) == 0:
        raise APIValueError('email','Email not exist.')
    user= users[0]
    #把登录密码转化格式并进行摘要算法
    sha1=hashlib.sha1()
    sha1.update(user.id.encode('utf-8'))
    sha1.update(b':')
    sha1.update(passwd.encode('utf-8'))
    if sha1.hexdigest()!=user.passwd:
        raise APIValueError('password','Invaild password')
    # 制作cookie发送给浏览器，这步骤与注册用户一样
    r=web.Response()
    r.set_cookie(COOKIE_NAME, user2cookie(user, 86400), max_age=86400, httponly=True)
    user.passwd = '*******'
    r.content_type = 'application/json'
    r.body = json.dumps(user, ensure_ascii=False).encode('utf-8')
    return r

#解释cookie
async def cookie2user(cookie_str):
    if not cookie_str:
        return None
    try:
        L=cookie_str.split('-')
        if len(L)!=3:
            return None
        uid,expires,sha1=L
        if float(expires)<time.time():
            return None
        user=await User.find(uid)
        if not user:
            return None
        s = '%s-%s-%s-%s' % (uid, user.passwd, expires, _COOKIE_KEY)
        if sha1 != hashlib.sha1(s.encode('utf-8')).hexdigest():
            logging.info('invalid sha1')
            return None
        user.passwd = "******"
        return user
    except Exception as e:
        logging.exception(e)
        return None



def check_admin(request):
    if request.__user__ is None or  request.__user__.admin !=1:
        raise APIPermissionError()

@post('/api/blogs')
async def api_create_blogs(request,*,name,summary,content):
    print(request.__user__.admin)
    check_admin(request)
    if not name or not name.strip():
        raise APIValueError('name', 'name can not empty.')
    if not summary or not summary.strip():
        raise APIValueError('summary', 'summary can not empty.')
    if not content or not content.strip():
        raise APIValueError('content', 'content can not empty.')
    blog = Blog(user_id=request.__user__.id, user_name=request.__user__.name, user_image=request.__user__.image,
                    summary=summary.strip(), name=name.strip(), content=content.strip())
    await blog.save()
    return blog

@get('/manage/blogs/create')
def manage_create_blog(request):
    return {
        '__template__': 'manage_blog_edit.html',
        'id': '',
        'action':'/api/blogs',
        'user':request.__user__
    }

#用于选择当前页面
def get_page_index(page_str):
    p = 1  #初始化页数取整
    try:
        p = int(page_str)
    except ValueError as e:
        pass
    if p < 1:
        p = 1
    return p

@get('/api/blogs')
async def api_blogs(*,page='1'):
    page_index=get_page_index(page)
    num=await Blog.findnumber('count(id)')#查询日志总数
    p=Page(num,page_index)
    if num==0:#数据库没日志
        return dict(page=p,blogs=())
    blogs=await Blog.findAll(orderBy='create_at desc',limit=(p.offset,p.limit))
    return dict(page=p,blogs=blogs)#返回管理页面信息，及显示总数

@get('/manage/blogs')
def manage_blogs(*, page='1'):
    return {
        '__template__': 'manage_blogs.html',
        'page_index': get_page_index(page)
    }
