# -*- coding: utf-8 -*-
import orm,asyncio
from models import User,Blog,Comment
from config import config
import time

async def test(loop):
    await orm.create_pool(loop,**config['db'])


    b1 = Blog(user_id='1',user_name='sunmeng',user_image='test',name='Test',summary='Testconn',content='Test',created_at=time.time()-120)
    b2 = Blog(user_id='2', user_name='wuyanzu', user_image='wuyanzu', name='wuyanzu', summary='wuyanzu', content='wuyanzu',created_at=time.time() -3600)
    b3 = Blog(user_id='3', user_name='liuyifei', user_image='liuyifei', name='liuyifei', summary='liuyifei', content='liuyifei', created_at=time.time() )
    await  b1.save()
    await  b2.save()
    await  b3.save()
    await orm.destory_pool()
#获取EventLoop
loop = asyncio.get_event_loop()
#把协程丢到Eventloop中执行.
loop.run_until_complete(test(loop))
#关闭EventLoop
loop.close()
