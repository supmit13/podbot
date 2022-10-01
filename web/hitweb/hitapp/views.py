import os, sys, re, time
from datetime import datetime
import shutil
import string, random
import urllib.parse
import urllib
import base64

from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt, csrf_protect
from django.http import HttpResponse
from django.template import loader
from django.conf import settings

from hitapp.models import HitManager, Proxies, ProxyUsage, APIKeys
from hitapp.tasks import hitbot_webrun, hitbot_webstop, hitbot_webstatus

from django.http import HttpResponseRedirect
from django.contrib.auth import authenticate, login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib.auth import logout


def adduser(request):
    if not request.user.is_authenticated: # You need to be logged in to create a new user.
        return HttpResponseRedirect("/hitapp/login/?err=3")
    if request.method == 'GET':
        context = {}
        template = loader.get_template('adduser.html')
        return HttpResponse(template.render(context, request))
    elif request.method == 'POST':
        firstname, lastname, username, emailid, password = "", "", "", "", ""
        firstname = request.POST.get('firstname', '')
        lastname = request.POST.get('lastname', '')
        username = request.POST.get('username', '')
        emailid = request.POST.get('email', '')
        password = request.POST.get('psw', '')
        newuser = User()
        newuser.first_name = firstname
        newuser.last_name = lastname
        newuser.username = username
        newuser.email = emailid
        newuser.set_password(password)
        newuser.is_active = True
        newuser.date_joined = datetime.now()
        newuser.is_staff = False
        newuser.is_superuser = False
        try:
            newuser.save()
            msg = "Successfully added user"
        except:
            msg = "Failed to add user: %s"%sys.exc_info()[1].__str__()
        return HttpResponse(msg)
    else:
        msg = "Invalid method of call"
        return HttpResponse(msg)


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


def on_raw_message(content):
    print(content) 


def runhitbot(request):
    if not request.user.is_authenticated:
        return HttpResponseRedirect("/hitapp/login/?err=3")
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
        proxies = []
        targeturl, amazontargethits, spotifytargethits, appletargethits, amazonapikey, spotifyclientid, spotifyclientsecret = "", -1, -1, -1, "", "", ""
        amazononly, spotifyonly, appleonly = False, False, False
        # First thing, get all param values
        if 'targeturl' in request.POST.keys():
            targeturl = request.POST['targeturl']
        if 'amazontargethits' in request.POST.keys():
            amazontargethits = request.POST['amazontargethits']
        if 'spotifytargethits' in request.POST.keys():
            spotifytargethits = request.POST['spotifytargethits']
        if 'appletargethits' in request.POST.keys():
            appletargethits = request.POST['appletargethits']
        if 'AMAZON_APIKEY' in request.POST.keys():
            amazonapikey = request.POST['AMAZON_APIKEY']
        if 'SPOTIFY_CLIENTID' in request.POST.keys():
            spotifyclientid = request.POST['SPOTIFY_CLIENTID']
        if 'SPOTIFY_CLIENTSECRET' in request.POST.keys():
            spotifyclientsecret = request.POST['SPOTIFY_CLIENTSECRET']
        try:
            amazontargethits = int(amazontargethits)
        except:
            msg = "Could not interpret Amazon target hits value as integer"
            return HttpResponse(msg)
        try:
            spotifytargethits = int(spotifytargethits)
        except:
            msg = "Could not interpret Spotify target hits value as integer"
            return HttpResponse(msg)
        try:
            appletargethits = int(appletargethits)
        except:
            msg = "Could not interpret Apple target hits value as integer"
            return HttpResponse(msg)
        if 'amazononly' in request.POST.keys() and int(request.POST['amazononly']) == 1:
            amazononly = True
            spotifyonly = False
            appleonly = False
        if 'spotifyonly' in request.POST.keys() and int(request.POST['spotifyonly']) == 1:
            amazononly = False
            spotifyonly = True
            appleonly = False
        if 'appleonly' in request.POST.keys() and int(request.POST['appleonly']) == 1:
            amazononly = False
            spotifyonly = False
            appleonly = True
        if 'selproxies' in request.POST.keys():
            proxiesbase64 = request.POST['selproxies']
            proxiesstr = base64.b64decode(proxiesbase64)
            proxies = str(proxiesstr).split("##")
        # Add HitManager objects - logic: If buzzsprout url is given, add 3 HitManager objects, one each for amazon, spotify and apple.
        # If amazononly or spotifyonly or appleonly is true, add one HitManager object for the relevant platform.
        errmsg = ""
        tstr = str(int(time.time() * 1000)) + ".status"
        hitbotstatusdir = os.getcwd() + os.path.sep + "hitstatus"
        if not os.path.exists(hitbotstatusdir) or not os.path.isdir(hitbotstatusdir):
            os.makedirs(hitbotstatusdir, 0o777)
        statusfile = hitbotstatusdir + os.path.sep + tstr
        if not amazononly and not spotifyonly and not appleonly:
            hmobjamz = HitManager()
            hmobjspt = HitManager()
            hmobjapl = HitManager()
            hmobjamz.platform = "Amazon"
            hmobjspt.platform = "Spotify"
            hmobjapl.platform = "Apple"
            hmobjamz.targeturl = hmobjspt.targeturl = hmobjapl.targeturl = targeturl
            hmobjamz.targetcount = amazontargethits
            hmobjspt.targetcount = spotifytargethits
            hmobjapl.targetcount = appletargethits
            nowtime = datetime.now()
            hmobjamz.starttime = hmobjspt.starttime = hmobjapl.starttime = nowtime
            hmobjamz.user = hmobjspt.user = hmobjapl.user = request.user
            hmobjamz.debugstatus = hmobjspt.debugstatus = hmobjapl.debugstatus = True
            hmobjamz.humanizestatus = hmobjspt.humanizestatus = hmobjapl.humanizestatus = False
            hmobjamz.loggingstatus = hmobjspt.loggingstatus = hmobjapl.loggingstatus = True
            hmobjamz.cleanupstatus = hmobjspt.cleanupstatus = hmobjapl.cleanupstatus = False
            try:
                hmobjamz.save()
                hmobjspt.save()
                hmobjapl.save()
                amzlastid, sptlastid, apllastid = -1, -1, -1
                amzlastid = hmobjamz.id
                sptlastid = hmobjspt.id
                apllastid = hmobjapl.id
                amzprxusage = ProxyUsage()
                sptprxusage = ProxyUsage()
                aplprxusage = ProxyUsage()
                amzprxusage.hit = hmobjamz
                sptprxusage.hit = hmobjspt
                aplprxusage.hit = hmobjapl
                amzprxusage.proxy = ",".join(proxies)
                sptprxusage.proxy = ",".join(proxies)
                aplprxusage.proxy = ",".join(proxies)
                amzprxusage.save()
                sptprxusage.save()
                aplprxusage.save()
                idlist = [amzlastid, sptlastid, apllastid]
                # pass all params to the hitbot_webdriver call
                r = hitbot_webrun.apply_async(args=[proxies, targeturl, amazontargethits, spotifytargethits, appletargethits, amazononly, spotifyonly, appleonly, amazonapikey, spotifyclientid, spotifyclientsecret, idlist, statusfile])
                errmsg = "Started hit bot successfully and saved run info in DB"
                #r.get(on_message=on_raw_message, propagate=False)
            except:
                errmsg = "Error - could not run bot: %s"%sys.exc_info()[1].__str__()
            return HttpResponse(str(statusfile))
        elif amazononly is True:
            hmobj = HitManager()
            hmobj.platform = "Amazon"
            hmobj.targetcount = amazontargethits
        elif spotifyonly is True:
            hmobj = HitManager()
            hmobj.platform = "Spotify"
            hmobj.targetcount = spotifytargethits
        elif appleonly is True:
            hmobj = HitManager()
            hmobj.platform = "Apple"
            hmobj.targetcount = appletargethits
        else:
            errmsg = "Unhandled Platform"
        hmobj.targeturl = targeturl
        nowtime = datetime.now()
        hmobj.starttime = nowtime
        hmobj.debugstatus = True
        hmobj.humanizestatus = False
        hmobj.loggingstatus = True
        hmobj.cleanupstatus = False
        hmobj.user = request.user
        try:
            hmobj.save()
            amzlastid, sptlastid, apllastid = -1, -1, -1
            if hmobj.platform == "Amazon":
                amzlastid = hmobj.id
            if hmobj.platform == "Spotify":
                sptlastid = hmobj.id
            if hmobj.platform == "Apple":
                apllastid = hmobj.id
            prxusage = ProxyUsage()
            prxusage.hit = hmobj
            prxusage.proxy = ",".join(proxies)
            prxusage.save()
            idlist = [amzlastid, sptlastid, apllastid]
            # pass all params to the hitbot_webdriver call
            r = hitbot_webrun.apply_async(args=[proxies, targeturl, amazontargethits, spotifytargethits, appletargethits, amazononly, spotifyonly, appleonly, amazonapikey, spotifyclientid, spotifyclientsecret, idlist, statusfile])
            errmsg = "Started hit bot successfully and saved run info in DB"
        except:
            errmsg = "Error - could not save run information in DB: %s"%sys.exc_info()[1].__str__()
        return HttpResponse(str(statusfile))



