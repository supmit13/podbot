import os, sys
import pymysql
from .celery import app as celery_app
sys.path.append(os.getcwd() + os.path.sep + '..' + os.path.sep + '..')

pymysql.install_as_MySQLdb()
__all__ = ("celery_app",)


