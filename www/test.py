# -*- coding: utf-8 -*-
class Base(object):

    def __init__(self):
        print ('Base create')
class childA(Base):

    def __init__(self):
        print ('creat A '),

        Base.__init__(self)
class childB(Base):

    def __init__(self):
        print('creat B '),

        super(childB, self).__init__()


base = Base()

a = childA()

b = childB()