def stophitbot(request):
    if not request.user.is_authenticated:
        return HttpResponseRedirect("/hitapp/login/?err=3")
    hitbot_webstop.apply_async()


def runstatus(request):
    if not request.user.is_authenticated:
        return HttpResponseRedirect("/hitapp/login/?err=3")
    hitbot_webstatus.apply_async()


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
    if not request.user.is_authenticated:
        return HttpResponseRedirect("/hitapp/login/?err=3")
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
    if not request.user.is_authenticated:
        return HttpResponseRedirect("/hitapp/login/?err=3")
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
    if not request.user.is_authenticated:
        return HttpResponseRedirect("/hitapp/login/?err=3")
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
    if not request.user.is_authenticated:
        return HttpResponseRedirect("/hitapp/login/?err=3")
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
    if not request.user.is_authenticated:
        return HttpResponseRedirect("/hitapp/login/?err=3")
    if request.method == 'GET':
        allkeys = APIKeys.objects.filter(deleted=False)
        if allkeys is None or allkeys.__len__() == 0:
            msg = "Please add some keys in the DB"
            context = {'errmsg' : msg}
            template = loader.get_template('managekeys.html')
            return HttpResponse(template.render(context, request))
        keysdict = {}
        for apikey in allkeys:
            keytag = apikey.keytag
            keyvalue = apikey.keyvalue
            keysdict[keytag] = keyvalue
        context = {'apikeys' : keysdict}
        template = loader.get_template('managekeys.html')
        return HttpResponse(template.render(context, request))
    elif request.method == 'POST':
        keysdict = {}
        errmsglist = []
        for i in range(1, 4):
            tagname = request.POST.get('keytag_%s'%i)
            keyvalue = request.POST.get('keyval_%s'%i)
            try:
                keyobj = APIKeys.objects.get(keytag=tagname, deleted=False)
                keyobj.keyvalue = keyvalue
                keyobj.save()
            except:
                msg = "Error trying to find key identified by tag: %s"%tagname
                errmsglist.append(msg)
        msg = "Completed operation with %s errors<br />"%(errmsglist.__len__())
        for err in errmsglist:
            msg += err + "<br />"
        return HttpResponse(msg)





