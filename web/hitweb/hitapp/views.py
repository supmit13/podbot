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

from hitapp.models import HitManager, Proxies, ProxyUsage, APIKeys

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
    if request.method == 'GET':
        context = {'color' : "color:#1c30c7;"}
        proxyqset = Proxies.objects.filter(deleted=False)
        proxiesdict = {}
        for prx in proxyqset:
            prxurl = prx.proxyurl
            prxprovider = prx.provider
            proxiesdict[prxurl] = prxprovider
        context['proxies'] = proxiesdict
        apikeys = APIKeys.objects.filter(deleted=False)
        keysdict = {}
        for apikey in apikeys:
            keytag = apikey.keytag
            keyvalue = apikey.keyvalue
            keyname = apikey.keyname
            keysdict[keytag] = [keyvalue, keyname]
        context['apikeys'] = keysdict
        template = loader.get_template('runbot.html')
        return HttpResponse(template.render(context, request))
    elif request.method == 'POST':
        pass


def manageproxies(request):
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
    proxiesdict = {}
    proxiesqs = Proxies.objects.filter(deleted=False)[startctr:endctr]
    for proxy in proxiesqs:
        proxyurl = proxy.proxyurl
        proxyprovider = proxy.provider
        proxytype = proxy.proxytype
        color = "color:#34eb37;"
        proxiesdict[proxyurl] = [proxyprovider, proxytype, color]
    prevpage = pageno - 1
    prxlist = list(proxiesdict.keys())
    if prxlist.__len__() > 0:
        nextpage = pageno + 1
    else:
        nextpage = None
    context = {'proxies' : proxiesdict, 'showpagination' : 1, 'prevpage' : prevpage, 'nextpage' : nextpage}
    template = loader.get_template('listproxies.html')
    return HttpResponse(template.render(context, request))


def addproxies(request):
    if request.method == 'GET':
        context = {'operation' : 'Add'}
        template = loader.get_template('addeditproxy.html')
        return HttpResponse(template.render(context, request))
    elif request.method == 'POST':
        proxyip = request.POST.get('proxyip', '')
        proxyport = request.POST.get('proxyport', '')
        proxytype = request.POST.get('proxytype', '')
        proxyprovider = request.POST.get('proxyprovider', '')
        operation = request.POST.get('operation', '')
        if operation == "Edit":
            saveproxy(request)
        else:
            proxyurl = proxytype + "://" + proxyip + ":" + proxyport
            proxyobj = Proxies()
            proxyobj.proxyip = proxyip
            proxyobj.proxyport = proxyport
            proxyobj.proxytype = proxytype
            proxyobj.provider = proxyprovider
            proxyobj.proxyurl = proxyurl
            proxyobj.addedon = datetime.now()
            try:
                proxyobj.save()
            except:
                msg = "Error saving proxy details: %s"%sys.exc_info()[1].__str__()
                return HttpResponse(msg)
            msg = "Successfully added proxy"
            return HttpResponse(msg)


def deleteproxy(request):
    if request.method != 'POST':
        msg = "Invalid method of call"
        return HttpResponse(msg)
    proxyurl = request.POST.get('proxyurl', '')
    proxyqset = Proxies.objects.filter(proxyurl=proxyurl).order_by('-addedon') # Getting the latest.
    if proxyqset.__len__() == 0:
        errmsg = 'Proxy with the given URL could not be found'
        return HttpResponse(errmsg)
    proxyobj = proxyqset[0]
    proxyobj.deleted = True
    proxyobj.removedon = datetime.now()
    try:
        proxyobj.save()
    except:
        msg = "Could not delete proxy: %s"%sys.exc_info()[1].__str__()
        return HttpResponse(msg)
    msg = "Successfully deleted proxy. Refresh the page to view the list now."
    return HttpResponse(msg)


def editproxies(request):
    if request.method != 'POST':
        msg = "Invalid method of call"
        return HttpResponse(msg)
    proxyurl = request.POST.get('proxyurl', '')
    proxyqset = Proxies.objects.filter(proxyurl=proxyurl, deleted=False).order_by('-addedon') # Getting the latest.
    if proxyqset.__len__() == 0:
        context = {'errmsg' : 'Proxy with the given URL could not be found'}
        template = loader.get_template('addeditproxy.html')
        return HttpResponse(template.render(context, request))
    proxyip = proxyqset[0].proxyip
    proxyport = proxyqset[0].proxyport
    proxytype = proxyqset[0].proxytype
    proxyprovider = proxyqset[0].provider
    context = {'proxyip' : proxyip, 'proxyport' : proxyport, 'proxytype' : proxytype, 'proxyprovider' : proxyprovider, 'proxyurl' : proxyurl, 'operation' : 'Edit', 'currentproxyurl' : proxyurl}
    template = loader.get_template('addeditproxy.html')
    return HttpResponse(template.render(context, request))


def saveproxy(request):
    if request.method != 'POST':
        msg = "Invalid method of call"
        return HttpResponse(msg)
    proxyip = request.POST.get('proxyip', '')
    proxyport = request.POST.get('proxyport', '')
    proxytype = request.POST.get('proxytype', '')
    proxyprovider = request.POST.get('proxyprovider', '')
    operation = request.POST.get('operation', '')
    currentproxyurl = request.POST.get('currentproxyurl', '')
    if operation == "Add":
        addproxies(request)
    else:
        proxyurl = proxytype + "://" + proxyip + ":" + proxyport
        proxyqset = Proxies.objects.filter(proxyurl=currentproxyurl, deleted=False).order_by('-addedon')
        if proxyqset.__len__() == 0:
            addproxies(request)
        else:
            proxyobj = proxyqset[0]
            proxyobj.proxyip = proxyip
            proxyobj.proxyport = proxyport
            proxyobj.proxytype = proxytype
            proxyobj.provider = proxyprovider
            proxyobj.proxyurl = proxyurl
            try:
                proxyobj.save()
            except:
                msg = "Error saving proxy details: %s"%sys.exc_info()[1].__str__()
                return HttpResponse(msg)
            msg = "Saved proxy details"
            return HttpResponse(msg)


def managekeys(request):
    if request.method == 'GET':
        allkeys = APIKeys.objects.filter(deleted=False)
        if allkeys is None or allkeys.__len__() == 0:
            msg = "Please add some keys in the DB"
            context = {'errmsg' : msg}
            template = loader.get_template('managekeys.html')
            return HttpResponse(template.render(context, request))
        keysdict = {}
        for apikey in allkeys:
            keyname = apikey.keyname
            keyvalue = apikey.keyvalue
            keysdict[keyname] = keyvalue
        context = {'apikeys' : keysdict}
        template = loader.get_template('managekeys.html')
        return HttpResponse(template.render(context, request))
    elif request.method == 'POST':
        pass





