# -*- coding: utf-8 -*-
import asyncio, logging

import aiomysql

#记录sql操作
def log(sql,args=()):
    logging.info('SQL:%s'% sql)

#创建全局连接池，**kw关键字参数集
@asyncio.coroutine
def create_pool(loop,**kw):
    logging.info('create database connection pool...')
    #定义全局变量
    global __pool
    __pool =yield from aiomysql.create_pool(
        host=kw.get('host','localhost'),#默认主机ip
        port=kw.get('port',3306),
        user=kw['user'],
        password=kw['password'],
        db=kw['db'],#选择数据库
        charset=kw.get('charset', 'utf8'),#设置编码
        autocommit=kw.get('autocommit', True),#设置自动提交事务，默认打开
        maxsize=kw.get('maxsize', 10),#设置最大连接数
        minsize=kw.get('minsize', 10),#设置最小连接数
        loop=loop #需要传递一个事件循环实例，若无特别声明，默认使用asyncio.get_event_loop()
    )
#关闭连接池
@asyncio.coroutine
def destory_pool():
    global __pool
    if __pool is not None :
        __pool.close()
        yield from __pool.wait_closed()

#封装select方法
async def select(sql,args,size=None):
    log(sql,args)
    #使用全局变量
    global __pool
    #从连接池获取一个连接
    with (await __pool)as conn:
        #创建一个游标，返回由dict组成的list
        cur=await conn.cursor(aiomysql.DictCursor)
        #执行sql
        await cur.execute(sql.replace('?','%s'),args)
        if size:
            rs=await cur.fetchmany(size)#只读取size条记录
        else:
            rs=await cur.fetchall()#
        await cur.close()
        logging.info('rows returned: %s' % len(rs))
        return rs

#封装execute方法（update\insert\delete）
async def execute(sql,args):
    global __pool
    try:
        with (await __pool) as conn:
            cur=await conn.cursor()
            await cur.execute(sql.replace('?','%s'),args)
            affected=cur.rowcount  #获得影响的行数
            await cur.close()
    except BaseException as e:
        raise e
    return affected

#制作参数字符串
def create_args_string(num):
    L=[]
    for n in range(num):#SQL的占位符是？，num是多少就插入多少个占位符
        L.append('?')
    return ','.join(L) #将L拼接成字符串返回，例如num=3时："?, ?, ?"



#字段类的实现
class Field(object):
    def __init__(self,name,column_type,primary_key,default):#可传入参数对应列名、数据类型、主键、默认值
        self.name=name
        self.column_type=column_type
        self.primary_key=primary_key
        self.default=default
    def __str__(self):#返回类名、列名
        return '<%s:%s>' %(self.__class__.__name__,self.name)
#继承Field类，定义字符类
class StringField(Field):
    def __init__(self,name=None,primary_key=False,default=None,ddl='varchar(50)'):
        super().__init__(name, ddl, primary_key, default)

#继承Field类，定义boolean类
class BooleanField(Field):
	def __init__(self, name=None, default=False): #可传入参数列名、默认值
		super().__init__(name, 'boolean', False, default) #对应列名、数据类型、主键、默认值

#继承Field类，定义整数类(bigint)，默认值为0
class IntegerField(Field):
	def __init__(self, name=None, primary_key=False, default=0): #可传入参数列名、主键、默认值
		super().__init__(name, 'bigint', primary_key, default)

#继承Field类，定义浮点类
class FloatField(Field):
	def __init__(self, name=None, primary_key=False, default=0.0):
		super().__init__(name, 'real', primary_key, default)

#继承Field类，定义text类
class TextField(Field):
	def __init__(self, name=None, default=None):
		super().__init__(name, 'text', False, default)


