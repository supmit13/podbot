import os, sys, re, time
import datetime
import shutil

import simplejson as json
import pymysql as MySQLdb
import gzip
import io

import subprocess
from threading import Thread

from celery import shared_task

from hitbot2 import *

class WebUI(object):
    def __init__(self):
        self.emptystringpattern = re.compile("^\s*$")
        self.httppattern = re.compile("^https?", re.IGNORECASE)
        self.amazonkey = ""
        self.spotifyclientid = ""
        self.spotifyclientsecret = ""
        self.targeturl = ""
        # Default target hits for each platform - a value of -1 means loop infinitely (or at least as long as no one presses ctrl+c)
        self.targetamazonhits = -1
        self.targetspotifyhits = -1
        self.targetapplehits = -1
        # Playlist mode flags for each platform
        self.amazononly = False
        self.spotifyonly = False
        self.appleonly = False
        # Available options for bot
        self.DEBUG = False
        self.humanize = False
        self.logging = True
        self.cleanupmedia = True
        # Operational objects
        self.buzz = None
        self.threadslist = []
        self.rt = None
        self.proxieslist = []
        self.errmsg = ""
        

    def startbot(self, targeturl, amazonapikey, spotifyclientid, spotifyclientsecret, proxieslist, targetamazonhits, targetspotifyhits, targetapplehits, amazononly, spotifyonly, appleonly, idlist, debug=False, humanize=False, logging=True, cleanup=True, statusfile=None):
        self.targeturl = targeturl
        if self.targeturl == "":
            self.errmsg = "Target URL cannot be empty"
            return False
        eps = re.search(self.emptystringpattern, self.targeturl)
        if eps:
            self.errmsg = "Target URL is not valid"
            return False
        hps = re.search(self.httppattern, self.targeturl)
        if not hps:
            self.errmsg = "Target URL is not valid"
            return False
        self.amazonkey = amazonapikey
        self.spotifyclientid = spotifyclientid
        self.spotifyclientsecret = spotifyclientsecret
        if self.amazonkey == "":
            self.errmsg = "<br />Could not find Amazon API Key"
        if self.spotifyclientid == "":
            self.errmsg = "<br />Could not find Spotify Client ID"
        if self.spotifyclientsecret == "":
            self.errmsg = "<br />Could not find Spotify Client Secret"
        if self.errmsg != "":
            return False
        self.proxieslist = []
        self.proxypattern = re.compile("^https\:\/\/\d+\.\d+\.\d+\.\d+\:\d+", re.IGNORECASE)
        for proxline in proxieslist:
            if not re.search(self.proxypattern, proxline):
                continue
            self.proxieslist.append(proxline)
        self.targetamazonhits = targetamazonhits
        self.targetspotifyhits = targetspotifyhits
        self.targetapplehits = targetapplehits

        if int(amazononly) == 1 or amazononly == True:
            self.amazononly = True
        if int(spotifyonly) == 1 or spotifyonly == True:
            self.spotifyonly = True
        if int(appleonly) == 1 or appleonly == True:
            self.appleonly = True
        
        self.DEBUG = debug
        self.humanize = humanize
        self.logging = logging
        self.cleanupmedia = cleanup
        if self.DEBUG:
            print("%s ___ %s ____ %s"%(self.DEBUG, self.humanize, self.logging))
        # Start bot in a background thread...
        self.rt = Thread(target=self.runbot, args=(self.targeturl, idlist, self.targetamazonhits, self.targetspotifyhits, self.targetapplehits, statusfile))
        self.rt.daemon = True
        self.rt.start()
        
        self.errmsg = "<p style='color:#00AA00;'>Operation in progress...\nAPPLE: 0\nAMAZON: 0\nSPOTIFY: 0</p>"
        # ... and return to user
        return True


    """
    A target count of -1 means the bot should run indefinitely hitting all targets until it is stopped
    (possibly by killing the process).
    """
    def runbot(self, targeturl, idlist, amazonsettarget=-1, spotifysettarget=-1, applesettarget=-1, statusfile=None):
        self.buzz = BuzzBot(targeturl, self.amazonkey, self.spotifyclientid, self.spotifyclientsecret, self, self.proxieslist, False)
        self.buzz.DEBUG = self.DEBUG
        self.buzz.humanize = self.humanize
        self.buzz.logging = self.logging
        self.buzz.cleanupmedia = self.cleanupmedia
        self.buzz.settargetcounts(amazonsettarget, spotifysettarget, applesettarget)
        if self.amazononly == True:
            self.buzz.platformonly = "amazon"
        elif self.spotifyonly == True:
            self.buzz.platformonly = "spotify"
        elif self.appleonly == True:
            self.buzz.platformonly = "apple"
        else:
            pass
        if self.amazononly == False and self.spotifyonly == False and self.appleonly == False:
            self.buzz.makerequest()
            self.buzz.gethttpresponsecontent()
            urlsdict = self.buzz.getpodcasturls()
        else:
            urlsdict = {self.buzz.platformonly : targeturl}
        self.threadslist = []
        for sitename in urlsdict.keys():
            siteurl = urlsdict[sitename]
            targetcount = -1
            dbid = -1
            if sitename.lower() == "apple":
                targetcount = self.buzz.applesettarget
                if self.amazononly == True or self.spotifyonly == True:
                    targetcount = 0
                dbid = idlist[2]
            if sitename.lower() == "amazon":
                targetcount = self.buzz.amazonsettarget
                if self.appleonly == True or self.spotifyonly == True:
                    targetcount = 0
                dbid = idlist[0]
            if sitename.lower() == "spotify":
                targetcount = self.buzz.spotifysettarget
                if self.appleonly == True or self.amazononly == True:
                    targetcount = 0
                dbid = idlist[1]
            # If targetcount is 0, then there is no reason to start a thread
            if targetcount == 0:
                continue
            t = Thread(target=self.buzz.hitpodcast, args=(siteurl, sitename, targetcount, dbid, statusfile, False))
            t.daemon = True
            t.start()
            self.threadslist.append(t)
        time.sleep(2) # sleep 2 seconds.
        for tj in self.threadslist:
            tj.join()
        rmcmd = "rm -f %s"%statusfile
        x = subprocess.Popen(rmcmd, shell=True, stdin=PIPE, stdout=PIPE, stderr=STDOUT, close_fds=True)
        #statusremovemessage = x.stdout.read()
        # Done. The statusfile should be gone now.
        curmessagecontent = ""
        curmessagecontent += "\n\nFinished hitting targets."
        self.errmsg = curmessagecontent
        return True


    def closebot(self):
        try:
            self.buzz.quitflag = True
        except:
            print("No object called 'buzz'")
        if self.rt is not None:
            self.rt.join()
        # Write this message in history
        curmessagecontent = "Stopping bot - user pressed stop button"
        print(curmessagecontent)
        if self.buzz is not None and self.buzz.logger is not None:
            self.buzz.logger.close()
        sys.exit()


    def stopbot(self):
        """
        if os.name == 'posix':
            signal.SIGINT # On linux or macOSX
        else:
            signal.CTRL_C_EVENT # On windows family
        """
        self.closebot()


@shared_task
def hitbot_webrun(proxies, targeturl, amazontargethits, spotifytargethits, appletargethits, amazononly, spotifyonly, appleonly, amazonapikey, spotifyclientid, spotifyclientsecret, idlist, statusfile):
    botui = WebUI()
    botui.startbot(targeturl, amazonapikey, spotifyclientid, spotifyclientsecret, proxies, amazontargethits, spotifytargethits, appletargethits, amazononly, spotifyonly, appleonly, idlist, True, False, True, False, statusfile)


@shared_task
def hitbot_webstop():
    pass



