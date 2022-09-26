import os, sys, re, time
from datetime import datetime
import shutil
import string, random
import urllib.parse
import urllib

from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt, csrf_protect
from django.http import HttpResponse
from django.template import loader
from django.conf import settings

from hitapp.models import HitManager, Proxies, ProxyUsage

from django.http import HttpResponseRedirect
from django.contrib.auth import authenticate, login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib.auth import logout



def showlogin(request):
    if request.method != 'GET':
        return HttpResponse("Invalid method of call")
    context = {}
    template = loader.get_template('login.html')
    return HttpResponse(template.render(context, request))


@csrf_protect
def dologin(request):
    if request.method != 'POST':
        return HttpResponse("Invalid method of call")
    username, password = "", ""
    username = request.POST['uname']
    password = request.POST['psw']
    authuser = authenticate(username=username, password=password)
    if authuser is not None:
        login(request, authuser)
        return HttpResponseRedirect("/hitapp/dashboard/")
    else:
        return HttpResponseRedirect("/hitapp/login/?err=1") # err=1 - user failed auth.


def logout(request):
    logout(request)
    return HttpResponseRedirect("/hitapp/login/")


def dashboard(request):
    if request.method != 'GET':
        message = "Invalid method of call"
        return HttpResponse(message)
    if not request.user.is_authenticated:
        return HttpResponseRedirect("/hitapp/login/?err=3")
    pageno = 1
    if 'page' in request.GET.keys():
        pageno = request.GET.get('page', 1)
    try:
        pageno = int(pageno)
    except:
        pageno = 1
    blocksize = 20
    startctr = pageno * blocksize - blocksize
    endctr = startctr + blocksize
    allhitsessions = HitManager.objects.all().order_by('-starttime')[startctr:endctr]
    hitslist = []
    for hitsess in allhitsessions:
        hitdict = {}
        hitdict['targeturl'] = hitsess.targeturl
        hitdict['platform'] = hitsess.platform
        hitdict['targetcount'] = hitsess.targetcount
        hitdict['actualcount'] = hitsess.actualcount
        hitdict['starttime'] = hitsess.starttime
        hitdict['endtime'] = hitsess.endtime
        hitdict['username'] = hitsess.user.username
        hitdict['debug'] = hitsess.debugstatus
        hitdict['humanize'] = hitsess.humanizestatus
        hitdict['logging'] = hitsess.loggingstatus
        hitdict['cleanup'] = hitsess.cleanupstatus
        hitdict['forcedstop'] = hitsess.forcedstop
        if hitsess.endtime is None:
            hitdict['color'] = "color:#34eb37;"
        else:
            hitdict['color'] = "color:#1c30c7;"
        hitslist.append(hitdict)
    prevpage = pageno - 1
    if hitslist.__len__() > 0:
        nextpage = pageno + 1
    else:
        nextpage = None
    context = {'hits' : hitslist, 'showpagination' : 1, 'prevpage' : prevpage, 'nextpage' : nextpage}
    template = loader.get_template('dashboard.html')
    return HttpResponse(template.render(context, request))


def runhitbot(request):
    pass


def manageproxies(request):
    pass


def addproxies(request):
    pass


def removeproxies(request):
    pass


def editproxy(request):
    pass