#定义元类
class ModelMetaClass(type):
    def __new__(cls, name,bases,attrs):
        #排除model类本身
        if name=="Model":
            return type.__new__(cls,name,bases,attrs)
        #获取table名,默认和类的名字相同
        tableName=attrs.get('__table__',None) or name
        logging.info('found model: %s(table:%s)' %(name,tableName))
        #获取所有的字段，以及字段值
        mappings=dict()
        #仅用来存储非主键以外的其它字段，只存key
        fields=[]
        #仅保存主键的key
        primarykey=None
        for k,v in attrs.items():
            if isinstance(v,Field):
                mappings[k]=v
                if v.primary_key:
                    if primarykey:
                        raise RuntimeError("Douplicate primary key for field :%s" % primarykey)
                    primarykey=k
                else:
                    fields.append(k)
        #保证了必须有一个主键
        if not primarykey:
            raise RuntimeError("Primary key not found")
        for k in mappings.keys():
            attrs.pop(k)

        attrs['__mappings__']=mappings#保存属性和列的映射关系
        attrs['__table__']=tableName
        attrs['__primarykey__']=primarykey#主键属性名
        attrs['__fields__']=fields#除主键外的属性名
        #构造默认的sql语句
        attrs['__select__'] = "select %s ,%s from %s " % (primarykey, ','.join(map(lambda f: '%s' % (mappings.get(f).name or f), fields)), tableName)
        attrs['__update__'] = "update %s set %s where %s=?" % (tableName, ', '.join(map(lambda f: '`%s`=?' % (mappings.get(f).name or f), fields)), primarykey)
        attrs['__insert__'] = "insert into %s (%s,%s) values (%s);" % (tableName, primarykey, ','.join(map(lambda f: '%s' % (mappings.get(f).name or f), fields)),create_args_string(len(fields) + 1))
        attrs['__delete__'] = "delete from %s where %s= ? ;" % (tableName, primarykey)
        return type.__new__(cls, name, bases, attrs)

#定义模板类，继承dict的属性，继承元类获得属性和列的映射关系，即orm
class Model(dict,metaclass=ModelMetaClass):
    def __init__(self,**kw):
        super(Model,self).__init__(**kw)
    #__getattr__和__setattr__实现属性动态绑定和获取
    def __getattr__(self, key):
        try:
            return self[key]
        except KeyError:
            raise AttributeError(r"'Model'object has no attribute '%s'"%key)
    def __setattr__(self, key, value):
        self[key]=value
    #返回属性值，默认None
    def getValue(self,key):
        value=getattr(self,key,None)
        return value
    #返回属性值，空则返回默认值
    def getValueOrDefault(self,key):
        value=getattr(self,key,None)
        if value is None:
            #查询属性对应的列的数量类型默认值
            field=self.__mappings__[key]
            if field.default is not None:
                value=field.default() if callable(field.default) else field.default
                logging.debug('using default value for %s: %s' % (key, str(value)))
                setattr(self,key,value)
        return value

    @asyncio.coroutine
    def save(self):
        args=list(map(self.getValueOrDefault,self.__mappings__))
        yield from execute(self.__insert__,args)
    @asyncio.coroutine
    def remove(self):
        args=[]
        args.append(self[self.__primarykey__])
        print(self.__delete__)
        yield from execute(self.__delete__,args)
    @asyncio.coroutine
    def update(self,**kw):
        print("enter update")
        args=[]
        for key in kw:
            if key not in self.__fields__:
                raise RuntimeError("field not found")
        for key in self.__fields__:
            if key in kw:
                args.append(kw[key])
            else:
                args.append(getattr(self,key,None))
        args.append(getattr(self.__primarykey__))
        yield from execute(self.__update__,args)

    @classmethod  #添加类方法
    @asyncio.coroutine
    def find(cls, pk):
        rs = yield from select('%s where `%s`=?' % (cls.__select__, cls.__primarykey__), [pk], 1)
        if len(rs) == 0:
            return None
        return cls(**rs[0])  # 将dict作为关键字参数传入当前类的对象

    @classmethod
    @asyncio.coroutine
    def findAll(cls, where=None, args=None,**kw):
        sql = [cls.__select__]#用列表存储sql语句
        if where:
            sql.append('where')
            sql.append(where)
        if args is None:
            args = []
        rs = yield from select(' '.join(sql), args)
        return [cls(**r) for r in rs]

    @classmethod
    @asyncio.coroutine
    def findnumber(cls,selectField,where=None,args=None):
        sql=['select %s _num_ from %s' %(selectField,cls.__table__)]
        if where:
            sql.append('where')
            sql.append(where)
        rs= yield from select(''.join(sql),args,1)
        if len(rs)==0:
            return None
        return rs[0]['_num_']



