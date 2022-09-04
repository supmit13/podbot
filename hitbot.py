import os, sys, re, time
from datetime import datetime
import random
import shutil

import subprocess
from multiprocessing import Process, Pool, Queue
from threading import Thread

import socks
import socket
import ssl
import urllib, requests
from urllib.parse import urlencode, quote_plus, urlparse
from requests_html import HTMLSession

import simplejson as json
from bs4 import BeautifulSoup
import numpy as np
import gzip
import io
import hashlib, base64
import weakref

# Amazon APIs
import boto3
from listennotes import podcast_api

# Spotify APIs
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
from spotipy.oauth2 import SpotifyOAuth

# Apple Podcasts library
import podsearch

# Tkinter library for GUI
from tkinter import *
from tkinter.scrolledtext import ScrolledText
from tkinter import ttk

# TODO:
"""
1. Display current hit counts in status message section of the GUI.
"""

# Module level globals: These variables represent the number of hits made on the service platforms at any instant during a run.
AMAZON_HIT_STAT = 0
APPLE_HIT_STAT = 0
SPOTIFY_HIT_STAT = 0


def _decodeGzippedContent(encoded_content):
    response_stream = io.BytesIO(encoded_content)
    decoded_content = ""
    try:
        gzipper = gzip.GzipFile(fileobj=response_stream)
        decoded_content = gzipper.read()
    except: # Maybe this isn't gzipped content after all....
        decoded_content = encoded_content
    decoded_content = decoded_content.decode('utf-8')
    return(decoded_content)


def makeregex(targetstr):
    spacepattern = re.compile("\s+")
    targetpattern = targetstr.replace("\\", "\\\\")
    targetpattern = re.sub(spacepattern, "\s+", targetpattern)
    targetpattern = targetpattern.replace("(", "\(").replace(")", "\)")
    targetpattern = targetpattern.replace("-", "\-").replace(".", "\.").replace(":", "\:")
    targetpattern = targetpattern.replace("/", "\/").replace('"', '\"')
    targetpattern = targetpattern.replace("[", "\[").replace("]", "\]")
    #print(targetpattern)
    targetregex = re.compile(targetpattern, re.DOTALL|re.IGNORECASE)
    return targetregex

"""
Generate a random integer between 0 and 10 (or whatever t is). 
This will be used as a interval (in seconds) between 2 successive requests.
"""
def getrandominterval(t=10):
    return random.randint(0, t)


def createrequestcontext():
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


# Redirects handler, in case we need to handle HTTP redirects.
class NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def http_error_302(self, req, fp, code, msg, headers):
        infourl = urllib.response.addinfourl(fp, headers, req.get_full_url())
        infourl.status = code
        infourl.code = code
        return infourl

    http_error_300 = http_error_302
    http_error_301 = http_error_302
    http_error_303 = http_error_302
    http_error_307 = http_error_302


class AmazonBot(object):
    
    def __init__(self, apikey, proxies):
        self.DEBUG = False
        self.humanize = True
        self.logging = True
        self.apikey = apikey
        self.proxies = proxies
        self.response = None # This would a response object from Amazon API
        self.content = None # This could be a text chunk or a binary data (like a Podcast content)
        self.podclient = podcast_api.Client(api_key=self.apikey)
        self.results = []
        # HTTP(S) request/response and parameters
        self.httprequest = None
        self.httpresponse = None
        self.httpcontent = None
        try:
            self.proxyip, self.proxyport = self.proxies['https'][0].split(":")
        except:
            self.proxyip, self.proxyport = "", ""
        try:
            self.context = createrequestcontext()
            #if self.proxyip != "":
            #    socks.set_default_proxy(socks.SOCKS5, self.proxyip, int(self.proxyport))
            #    socket.socket = socks.socksocket
            self.httpshandler = urllib.request.HTTPSHandler(context=self.context)
            self.proxyhandler = urllib.request.ProxyHandler({'https': self.proxies['https'][0],})
            self.httpopener = urllib.request.build_opener(urllib.request.HTTPHandler(), self.httpshandler, self.proxyhandler)
        except:
            print("Error creating opener with proxy: %s"%sys.exc_info()[1].__str__())
            self.httpopener = urllib.request.build_opener(urllib.request.HTTPHandler(), urllib.request.HTTPSHandler())
        if self.proxyip != "":
            self.randomproxyopener = self.buildopenerrandomproxy()
        else:
            self.randomproxyopener = None
        self.httpheaders = { 'User-Agent' : r'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/88.0.4324.150 Safari/537.36',  'Accept' : 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9', 'Accept-Language' : 'en-GB,en-US;q=0.9,en;q=0.8', 'Accept-Encoding' : 'gzip,deflate', 'Accept-Charset' : 'ISO-8859-1,utf-8;q=0.7,*;q=0.7', 'Pragma' : 'no-cache', 'Cache-Control' : 'no-cache', }
        self.httpheaders['upgrade-insecure-requests'] = "1"
        self.httpheaders['sec-fetch-dest'] = "document"
        self.httpheaders['sec-fetch-mode'] = "navigate"
        self.httpheaders['sec-fetch-site'] = "none"
        self.httpheaders['sec-fetch-user'] = "?1"
        self.httpheaders['sec-ch-ua-mobile'] = "?0"
        self.httpheaders['sec-ch-ua'] = "\".Not/A)Brand\";v=\"99\", \"Google Chrome\";v=\"103\", \"Chromium\";v=\"103\""
        self.httpheaders['sec-ch-ua-platform'] = "Linux"
        self.httpcookies = ""
        self.httpheaders['cookie'] = ""
        self.requesturl = "https://music.amazon.com/"
        self.httprequest = urllib.request.Request(self.requesturl, headers=self.httpheaders)
        try:
            self.httpresponse = self.httpopener.open(self.httprequest)
        except:
            print("Error making request to %s: %s"%(self.requesturl, sys.exc_info()[1].__str__()))
            return None
        self.httpcookies = BuzzBot._getCookieFromResponse(self.httpresponse)
        self.httpheaders['cookie'] = self.httpcookies


    def buildopenerrandomproxy(self):
        httpsproxycount = self.proxies['https'].__len__() - 1
        self.context = createrequestcontext()
        self.httpshandler = urllib.request.HTTPSHandler(context=self.context)
        try:
            httpsrandomctr = random.randint(0, httpsproxycount)
            self.proxyhandler = urllib.request.ProxyHandler({'https': self.proxies['https'][httpsrandomctr],})
            self.httpopener = urllib.request.build_opener(urllib.request.HTTPHandler(), self.httpshandler, self.proxyhandler)
        except:
            print("Error creating opener with proxy: %s"%sys.exc_info()[1].__str__())
            self.httpopener = urllib.request.build_opener(urllib.request.HTTPHandler(), self.httpshandler)
        return self.httpopener


    def makehttprequest(self, requrl):
        self.httpopener = self.buildopenerrandomproxy()
        self.httprequest = urllib.request.Request(requrl, headers=self.httpheaders)
        session = HTMLSession()
        self.httpresponse = session.get(requrl)
        return self.httpresponse


    def gethttpresponsecontent(self):
        self.httpcontent = self.httpresponse.html.html
        return str(self.httpcontent)


    def parsecontent(self, reqtype='search', reqformat='json'):
        """
        Parse self.content. 'reqformat' specifies the format of the content. 'reqtype' specifies what type of request returned the response content. At present, only json reqformat is supported.
        """
        self.results = [] # self.results will always be a list. In case of reqtype=episode, it would be a one member list.
        if reqformat.lower() == 'json':
            if reqtype == 'search':
                results = self.content['results']
                for rd in results:
                    try:
                        link = rd['link']
                    except:
                        link = ""
                    try:
                        audio = rd['audio']
                    except:
                        audio = ""
                    try:
                        listennotes = rd['podcast']['listennotes_url']
                    except:
                        listennotes = ""
                    try:
                        podcastid = rd['podcast']['id']
                    except:
                        podcastid = ""
                    try:
                        title = rd['title_original']
                    except:
                        title = ""
                    try:
                        itunesid = rd['itunes_id']
                    except:
                        itunesid = ""
                    d = {'link' : link, 'audio' : 'audio', 'listennotesurl' : listennotes, 'title' : title, 'itunesid' : itunesid, 'podcastid' : podcastid}
                    self.results.append(d)
            if reqtype == 'podcast': # Response came from a request for a podcast identified by a podcast Id
                handles = {}
                try:
                    handles['google'] = self.content['extra']['google_url']
                    handles['spotify'] = self.content['extra']['spotify_url']
                    handles['youtube'] = self.content['extra']['youtube_url']
                    handles['linkedin'] = self.content['extra']['linkedin_url']
                    handles['wechat'] = self.content['extra']['wechat_handle']
                    handles['patreon'] = self.content['extra']['patreon_handle']
                    handles['twitter'] = self.content['extra']['twitter_handle']
                    handles['facebook'] = self.content['extra']['facebook_handle']
                    handles['amazon_music'] = self.content['extra']['amazon_music_url']
                    handles['instagram'] = self.content['extra']['instagram_handle']
                except:
                    print("Error retrieving handles: %s"%sys.exc_info()[1].__str__())
                episodes = self.content['episodes']
                for episode in episodes:
                    try:
                        id = episode['id']
                    except:
                        continue # Without Id, we can't consider this object for our purpose
                    try:
                        link = episode['link']
                    except:
                        link = ""
                    try:
                        audio = episode['audio']
                    except:
                        audio = ""
                    try:
                        title = episode['title']
                    except:
                        title = ""
                    try:
                        listennotes = episode['listennotes_url']
                    except:
                        listennotes = ""
                    d = {'id' : id, 'link' : link, 'audio' : audio, 'title' : title, 'listennotes' : listennotes, 'handles' : handles}
                    self.results.append(d)
            if reqtype == 'episode':
                id = self.content['id']
                try:
                    link = self.content['link']
                except:
                    link = ""
                try:
                    audio = self.content['audio']
                except:
                    audio = ""
                try:
                    title = self.content['title']
                except:
                    title = ""
                try:
                    listennotes = self.content['listennotes_url']
                except:
                    listennotes = ""
                urls = []
                try:
                    url1 = self.content['podcast']['extra']['url1']
                    if url1 != "" and url1 is not None:
                        urls.append(url1)
                except:
                    pass
                try:
                    url2 = self.content['podcast']['extra']['url2']
                    if url2 != "" and url2 is not None:
                        urls.append(url2)
                except:
                    pass
                try:
                    url3 = self.content['podcast']['extra']['url3']
                    if url3 != "" and url3 is not None:
                        urls.append(url3)
                except:
                    pass
                d = {'id' : id, 'link' : link, 'audio' : audio, 'title' : title, 'listennotes' : listennotes, 'urls' : urls}
                self.results.append(d)
        return self.results


    def searchforpodcasts(self, searchkey):
        """
        Search Amazon Podcast (Listen) for a podcast matching the phrase specified using 'searchkey'.
        """
        try:
            self.response = self.podclient.search(q=searchkey, sort_by_date=1, only_in='title,description')
            self.content = self.response.json()
        except:
            print("Error in search: %s"%sys.exc_info()[1].__str__())
            return None
        return self.content


    def fetchpodcastbyId(self, podcast_id):
        """
        Fetch a podcast metadata using a valid Podcast Id.
        """
        try:
            self.response = self.podclient.fetch_podcast_by_id(id=podcast_id)
            self.content = self.response.json()
        except:
            print("Error retrieving a Podcast: %s"%sys.exc_info()[1].__str__())
            return None
        return self.content


    def fetchpodcastepisodebyId(self, episode_id):
        """
        Fetch a podcast episode by Id.
        """
        try:
            self.response = self.podclient.fetch_episode_by_id(id=episode_id, show_transcript=1)
            self.content = self.response.json()
        except:
            print("Error retrieving a podcast episode: %s"%sys.exc_info()[1].__str__())
            return None
        return self.content


    def existsincontent(self, regexpattern):
        content = self.httpcontent
        if re.search(regexpattern, content):
            return True
        return False


    def getvisualdict(self, paramstuple, episodeid="", mediaflag=0):
        urlid, sessid, ipaddr, csrftoken, csrfts, csrfrnd, devid, devtype, siteurl = paramstuple[0], paramstuple[1], paramstuple[2], paramstuple[3], paramstuple[4], paramstuple[5], paramstuple[6], paramstuple[7], paramstuple[8]
        siteurlparts = siteurl.split("/")
        siteurl = "/" + "/".join(siteurlparts[3:])
        ts = int(time.time() * 1000)
        httpheaders = {'accept' : '*/*', 'accept-encoding' : 'gzip,deflate', 'accept-language' : 'en-GB,en-US;q=0.9,en;q=0.8', 'cache-control' : 'no-cache', 'content-encoding' : 'amz-1.0', 'content-type' : 'application/json; charset=UTF-8', 'origin' : 'https://music.amazon.com', 'pragma' : 'no-cache', 'referer' : siteurl, 'sec-ch-ua' : '".Not/A)Brand";v="99", "Google Chrome";v="103", "Chromium";v="103"', 'sec-ch-ua-mobile' : '?0', 'sec-ch-ua-platform' : 'Linux', 'sec-fetch-dest' : 'empty', 'sec-fetch-mode' : 'cors', 'sec-fetch-site' : 'same-origin', 'user-agent' : 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/103.0.0.0 Safari/537.36', 'x-amz-target' : 'com.amazon.dmpbrowsevisualservice.skills.DMPBrowseVisualService.ShowPodcastWebSkill', 'x-amzn-requestid' : ''}
        httpheaders['cookie'] = ""
        httpheaders['cookie'] += self.httpheaders['cookie']
        self.httpopener = self.buildopenerrandomproxy()
        if mediaflag == 0:
            datadict = {"preset":"{\"id\":\"%s\",\"nextToken\":null}"%urlid,"identity":{"__type":"SOACoreInterface.v1_0#Identity","application":{"__type":"SOACoreInterface.v1_0#ApplicationIdentity","version":"2.1"},"user":{"__type":"SOACoreInterface.v1_0#UserIdentity","authentication":""},"request":{"__type":"SOACoreInterface.v1_0#RequestIdentity","id":"","sessionId":"%s"%sessid,"ipAddress":"%s"%ipaddr,"timestamp":ts,"domain":"music.amazon.com","csrf":{"__type":"SOACoreInterface.v1_0#Csrf","token":"%s"%csrftoken,"ts":"%s"%csrfts,"rnd":"%s"%csrfrnd}},"device":{"__type":"SOACoreInterface.v1_0#DeviceIdentity","id":"%s"%devid,"typeId":"%s"%devtype,"model":"WEBPLAYER","timeZone":"Asia/Calcutta","language":"en_US","height":"668","width":"738","osVersion":"n/a","manufacturer":"n/a"}},"clientStates":{"deeplink":{"url":"%s"%siteurl,"__type":"Podcast.DeeplinkInterface.v1_0#DeeplinkClientState"},"hidePromptPreference":{"preferenceMap":{},"__type":"Podcast.FollowPromptInterface.v1_0#HidePromptPreferenceClientState"}},"extra":{}}
        else:
            httpheaders['x-amz-target'] = "com.amazon.dmpplaybackvisualservice.skills.DMPPlaybackVisualService.PlayPodcastWebSkill"
            datadict = {"preset":"{\"podcastId\":\"%s\",\"startAtEpisodeId\":\"%s\"}"%(urlid, episodeid),"identity":{"__type":"SOACoreInterface.v1_0#Identity","application":{"__type":"SOACoreInterface.v1_0#ApplicationIdentity","version":"2.1"},"user":{"__type":"SOACoreInterface.v1_0#UserIdentity","authentication":""},"request":{"__type":"SOACoreInterface.v1_0#RequestIdentity","id":"","sessionId":"%s"%sessid,"ipAddress":"%s"%ipaddr,"timestamp":ts,"domain":"music.amazon.com","csrf":{"__type":"SOACoreInterface.v1_0#Csrf","token":"%s"%csrftoken,"ts":"%s"%csrfts,"rnd":"%s"%csrfrnd}},"device":{"__type":"SOACoreInterface.v1_0#DeviceIdentity","id":"%s"%devid,"typeId":"%s"%devtype,"model":"WEBPLAYER","timeZone":"Asia/Calcutta","language":"en_US","height":"668","width":"738","osVersion":"n/a","manufacturer":"n/a"}},"clientStates":{"deeplink":{"url":"%s"%siteurl,"__type":"Podcast.DeeplinkInterface.v1_0#DeeplinkClientState"}},"extra":{}}
        postdata = json.dumps(datadict).encode('utf-8')
        #print(postdata)
        httpheaders['content-length'] = postdata.__len__()
        requrl = "https://music.amazon.com/EU/api/podcast/browse/visual"
        if mediaflag == 0:
            self.httprequest = urllib.request.Request(requrl, data=postdata, headers=httpheaders)
        else:
            requrl = "https://music.amazon.com/EU/api/podcast/playback/visual"
            self.httprequest = urllib.request.Request(requrl, data=postdata, headers=httpheaders)
        try:
            self.httpresponse = self.httpopener.open(self.httprequest)
        except:
            print("Error making request to %s: %s"%(requrl, sys.exc_info()[1].__str__()))
            return {}
        returndata = _decodeGzippedContent(self.httpresponse.read())
        try:
            returndict = json.loads(returndata.encode('utf-8'))
        except:
            print("Error loading json data: %s"%(sys.exc_info()[1].__str__()))
            returndict = {}
        return returndict



class SpotifyBot(object):
    
    def __init__(self, client_id, client_secret, proxies):
        self.DEBUG = False
        self.humanize = True
        self.logging = True
        self.clientid = client_id
        self.clientsecret = client_secret
        self.redirecturi = "https://localhost:8000/"
        self.spotclient = spotipy.Spotify(auth_manager=SpotifyClientCredentials(client_id=client_id, client_secret=client_secret))
        self.proxies = proxies
        self.response = None # This would a response object from Amazon API
        self.content = None # This could be a text chunk or a binary data (like a Podcast content)
        self.results = []
        # HTTP(S) request/response and parameters
        self.httprequest = None
        self.httpresponse = None
        self.httpcontent = None
        try:
            self.proxyip, self.proxyport = self.proxies['https'][0].split(":")
        except:
            self.proxyip, self.proxyport = "", ""
        try:
            self.context = createrequestcontext()
            #if self.proxyip != "":
            #    socks.set_default_proxy(socks.SOCKS5, self.proxyip, int(self.proxyport))
            #    socket.socket = socks.socksocket
            self.httpshandler = urllib.request.HTTPSHandler(context=self.context)
            self.proxyhandler = urllib.request.ProxyHandler({'https': self.proxies['https'][0],})
            self.httpopener = urllib.request.build_opener(urllib.request.HTTPHandler(), self.httpshandler, self.proxyhandler)
        except:
            print("Error creating opener with proxy: %s"%sys.exc_info()[1].__str__())
            self.httpopener = urllib.request.build_opener(urllib.request.HTTPHandler(), urllib.request.HTTPSHandler())
        if self.proxyip != "":
            self.randomproxyopener = self.buildopenerrandomproxy()
        else:
            self.randomproxyopener = None
        self.httpheaders = { 'User-Agent' : r'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/88.0.4324.150 Safari/537.36',  'Accept' : 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9', 'Accept-Language' : 'en-us,en;q=0.5', 'Accept-Encoding' : 'gzip,deflate', 'Accept-Charset' : 'ISO-8859-1,utf-8;q=0.7,*;q=0.7', 'Connection' : 'keep-alive', }
        self.httpheaders['cache-control'] = "no-cache"
        self.httpheaders['upgrade-insecure-requests'] = "1"
        self.httpheaders['sec-fetch-dest'] = "document"
        self.httpheaders['sec-fetch-mode'] = "navigate"
        self.httpheaders['sec-fetch-site'] = "none"
        self.httpheaders['sec-fetch-user'] = "?1"
        self.httpheaders['sec-ch-ua-mobile'] = "?0"
        self.httpheaders['sec-ch-ua'] = "\".Not/A)Brand\";v=\"99\", \"Google Chrome\";v=\"103\", \"Chromium\";v=\"103\""
        self.httpheaders['sec-ch-ua-platform'] = "Linux"
        requesturl = "https://open.spotify.com/search"
        self.httprequest = urllib.request.Request(requesturl, headers=self.httpheaders)
        try:
            self.httpresponse = self.httpopener.open(self.httprequest)
        except:
            print("Error making request to %s: %s"%(requesturl, sys.exc_info()[1].__str__()))
            return None
        #print(self.httpresponse.headers)
        self.httpcookies = BuzzBot._getCookieFromResponse(self.httpresponse)
        # Prefix some standard cookies...
        d = datetime.now()
        day = d.strftime("%a")
        mon = d.strftime("%b")
        dd = d.strftime("%d")
        year = d.strftime("%Y")
        hh = d.strftime("%H")
        mm = d.strftime("%M")
        ss = d.strftime("%S")
        self.httpheaders['cookie'] = "sss=1; sp_m=in-en; _cs_c=0; sp_ab=%7B%222019_04_premium_menu%22%3A%22control%22%7D; spot=%7B%22t%22%3A1660164332%2C%22m%22%3A%22in-en%22%2C%22p%22%3Anull%7D;_sctr=1|1660156200000; OptanonAlertBoxClosed=2022-08-10T20:43:54.163Z;  ki_r=; ki_t=1660164170739%3B1661618190878%3B1661621393364%3B8%3B35; OptanonConsent=isIABGlobal=false&datestamp=" + day + "+" + mon + "+" + str(dd) + "+" + str(year) + "+" + str(hh) + "%3A" + str(mm) + "%3A" + str(ss) + "+GMT%2B0530+(India+Standard+Time)&version=6.26.0&hosts=&landingPath=NotLandingPage&groups=s00%3A1%2Cf00%3A1%2Cm00%3A1%2Ct00%3A1%2Ci00%3A1%2Cf02%3A1%2Cm02%3A1%2Ct02%3A1&AwaitingReconsent=false&geolocation=IN%3BDL; " + self.httpcookies
        if self.DEBUG:
            print("Cookie Sent: %s"%self.httpheaders['cookie'])
        

    def buildopenerrandomproxy(self):
        httpsproxycount = self.proxies['https'].__len__() - 1
        self.context = createrequestcontext()
        self.httpshandler = urllib.request.HTTPSHandler(context=self.context)
        try:
            httpsrandomctr = random.randint(0, httpsproxycount)
            self.proxyhandler = urllib.request.ProxyHandler({'https': self.proxies['https'][httpsrandomctr],})
            self.httpopener = urllib.request.build_opener(urllib.request.HTTPHandler(), self.httpshandler, self.proxyhandler)
        except:
            print("Error creating opener with proxy: %s"%sys.exc_info()[1].__str__())
            self.httpopener = urllib.request.build_opener(urllib.request.HTTPHandler(), self.httpshandler)
        return self.httpopener



    def searchforpodcasts(self, searchkey, limit=20):
        self.response = self.spotclient.search(q=searchkey, limit=limit)
        self.content = self.response
        url = self.response['tracks']['href']
        items = self.response['tracks']['items']
        self.results = []
        for item in items:
            try:
                albumspotifyurl = str(item['album']['external_urls']['spotify'])
            except:
                albumspotifyurl = ""
            try:
                albumid = str(item['album']['id'])
            except:
                albumid = ""
            try:
                albumuri = str(item['album']['uri'])
            except:
                albumuri = ""
            try:
                itemspotifyurl = str(item['external_urls']['spotify'])
            except:
                itemspotifyurl = ""
            try:
                spotifyhref = str(item['href'])
            except:
                spotifyhref = ""
            try:
                itemid = str(item['id'])
            except:
                itemid = ""
            try:
                itemuri = str(item['uri'])
            except:
                itemuri = ""
            d = {'albumspotifyurl' : albumspotifyurl, 'albumid' : albumid, 'albumuri' : albumuri, 'itemspotifyurl' : itemspotifyurl, 'spotifyhref' : spotifyhref, 'itemid' : itemid, 'itemuri' : itemuri}
            self.results.append(d)
        return self.results


    def makehttprequest(self, requrl, headers=None):
        self.httpopener = self.buildopenerrandomproxy()
        if headers is None:
            headers = self.httpheaders
        self.httprequest = urllib.request.Request(requrl, headers=headers)
        try:
            self.httpresponse = self.httpopener.open(self.httprequest)
        except:
            print("Error making request to %s: %s"%(requrl, sys.exc_info()[1].__str__()))
            return None
        return self.httpresponse


    def gethttpresponsecontent(self):
        try:
            encodedcontent = self.httpresponse.read()
            self.httpcontent = _decodeGzippedContent(encodedcontent)
        except:
            print("Error reading content: %s"%sys.exc_info()[1].__str__())
            self.httpcontent = ""
            return ""
        return str(self.httpcontent)


    def existsincontent(self, regexpattern):
        content = self.httpcontent
        if re.search(regexpattern, content):
            return True
        return False


    def getepisodemp3url(self, episodeid, accesstoken, clienttoken):
        episodeurl = "https://spclient.wg.spotify.com/soundfinder/v1/unauth/episode/%s/com.widevine.alpha?market=IN"%episodeid
        httpheaders = { 'User-Agent' : r'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/88.0.4324.150 Safari/537.36',  'Accept' : 'application/json', 'Accept-Language' : 'en', 'Accept-Encoding' : 'gzip,deflate', 'Cache-control' : 'no-cache', 'Connection' : 'keep-alive', 'Pragma' : 'no-cache', 'Referer' : 'https://open.spotify.com/', 'Sec-Fetch-Site' : 'same-site', 'Sec-Fetch-Mode' : 'cors', 'Sec-Fetch-Dest' : 'empty', 'sec-ch-ua-platform' : 'Linux', 'sec-ch-ua-mobile' : '?0', 'sec-ch-ua' : '".Not/A)Brand";v="99", "Google Chrome";v="103", "Chromium";v="103"', 'Origin' : 'https://open.spotify.com', 'Authorization' : "Bearer %s"%accesstoken, 'client-token' : clienttoken, 'app-platform' : 'WebPlayer'}
        self.httpopener = self.buildopenerrandomproxy()
        epinforequest = urllib.request.Request(episodeurl, headers=httpheaders)
        try:
            self.httpresponse = self.httpopener.open(epinforequest)
        except:
            print("Error making episode info request to %s: %s"%(episodeinfourl, sys.exc_info()[1].__str__()))
            return []
        self.httpcontent = _decodeGzippedContent(self.httpresponse.read())
        mp3url = ""
        try:
            contentdict = json.loads(self.httpcontent)
            mp3url = contentdict['passthroughUrl']
        except:
            print("Error in getting mp3 URL: %s"%sys.exc_info()[1].__str__())
        return mp3url


    def getallepisodes(self):
        episodeurlpattern = re.compile("(https\:\/\/open\.spotify\.com\/episode\/[^\"]+)\"", re.DOTALL)
        allepisodeurls = re.findall(episodeurlpattern, str(self.httpcontent))
        return allepisodeurls


    def player(self, uid):
        scope = "user-read-playback-state,user-modify-playback-state"
        spotobj = spotipy.Spotify(client_credentials_manager=SpotifyOAuth(scope=scope, client_id=self.clientid, client_secret=self.clientsecret, redirect_uri=self.redirecturi))
        devices = spotobj.devices()
        spotobj.start_playback(uris=['spotify:track:%s'%uid])



    def getclienttoken(self):
        requesturl = "https://clienttoken.spotify.com/v1/clienttoken"
        cid = "d8a5ed958d274c2e8ee717e6a4b0971d" # This ought to be self.clientid. Need to find a different clientid if this one gets blacklisted.
        data = {"client_data":{"client_version":"1.1.94.50.g7884d765","client_id":"%s"%cid,"js_sdk_data":{"device_brand":"unknown","device_model":"desktop","os":"Linux","os_version":"unknown"}}}
        databytes = json.dumps(data).encode('utf-8')
        httpheaders = { 'User-Agent' : r'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/88.0.4324.150 Safari/537.36',  'Accept' : 'application/json', 'Accept-Language' : 'en-GB,en-US;q=0.9,en;q=0.8', 'Accept-Encoding' : 'gzip,deflate', 'Cache-control' : 'no-cache', 'Connection' : 'keep-alive', 'Pragma' : 'no-cache', 'Referer' : 'https://open.spotify.com/', 'Sec-Fetch-Site' : 'same-site', 'Sec-Fetch-Mode' : 'cors', 'Sec-Fetch-Dest' : 'empty', 'sec-ch-ua-platform' : 'Linux', 'sec-ch-ua-mobile' : '?0', 'sec-ch-ua' : '".Not/A)Brand";v="99", "Google Chrome";v="103", "Chromium";v="103"', 'Content-Type' : 'application/json', 'Origin' : 'https://open.spotify.com'}
        httpheaders['Content-Length'] = databytes.__len__()
        self.httpopener = self.buildopenerrandomproxy()
        clienttokenrequest = urllib.request.Request(requesturl, data=databytes, headers=httpheaders)
        try:
            self.httpresponse = self.httpopener.open(clienttokenrequest)
        except:
            print("Error making client token request to %s: %s"%(requesturl, sys.exc_info()[1].__str__()))
            return ""
        self.httpcontent = _decodeGzippedContent(self.httpresponse.read())
        try:
            respdict = json.loads(self.httpcontent)
            clienttoken = respdict['granted_token']['token']
        except:
            clienttoken = ""
        return clienttoken


    def getepisode(self, epurl):
        httpheaders = { 'User-Agent' : r'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/88.0.4324.150 Safari/537.36',  'Accept' : '*/*', 'Accept-Language' : 'en-GB,en-US;q=0.9,en;q=0.8', 'Accept-Encoding' : 'gzip,deflate', 'Cache-control' : 'no-cache', 'Connection' : 'keep-alive', 'Pragma' : 'no-cache', 'Referer' : 'https://open.spotify.com/', 'Sec-Fetch-Site' : 'same-site', 'Sec-Fetch-Mode' : 'cors', 'Sec-Fetch-Dest' : 'empty', 'sec-ch-ua-platform' : 'Linux', 'sec-ch-ua-mobile' : '?0', 'sec-ch-ua' : '".Not/A)Brand";v="99", "Google Chrome";v="103", "Chromium";v="103"', 'Origin' : 'https://open.spotify.com', 'Cookie' : self.httpheaders['cookie']}
        self.makehttprequest(epurl, headers=httpheaders)
        content = self.httpresponse.read() # Actually, we don't need the content.
        return content



class AppleBot(object):

    def __init__(self, proxies):
        self.DEBUG = False
        self.humanize = True
        self.logging = True
        self.proxies = proxies
        self.response = None # This would a response object from Amazon API
        self.content = None # This could be a text chunk or a binary data (like a Podcast content)
        self.results = []
        # HTTP(S) request/response and parameters
        self.httprequest = None
        self.httpresponse = None
        self.httpcontent = None
        try:
            self.proxyip, self.proxyport = self.proxies['https'][0].split(":")
        except:
            self.proxyip, self.proxyport = "", ""
        try:
            self.context = createrequestcontext()
            #if self.proxyip != "":
            #    socks.set_default_proxy(socks.SOCKS5, self.proxyip, int(self.proxyport))
            #    socket.socket = socks.socksocket
            self.httpshandler = urllib.request.HTTPSHandler(context=self.context)
            self.proxyhandler = urllib.request.ProxyHandler({'https': self.proxies['https'][0],})
            self.httpopener = urllib.request.build_opener(urllib.request.HTTPHandler(), self.httpshandler, self.proxyhandler, NoRedirectHandler())
        except:
            print("Error creating opener with proxy: %s"%sys.exc_info()[1].__str__())
            self.httpopener = urllib.request.build_opener(urllib.request.HTTPHandler(), urllib.request.HTTPSHandler(), NoRedirectHandler())
        if self.proxyip != "":
            self.randomproxyopener = self.buildopenerrandomproxy()
        else:
            self.randomproxyopener = None
        self.httpheaders = { 'User-Agent' : r'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/88.0.4324.150 Safari/537.36',  'Accept' : 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9', 'Accept-Language' : 'en-us,en;q=0.5', 'Accept-Encoding' : 'gzip,deflate', 'Accept-Charset' : 'ISO-8859-1,utf-8;q=0.7,*;q=0.7', 'Keep-Alive' : '115', 'Connection' : 'keep-alive', }
        self.httpheaders['cache-control'] = "max-age=0"
        self.httpheaders['upgrade-insecure-requests'] = "1"
        self.httpheaders['sec-fetch-dest'] = "document"
        self.httpheaders['sec-fetch-mode'] = "navigate"
        self.httpheaders['sec-fetch-site'] = "same-origin"
        self.httpheaders['sec-fetch-user'] = "?1"
        self.httpheaders['sec-ch-ua-mobile'] = "?0"
        self.httpheaders['sec-ch-ua'] = "\".Not/A)Brand\";v=\"99\", \"Google Chrome\";v=\"103\", \"Chromium\";v=\"103\""
        self.httpheaders['sec-ch-ua-platform'] = "Linux"
        self.httpcookies = None


    def buildopenerrandomproxy(self):
        httpsproxycount = self.proxies['https'].__len__() - 1
        self.context = createrequestcontext()
        self.httpshandler = urllib.request.HTTPSHandler(context=self.context)
        try:
            httpsrandomctr = random.randint(0, httpsproxycount)
            self.proxyhandler = urllib.request.ProxyHandler({'https': self.proxies['https'][httpsrandomctr],})
            self.httpopener = urllib.request.build_opener(urllib.request.HTTPHandler(), self.httpshandler, self.proxyhandler, NoRedirectHandler())
        except:
            print("Error creating opener with proxy: %s"%sys.exc_info()[1].__str__())
            self.httpopener = urllib.request.build_opener(urllib.request.HTTPHandler(), self.httpshandler, NoRedirectHandler())
        return self.httpopener
        


    def searchforpodcasts(self, searchkey, country="us", limit=20):
        podcasts = podsearch.search(searchkey, country=country, limit=limit)


    def makehttprequest(self, requrl):
        self.httpopener = self.buildopenerrandomproxy()
        self.httprequest = urllib.request.Request(requrl, headers=self.httpheaders)
        try:
            self.httpresponse = self.httpopener.open(self.httprequest)
        except:
            print("Error making request to %s: %s"%(requrl, sys.exc_info()[1].__str__()))
            return None
        return self.httpresponse


    def gethttpresponsecontent(self):
        try:
            encodedcontent = self.httpresponse.read()
            self.httpcontent = _decodeGzippedContent(encodedcontent)
        except:
            print("Error reading content: %s"%sys.exc_info()[1].__str__())
            self.httpcontent = ""
            return ""
        return str(self.httpcontent)


    def existsincontent(self, regexpattern):
        content = str(self.httpcontent)
        #print(content)
        if re.search(regexpattern, content):
            return True
        return False


    def listpodcastsonpage(self):
        content = str(self.httpcontent)
        soup = BeautifulSoup(content, features="html.parser")
        allanchortags = soup.find_all("a", {'class' : 'link tracks__track__link--block'})
        podcastlinks = []
        for atag in allanchortags:
            alink = atag['href']
            podcastlinks.append(alink)
        return podcastlinks


    def downloadpodcast(self, podcastpagelink, dumpdir):
        self.makehttprequest(podcastpagelink)
        content = self.gethttpresponsecontent()
        content = content.replace("\\", "")
        assetpattern = re.compile('\"assetUrl\":\"([^\"]+)\"', re.DOTALL)
        aps = re.search(assetpattern, content)
        resourceurl = ""
        if aps:
            resourceurl = aps.groups()[0]
        self.httpopener = self.buildopenerrandomproxy()
        #print("Resource URL: %s"%resourceurl)
        self.httprequest = urllib.request.Request(resourceurl, headers=self.httpheaders)
        try:
            self.httpresponse = self.httpopener.open(self.httprequest)
        except:
            print("Error making request to %s: %s"%(resourceurl, sys.exc_info()[1].__str__()))
            return None
        try:
            location = self.httpresponse.getheader("location")
        except:
            print("Could not find header named 'location'")
            location = ""
        try:
            self.httprequest = urllib.request.Request(location, headers=self.httpheaders)
            self.httpresponse = self.httpopener.open(self.httprequest)
            content = self.httpresponse.read()
            redirecturlpattern = re.compile("href=\"([^\"]+)\"", re.DOTALL|re.IGNORECASE)
            rps = re.search(redirecturlpattern, str(content))
            if rps:
                mediaurl = rps.groups()[0]
            else:
                mediaurl = ""
        except:
            print("Error getting MediaURL from '%s': %s"%(location, sys.exc_info()[1].__str__()))
            mediaurl = ""
        mediaurl = mediaurl.replace("amp;", "")
        #print("Media URL: %s"%mediaurl)
        httpheaders = { 'User-Agent' : r'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/88.0.4324.150 Safari/537.36',  'Accept' : '*/*', 'Accept-Language' : 'en-GB,en-US;q=0.9,en;q=0.8', 'Accept-Encoding' : 'identity;q=1, *;q=0', 'Accept-Charset' : 'ISO-8859-1,utf-8;q=0.7,*;q=0.7', 'Cache-control' : 'no-cache', 'Connection' : 'keep-alive', 'Pragma' : 'no-cache', 'Referer' : 'https://podcasts.apple.com/', 'Sec-Fetch-Site' : 'cross-site', 'Sec-Fetch-Mode' : 'no-cors', 'Sec-Fetch-Dest' : 'audio', 'sec-ch-ua-platform' : 'Linux', 'sec-ch-ua-mobile' : '?0', 'sec-ch-ua' : '".Not/A)Brand";v="99", "Google Chrome";v="103", "Chromium";v="103"', 'range' : 'bytes=0-'}
        try:
            self.httprequest = urllib.request.Request(mediaurl, headers=httpheaders)
            self.httpresponse = self.httpopener.open(self.httprequest)
            mediacontent = self.httpresponse.read()
        except:
            print("Error in making media request: %s"%sys.exc_info()[1].__str__())
            mediacontent = b""
        if self.DEBUG:
            t = str(int(time.time() * 1000))
            dumpfile = dumpdir + os.path.sep + "apple_" + t + ".mp3"
            fp = open(dumpfile, "wb")
            fp.write(mediacontent)
            fp.close()
        return mediacontent


class BuzzBot(object):
    
    def __init__(self, podlisturl, amazonkey, spotifyclientid, spotifyclientsecret, parent, proxieslist=[]):
        self.DEBUG = False
        self.humanize = True
        self.logging = True
        self.cleanupmedia = True
        self.parent = weakref.ref(parent)
        self.msglabeltext = parent.msglabeltext
        self.proxies = {'https' : proxieslist,}
        self.amazonkey = amazonkey
        self.spotifyclientid = spotifyclientid
        self.spotifyclientsecret = spotifyclientsecret
        self.results = []
        # HTTP(S) request/response and parameters
        self.httprequest = None
        self.httpresponse = None
        self.httpcontent = None
        self.logdir = os.getcwd() + os.path.sep + "logs"
        self.logfile = self.logdir + os.path.sep + "hitbot.log"
        self.logger = Logger(self.logfile)
        try:
            self.proxyip, self.proxyport = self.proxies['https'][0].split(":")
        except:
            self.proxyip, self.proxyport = "", ""
        try:
            self.context = createrequestcontext()
            #if self.proxyip != "":
            #    socks.set_default_proxy(socks.https, self.proxyip, int(self.proxyport))
            #    socket.socket = socks.socksocket
            self.httpshandler = urllib.request.HTTPSHandler(context=self.context)
            self.proxyhandler = urllib.request.ProxyHandler({'https': self.proxies['https'][0]})
            self.httpopener = urllib.request.build_opener(urllib.request.HTTPHandler(), self.httpshandler, self.proxyhandler)
        except:
            print("Error creating opener with proxy: %s"%sys.exc_info()[1].__str__())
            self.httpopener = urllib.request.build_opener(urllib.request.HTTPHandler(), urllib.request.HTTPSHandler())
        if self.proxyip != "":
            self.randomproxyopener = self.buildopenerrandomproxy()
        else:
            self.randomproxyopener = None
        self.httpheaders = { 'User-Agent' : r'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/88.0.4324.150 Safari/537.36',  'Accept' : 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9', 'Accept-Language' : 'en-us,en;q=0.5', 'Accept-Encoding' : 'gzip,deflate', 'Accept-Charset' : 'ISO-8859-1,utf-8;q=0.7,*;q=0.7', 'Keep-Alive' : '115', 'Connection' : 'keep-alive', }
        self.httpheaders['cache-control'] = "max-age=0"
        self.httpheaders['upgrade-insecure-requests'] = "1"
        self.httpheaders['sec-fetch-dest'] = "document"
        self.httpheaders['sec-fetch-mode'] = "navigate"
        self.httpheaders['sec-fetch-site'] = "same-origin"
        self.httpheaders['sec-fetch-user'] = "?1"
        self.httpheaders['sec-ch-ua-mobile'] = "?0"
        self.httpheaders['sec-ch-ua'] = "\".Not/A)Brand\";v=\"99\", \"Google Chrome\";v=\"103\", \"Chromium\";v=\"103\""
        self.httpheaders['sec-ch-ua-platform'] = "Linux"
        self.httpcookies = None
        self.requesturl = podlisturl
        self.podcasttitle = ""
        self.hitstatus = {} # A dict of site names as keys and a list of boolean values specifying hit or miss
        self.amazonsettarget = -1
        self.spotifysettarget = -1
        self.applesettarget = -1
        self.dumpdir = os.getcwd() + os.path.sep + "mediadumps"
        if not os.path.isdir(self.dumpdir):
            os.makedirs(self.dumpdir, 0o777)
        self.logger.write("Starting run at: %s\n"%datetime.strftime(datetime.now(), "%d-%b-%Y %H:%M:%S"))


    def buildopenerrandomproxy(self):
        httpsproxycount = self.proxies['https'].__len__() - 1
        self.context = createrequestcontext()
        self.httpshandler = urllib.request.HTTPSHandler(context=self.context)
        try:
            httpsrandomctr = random.randint(0, httpsproxycount)
            self.proxyhandler = urllib.request.ProxyHandler({'https': self.proxies['https'][httpsrandomctr],})
            self.httpopener = urllib.request.build_opener(urllib.request.HTTPHandler(), self.httpshandler, self.proxyhandler)
            if self.logging:
                self.logger.write("Created opener using proxy %s\n"%self.proxies['https'][httpsrandomctr])
        except:
            print("Error creating opener with proxy: %s"%sys.exc_info()[1].__str__())
            if self.logging:
                self.logger.write("Error creating opener with proxy: %s"%sys.exc_info()[1].__str__())
            self.httpopener = urllib.request.build_opener(urllib.request.HTTPHandler(), urllib.request.HTTPSHandler())
        return self.httpopener


    def settargetcounts(self, amazonsettarget, spotifysettarget, applesettarget):
        try:
            self.amazonsettarget = int(amazonsettarget)
        except:
            pass
        try:
            self.spotifysettarget = int(spotifysettarget)
        except:
            pass
        try:
            self.applesettarget = int(applesettarget)
        except:
            pass
        if self.logging:
            self.logger.write("Target counts - Amazon: %s, Apple: %s, Spotify: %s\n"%(self.amazonsettarget, self.applesettarget, self.spotifysettarget))


    def makerequest(self):
        self.httpopener = self.buildopenerrandomproxy()
        if self.logging:
            self.logger.write("Making GET request to %s\n"%self.requesturl)
        self.httprequest = urllib.request.Request(self.requesturl, headers=self.httpheaders)
        try:
            self.httpresponse = self.httpopener.open(self.httprequest)
        except:
            print("Error making request to %s: %s"%(self.requesturl, sys.exc_info()[1].__str__()))
            if self.logging:
                self.logger.write("Error making request to %s: %s\n"%(self.requesturl, sys.exc_info()[1].__str__()))
            return None
        self.httpcookies = self.__class__._getCookieFromResponse(self.httpresponse)
        self.httpheaders["cookie"] = self.httpcookies
        if self.logging:
            self.logger.write("Cookie received: %s\n"%self.httpheaders["cookie"])
        return self.httpresponse


    def _getCookieFromResponse(cls, lastHttpResponse):
        cookies = ""
        responseCookies = lastHttpResponse.getheader("Set-Cookie")
        pathPattern = re.compile(r"Path=/;", re.IGNORECASE)
        domainPattern = re.compile(r"Domain=[^;,]+(;|,)", re.IGNORECASE)
        expiresPattern = re.compile(r"Expires=[^;]+;", re.IGNORECASE)
        maxagePattern = re.compile(r"Max-Age=[^;]+;", re.IGNORECASE)
        samesitePattern = re.compile(r"SameSite=[^;]+;", re.IGNORECASE)
        securePattern = re.compile(r"secure;?", re.IGNORECASE)
        httponlyPattern = re.compile(r"HttpOnly;?", re.IGNORECASE)
        if responseCookies and responseCookies.__len__() > 1:
            cookieParts = responseCookies.split("Path=/")
            for i in range(cookieParts.__len__()):
                cookieParts[i] = re.sub(domainPattern, "", cookieParts[i])
                cookieParts[i] = re.sub(expiresPattern, "", cookieParts[i])
                cookieParts[i] = re.sub(maxagePattern, "", cookieParts[i])
                cookieParts[i] = re.sub(samesitePattern, "", cookieParts[i])
                cookieParts[i] = re.sub(securePattern, "", cookieParts[i])
                cookieParts[i] = re.sub(pathPattern, "", cookieParts[i])
                cookieParts[i] = re.sub(httponlyPattern, "", cookieParts[i])
                cookieParts[i] = cookieParts[i].replace(",", "")
                cookieParts[i] = re.sub(re.compile("\s+", re.DOTALL), "", cookieParts[i])
                cookies += cookieParts[i]
        cookies = cookies.replace(";;", ";")
        return(cookies)

    _getCookieFromResponse = classmethod(_getCookieFromResponse)


    def gethttpresponsecontent(self):
        try:
            encodedcontent = self.httpresponse.read()
            self.httpcontent = _decodeGzippedContent(encodedcontent)
        except:
            print("Error reading content: %s"%sys.exc_info()[1].__str__())
            if self.logging:
                self.logger.write("Error reading content: %s\n"%sys.exc_info()[1].__str__())
            self.httpcontent = None
            return None
        return str(self.httpcontent)


    def getpodcasturls(self):
        content = str(self.httpcontent)
        soup = BeautifulSoup(content, features="html.parser")
        podcastsites = ['apple', 'google', 'amazon', 'spotify', 'overcast', 'stitcher', 'iheart', 'tun.in', 'podcastaddict', 'castro', 'castbox', 'podchaser', 'pcs.st', 'deezer', 'listennotes', 'player.fm', 'podcastindex', 'podfriend', 'buzzsprout']
        self.results = {}
        if not soup:
            print("Error getting html content: %s"%sys.exc_info()[1].__str__())
            if self.logging:
                self.logger.write("Error getting html content: %s\n"%sys.exc_info()[1].__str__())
            return self.results
        h1tag = soup.find("h1")
        if not h1tag:
            return {}
        h1contents = h1tag.renderContents().decode('utf-8')
        self.podcasttitle = h1contents
        self.podcasttitle = self.podcasttitle.replace("\n", "").replace("\r", "")
        sectiontag = soup.find("section", {'class' : 'p-8'})
        allanchors = []
        if sectiontag is not None:
            allanchors = sectiontag.find_all("a")
        else:
            print("Could not find the anchor tags for podcasts URLs")
            if self.logging:
                self.logger.write("Could not find the anchor tags for podcasts URLs\n")
            return self.results
        for anchor in allanchors:
            if anchor is not None and 'href' in str(anchor):
                podcasturl = anchor['href']
                for podsite in podcastsites:
                    if podsite in podcasturl:
                        self.results[podsite] = podcasturl
                    else:
                        pass
        if self.logging:
            self.logger.write("Podcast URLs: %s\n"%self.results.__str__())
        return self.results


    def hitpodcast(self, siteurl, sitename, targetcount=-1):
        global AMAZON_HIT_STAT
        global SPOTIFY_HIT_STAT
        global APPLE_HIT_STAT
        titleregex = makeregex(self.podcasttitle)
        apikey = self.amazonkey
        clientid = self.spotifyclientid
        clientsecret = self.spotifyclientsecret
        ctr = 0
        if targetcount == -1:
            targetcount = 10000 # We set this to 10000, a suitably large number of hits
        if self.logging:
            self.logger.write("Starting podcast hits for '%s': Target count = %s\n"%(sitename, targetcount))
        if sitename.lower() == "apple":
            if self.DEBUG:
                print(siteurl)
            if self.logging:
                self.logger.write("Apple URL: %s\n"%siteurl)
            statuspattern = re.compile("APPLE\:\s+\d+", re.DOTALL)
            applebot = AppleBot(self.proxies)
            applebot.DEBUG = self.DEBUG
            applebot.humanize = self.humanize
            applebot.logging = self.logging
            applebot.makehttprequest(siteurl)
            applebot.gethttpresponsecontent()
            podcastlinks = applebot.listpodcastsonpage()
            ctr = 0
            while ctr < targetcount :
                if self.DEBUG:
                    print("APPLE ITERATION #%s ======================="%ctr)
                if self.logging:
                    self.logger.write("APPLE ITERATION #%s =======================\n"%ctr)
                for pclink in podcastlinks:
                    if self.logging:
                        self.logger.write("Getting Apple podcast mp3 from %s\n"%pclink)
                    if self.humanize:
                        ht = getrandominterval(5)
                        time.sleep(ht)
                    resp = applebot.downloadpodcast(pclink, self.dumpdir)
                    APPLE_HIT_STAT += 1
                    curmessagecontent = self.msglabeltext.get()
                    replacementmessage = "APPLE: %s"%APPLE_HIT_STAT
                    curmessagecontent = statuspattern.sub(replacementmessage, curmessagecontent)
                    self.msglabeltext.set(curmessagecontent)
                ctr += 1
            # Check to see if self.podcasttitle exists in the retrieved content
            boolret = applebot.existsincontent(titleregex)
            if "apple" in self.hitstatus.keys():
                self.hitstatus['apple'].append(boolret)
            else:
                self.hitstatus['apple'] = []
                self.hitstatus['apple'].append(boolret)
        elif sitename.lower() == "spotify":
            spotbot = SpotifyBot(clientid, clientsecret, self.proxies) # Get this from the environment
            if self.DEBUG:
                print("Spotify: %s"%siteurl)
            if self.logging:
                self.logger.write("Spotify URL: %s\n"%siteurl)
            spotbot.DEBUG = self.DEBUG
            spotbot.humanize = self.humanize
            spotbot.logging = self.logging
            statuspattern = re.compile("SPOTIFY\:\s+\d+", re.DOTALL)
            spotbot.makehttprequest(siteurl)
            spotbot.gethttpresponsecontent()
            episodeurls = spotbot.getallepisodes()
            episodeidlist = []
            episodeurlpattern = re.compile("https\:\/\/open\.spotify\.com\/episode\/([^\"]+)$")
            episodeitemlist = []
            for epurl in episodeurls:
                eps = re.search(episodeurlpattern, epurl)
                if eps:
                    epid = eps.groups()[0]
                    episodeidlist.append(epid)
            episodeids = ",".join(episodeidlist)
            if self.logging:
                self.logger.write("Spotify episode Ids: %s\n"%episodeids)
            #print(episodeurls)
            clientid, accesstoken = "", ""
            clientidpattern = re.compile("\"clientId\"\:\"([^\"]+)\"", re.DOTALL)
            accesstokenpattern = re.compile("\"accessToken\"\:\"([^\"]+)\",", re.DOTALL)
            correlationidpattern = re.compile("\"correlationId\"\:\"([^\"]+)\",")
            cps = re.search(clientidpattern, spotbot.httpcontent)
            aps = re.search(accesstokenpattern, spotbot.httpcontent)
            cdps = re.search(correlationidpattern, spotbot.httpcontent)
            if cps:
                clientid = cps.groups()[0]
            if aps:
                accesstoken = aps.groups()[0]
            if cdps:
                correlationid = cdps.groups()[0]
            clienttoken = spotbot.getclienttoken()
            if self.logging:
                self.logger.write("Spotify access token: %s, client token: %s\n"%(accesstoken, clienttoken))
            spotmp3list = []
            for eid in episodeidlist:
                epmp3url = spotbot.getepisodemp3url(eid, accesstoken, clienttoken)
                if self.DEBUG:
                    print("Spotify mp3 URL: %s"%epmp3url)
                if self.logging:
                    self.logger.write("Spotify mp3 URL: %s\n"%epmp3url)
                spotmp3list.append(epmp3url)
            while ctr < targetcount:
                if self.DEBUG:
                    print("SPOTIFY ITERATION #%s ======================="%ctr)
                if self.logging:
                    self.logger.write("SPOTIFY ITERATION #%s =======================\n"%ctr)
                for epurl in spotmp3list:
                    if self.humanize:
                        ht = getrandominterval(5)
                        time.sleep(ht)
                    content = spotbot.getepisode(epurl)
                    if self.logging:
                        self.logger.write("Getting Spotify mp3 from %s\n"%epurl)
                    if self.DEBUG:
                        t = str(int(time.time() * 1000))
                        fs = open(self.dumpdir + os.path.sep + "spotify_%s.mp3"%t, "wb")
                        fs.write(content)
                        fs.close()
                    SPOTIFY_HIT_STAT += 1
                    curmessagecontent = self.msglabeltext.get()
                    replacementmessage = "SPOTIFY: %s"%SPOTIFY_HIT_STAT
                    curmessagecontent = statuspattern.sub(replacementmessage, curmessagecontent)
                    self.msglabeltext.set(curmessagecontent)
                ctr += 1
            # Check to see if self.podcasttitle exists in the retrieved content
            boolret = spotbot.existsincontent(titleregex)
            if "spotify" in self.hitstatus.keys():
                self.hitstatus['spotify'].append(boolret)
            else:
                self.hitstatus['spotify'] = []
                self.hitstatus['spotify'].append(boolret)
        elif sitename.lower() == "amazon":
            ambot = AmazonBot(apikey, self.proxies) # Get this from the environment
            if self.DEBUG:
                print("Amazon: %s"%siteurl)
            if self.logging:
                self.logger.write("Amazon URL: %s\n"%siteurl)
            ambot.DEBUG = self.DEBUG
            ambot.humanize = self.humanize
            ambot.logging = self.logging
            statuspattern = re.compile("AMAZON\:\s+\d+", re.DOTALL)
            idpattern = re.compile("https\:\/\/music\.amazon\.com\/podcasts\/(.*)$")
            idps = re.search(idpattern, siteurl)
            urlid = ""
            if idps:
                urlid = idps.groups()[0]
            else:
                pass # If urlid can't be found, then there is actually not much we can do.
            ambot.makehttprequest(siteurl)
            ambot.gethttpresponsecontent()
            devicetypepattern = re.compile("\"deviceType\"\:\s*\"([^\"]+)\",", re.DOTALL)
            deviceidpattern = re.compile("\"deviceId\"\:\s*\"([^\"]+)\",", re.DOTALL)
            faviconpattern = re.compile("\"faviconUrl\"\:\s*\"([^\"]+)\",", re.DOTALL)
            marketplacepattern = re.compile("\"marketplaceId\"\:\s*\"([^\"]+)\",", re.DOTALL)
            sessionidpattern = re.compile("\"sessionId\"\:\s*\"([^\"]+)\",", re.DOTALL)
            ipaddresspattern = re.compile("\"ipAddress\"\:\s*\"([^\"]+)\",", re.DOTALL)
            csrftokenpattern = re.compile("\"token\"\:\s*\"([^\"]+)\",", re.DOTALL)
            csrftspattern = re.compile("\"ts\"\:\s*\"([^\"]+)\",", re.DOTALL)
            csrfrndpattern = re.compile("\"rnd\"\:\s*\"([^\"]+)\",", re.DOTALL)
            devtype, devid, favicon, mktplace, sessid, ipaddr, csrftoken, csrfts, csrfrnd = "", "", "", "", "", "", "", "", ""
            dts = re.search(devicetypepattern, ambot.httpcontent)
            dis = re.search(deviceidpattern, ambot.httpcontent)
            fis = re.search(faviconpattern, ambot.httpcontent)
            mks = re.search(marketplacepattern, ambot.httpcontent)
            sss = re.search(sessionidpattern, ambot.httpcontent)
            ips = re.search(ipaddresspattern, ambot.httpcontent)
            cts = re.search(csrftokenpattern, ambot.httpcontent)
            css = re.search(csrftspattern, ambot.httpcontent)
            crs = re.search(csrfrndpattern, ambot.httpcontent)
            if dts:
                devtype = dts.groups()[0]
            if dis:
                devid = dis.groups()[0]
            if fis:
                favicon = fis.groups()[0]
            if mks:
                mktplace = mks.groups()[0]
            if sss:
                sessid = sss.groups()[0]
            if ips:
                ipaddr = ips.groups()[0]
            if cts:
                csrftoken = cts.groups()[0]
            if css:
                csrfts = css.groups()[0]
            if crs:
                csrfrnd = crs.groups()[0]
            paramstuple = (urlid, sessid, ipaddr, csrftoken, csrfts, csrfrnd, devid, devtype, siteurl)
            if self.logging:
                self.logger.write("Amazon 'visual' url first request parameters:\n urlid: %s\nsession Id: %s\nipaddr: %s\ncsrftoken: %s\ncsrfts: %s\ncsrfrnd: %s\ndevid: %s\ndevtype: %s\n"%(urlid, sessid, ipaddr, csrftoken, csrfts, csrfrnd, devid, devtype))
            datadict = ambot.getvisualdict(paramstuple, "", 0)
            #print(datadict)
            episodeurls = []
            uniqueepisodes = {}
            episodeids = []
            episodepattern = re.compile("\/episodes\/([^\/]+)\/", re.DOTALL)
            try:
                content = datadict['methods'][0]['content']
                deeplinkpattern = re.compile("\"deeplink\"\:\"(\/podcasts\/[^\"]+)\",", re.DOTALL)
                matches = re.findall(deeplinkpattern, content)
                for m in matches:
                    if "episodes" not in m:
                        continue
                    epurl = "https://music.amazon.com" + m
                    if epurl not in uniqueepisodes.keys():
                        episodeurls.append(epurl)
                        uniqueepisodes[epurl] = 1
                        eps = re.search(episodepattern, epurl)
                        if eps:
                            episodeids.append(eps.groups()[0])
            except:
                print("Error in extracting episode links: %s"%sys.exc_info()[1].__str__())
                if self.logging:
                    self.logger.write("Error in extracting episode links: %s\n"%sys.exc_info()[1].__str__())
            ectr = 0
            mediaurlslist = []
            for eurl in episodeurls:
                if self.logging:
                    self.logger.write("Fetching Amazon episode URL: %s\n"%eurl)
                response = ambot.makehttprequest(eurl)
                #print(response.content)
                devtype, devid, favicon, mktplace, sessid, ipaddr, csrftoken, csrfts, csrfrnd = "", "", "", "", "", "", "", "", ""
                dts = re.search(devicetypepattern, str(response.content))
                dis = re.search(deviceidpattern, str(response.content))
                fis = re.search(faviconpattern, str(response.content))
                mks = re.search(marketplacepattern, str(response.content))
                sss = re.search(sessionidpattern, str(response.content))
                ips = re.search(ipaddresspattern, str(response.content))
                cts = re.search(csrftokenpattern, str(response.content))
                css = re.search(csrftspattern, str(response.content))
                crs = re.search(csrfrndpattern, str(response.content))
                if dts:
                    devtype = dts.groups()[0]
                if dis:
                    devid = dis.groups()[0]
                if fis:
                    favicon = fis.groups()[0]
                if mks:
                    mktplace = mks.groups()[0]
                if sss:
                    sessid = sss.groups()[0]
                if ips:
                    ipaddr = ips.groups()[0]
                if cts:
                    csrftoken = cts.groups()[0]
                if css:
                    csrfts = css.groups()[0]
                if crs:
                    csrfrnd = crs.groups()[0]
                params = (urlid, sessid, ipaddr, csrftoken, csrfts, csrfrnd, devid, devtype, eurl)
                mediaidpattern = re.compile("\"mediaId\"\:\"(https:\/\/[^\"]+)\",", re.DOTALL)
                mflag = 1
                if self.logging:
                    self.logger.write("Amazon 'visual' url second request parameters:\n urlid: %s\nsessid: %s\nipaddr: %s\ncsrftoken: %s\ncsrfts: %s\ncsrfrnd: %s\ndevid: %s\ndevtype: %s\n"%(urlid, sessid, ipaddr, csrftoken, csrfts, csrfrnd, devid, devtype))
                if self.humanize:
                    ht = getrandominterval(5)
                    time.sleep(ht)
                mediadict = ambot.getvisualdict(params, episodeids[ectr], mflag)
                try:
                    content = str(mediadict['methods'][0]['content'])
                    #print(content)
                    cps = re.search(mediaidpattern, content)
                    if cps:
                        mediaurl = cps.groups()[0]
                        if self.DEBUG:
                            print(mediaurl)
                        mediaurlslist.append(mediaurl)
                except:
                    print("Error in extracting Amazon media links: %s"%sys.exc_info()[1].__str__())
                    if self.logging:
                        self.logger.write("Error in extracting Amazon media links: %s\n"%sys.exc_info()[1].__str__())
                ectr += 1
            ctr = 0
            if self.logging:
                self.logger.write("Amazon media links: %s\n"%("\n".join(mediaurlslist),))
            while ctr < targetcount:
                if self.DEBUG:
                    print("AMAZON ITERATION #%s ======================="%ctr)
                if self.logging:
                    self.logger.write("AMAZON ITERATION #%s =======================\n"%ctr)
                for mediaurl in mediaurlslist:
                    ambot.httpheaders['Referer'] = "https://music.amazon.com/"
                    ambot.httpheaders['range'] = "bytes=0-"
                    ambot.httpheaders['sec-fetch-dest'] = "audio"
                    ambot.httpheaders['sec-fetch-mode'] = "no-cors"
                    ambot.httpheaders['sec-fetch-site'] = "cross-site"
                    ambot.httpheaders['Accept-Encoding'] = "identity;q=1, *;q=0"
                    ambot.httpheaders['Accept'] = "*/*"
                    if self.humanize:
                        ht = getrandominterval(5)
                        time.sleep(ht)
                    response = ambot.makehttprequest(mediaurl)
                    AMAZON_HIT_STAT += 1
                    curmessagecontent = self.msglabeltext.get()
                    replacementmessage = "AMAZON: %s"%AMAZON_HIT_STAT
                    curmessagecontent = statuspattern.sub(replacementmessage, curmessagecontent)
                    self.msglabeltext.set(curmessagecontent)
                    if self.logging:
                        self.logger.write("Fetched Amazon URL: %s\n"%mediaurl)
                    if self.DEBUG:
                        t = str(int(time.time() * 1000))
                        fa = open(self.dumpdir + os.path.sep + "amazon_%s.mp3"%t, "wb")
                        fa.write(response.content)
                        fa.close()
                    else:
                        pass
                ctr += 1
            # Check to see if self.podcasttitle exists in the retrieved content
            boolret = ambot.existsincontent(titleregex)
            if "amazon" in self.hitstatus.keys():
                self.hitstatus['amazon'].append(boolret)
            else:
                self.hitstatus['amazon'] = []
                self.hitstatus['amazon'].append(boolret)
            if self.logging:
                self.logger.write("Done hitting podcasts for %s\n"%sitename)
        else:
            boolret = False
        if self.cleanupmedia:
            self.cleanupdownloadedmedia()
        return boolret


    def __get__(self, instance, owner):
        self.parent = instance
        return self  # expose object to be able access msglabeltext.

    """
    Method to clean up downloaded media
    """
    def cleanupdownloadedmedia(self):
        try:
            shutil.rmtree(self.dumpdir)
        except OSError as e:
            print ("Error: %s - %s." % (e.filename, e.strerror))


"""
Class to implement basic logging
"""
class Logger(object):

    def __init__(self, logfile):
        self.logdir = os.path.dirname(logfile)
        self.logfilepath = logfile
        self.logfilename = os.path.basename(logfile)
        if not os.path.isdir(self.logdir):
            os.makedirs(self.logdir, 0o777)
        if os.path.exists(self.logfilepath):
            self.logger = open(self.logfilepath, "a")
        else:
            self.logger = open(self.logfilepath, "w")
        self.lastmessage = ""


    def write(self, message):
        self.lastmessage = message
        self.logger.write(message)


    def close(self):
        self.logger.close()


"""
Class implementing the user interface.
"""
class GUI(object):

    def __init__(self):
        self.emptystringpattern = re.compile("^\s*$")
        self.httppattern = re.compile("^https?", re.IGNORECASE)
        self.amazonkey = ""
        self.spotifyclientid = ""
        self.spotifyclientsecret = ""
        self.mainwin = Tk()
        self.valcmd = (self.mainwin.register(self.validate), '%d', '%i', '%P', '%s', '%S', '%v', '%V', '%W')

        self.proxylabel = Label(self.mainwin, text="Add (https) Proxies: ", width=25, justify=LEFT, relief=RAISED)
        self.proxylabel.grid(row=0, column=0, sticky=W)
        self.proxytext = ScrolledText(self.mainwin, bg="white", fg="blue", width=40, height=10)
        self.proxytext.grid(row=0, column=1, columnspan=3)

        self.separator = ttk.Separator(self.mainwin, orient=HORIZONTAL, style='TSeparator', class_= ttk.Separator)
        self.separator.grid(row=1, column=0, columnspan=4)

        self.amazonkeylabel = Label(self.mainwin, text="Amazon Key: ", width=25, justify=LEFT, relief=RAISED)
        self.amazonkeylabel.grid(row=2, column=0, sticky=W)
        self.amazonkeyentry = Entry(self.mainwin, width=40, borderwidth=1)
        self.amazonkeyentry.grid(row=2, column=1, columnspan=3)

        self.spotifyclientidlabel = Label(self.mainwin, text="Spotify Client ID: ", width=25, justify=LEFT, relief=RAISED)
        self.spotifyclientidlabel.grid(row=3, column=0, sticky=W)
        self.spotifyclientidentry = Entry(self.mainwin, width=40, borderwidth=1)
        self.spotifyclientidentry.grid(row=3, column=1, columnspan=3)
        self.spotifyclientsecretlabel = Label(self.mainwin, text="Spotify Client Secret: ", width=25, justify=LEFT, relief=RAISED)
        self.spotifyclientsecretlabel.grid(row=4, column=0, sticky=W)
        self.spotifyclientsecretentry = Entry(self.mainwin, width=40, borderwidth=1)
        self.spotifyclientsecretentry.grid(row=4, column=1, columnspan=3)

        self.targeturl = ""
        self.urllabeltext = StringVar()
        self.msglabeltext = StringVar()
        self.urllabel = Label(self.mainwin, textvariable=self.urllabeltext, width=25, justify=LEFT, relief=RAISED)
        self.urllabel.grid(row=5, column=0, sticky=W)
        self.urllabeltext.set("Enter Target URL: ")
        self.targeturlentry = Entry(self.mainwin, width=40, borderwidth=1)
        self.targeturlentry.grid(row=5, column=1, columnspan=3)
        self.targetcountamazonlbl = StringVar()
        self.targetcountamazonlabel = Label(self.mainwin, textvariable=self.targetcountamazonlbl, width=25, justify=LEFT, relief=RAISED)
        self.targetcountamazonlabel.grid(row=6, column=0, sticky=W)
        self.targetcountamazonlbl.set("Amazon Hits: ")
        #self.targetamazonhits = Entry(self.mainwin, width=40, borderwidth=1)
        self.defaultamazonhits = StringVar()
        self.defaultamazonhits.set(-1)
        self.targetamazonhits = ttk.Combobox(self.mainwin, textvariable=self.defaultamazonhits, values=[i for i in range(-1,1000)], validatecommand=self.valcmd)
        self.targetamazonhits.grid(row=6, column=1, columnspan=3)
        self.targetcountspotifylbl = StringVar()
        self.targetcountspotifylabel = Label(self.mainwin, textvariable=self.targetcountspotifylbl, width=25, justify=LEFT, relief=RAISED)
        self.targetcountspotifylabel.grid(row=7, column=0, sticky=W)
        self.targetcountspotifylbl.set("Spotify Hits: ")
        #self.targetspotifyhits = Entry(self.mainwin, width=40, borderwidth=1)
        self.defaultspotifyhits = StringVar()
        self.defaultspotifyhits.set(-1)
        self.targetspotifyhits = ttk.Combobox(self.mainwin, textvariable=self.defaultspotifyhits, values=[i for i in range(-1,1000)], validatecommand=self.valcmd)
        self.targetspotifyhits.grid(row=7, column=1, columnspan=3)
        self.targetcountapplelbl = StringVar()
        self.targetcountapplelabel = Label(self.mainwin, textvariable=self.targetcountapplelbl, width=25, justify=LEFT, relief=RAISED)
        self.targetcountapplelabel.grid(row=8, column=0, sticky=W)
        self.targetcountapplelbl.set("Apple Hits: ")
        #self.targetapplehits = Entry(self.mainwin, width=40, borderwidth=1)
        self.defaultapplehits = StringVar()
        self.defaultapplehits.set(-1)
        self.targetapplehits = ttk.Combobox(self.mainwin, textvariable=self.defaultapplehits, values=[i for i in range(-1,1000)], validatecommand=self.valcmd)
        self.targetapplehits.grid(row=8, column=1, columnspan=3)
        self.DEBUG_var = IntVar() # By default, we don't we don't want to see debug output
        self.DEBUG = False
        self.debugchkbtn = Checkbutton(self.mainwin, text = "Debug", variable = self.DEBUG_var, onvalue = 1, offvalue = 0, height=2, width = 10)
        self.debugchkbtn.grid(row=9, column=0)
        self.humanize_var = IntVar()
        self.humanize = False
        self.humanizechkbtn = Checkbutton(self.mainwin, text = "Humanize", variable = self.humanize_var, onvalue = 1, offvalue = 0, height=2, width = 10)
        self.humanizechkbtn.grid(row=9, column=1)
        self.humanizechkbtn.select() # By default, we will humanize
        self.logging_var = IntVar()
        self.logging = True
        self.logchkbtn = Checkbutton(self.mainwin, text = "Logging", variable = self.logging_var, onvalue = 1, offvalue = 0, height=2, width = 10)
        self.logchkbtn.grid(row=9, column=2)
        self.logchkbtn.select() # By default, we log the operation
        self.cleanupmedia_var = IntVar()
        self.cleanupmedia = True
        self.cleanupmediachkbtn = Checkbutton(self.mainwin, text = "Clean up", variable = self.cleanupmedia_var, onvalue = 1, offvalue = 0, height=2, width = 10)
        self.cleanupmediachkbtn.grid(row=9, column=3)
        self.cleanupmediachkbtn.select()
        self.runbutton = Button(self.mainwin, text="Start Bot", command=self.startbot)
        self.runbutton.grid(row=10, column=0)
        self.stopbutton = Button(self.mainwin, text="Stop Bot", command=self.stopbot)
        self.stopbutton.grid(row=10, column=1)
        self.closebutton = Button(self.mainwin, text="Close Window", command=self.closebot)
        self.closebutton.grid(row=10, column=2)
        self.messagelabel = Message(self.mainwin, textvariable=self.msglabeltext, bg="white", width=400, relief=SUNKEN)
        self.messagelabel.grid(row=11, columnspan=3)
        
        self.buzz = None
        self.threadslist = []
        self.rt = None
        self.proxieslist = []

        self.mainwin.mainloop()


    def validate(self, action, index, value_if_allowed, prior_value, text, validation_type, trigger_type, widget_name):
        if value_if_allowed:
            try:
                int(value_if_allowed)
                return True
            except ValueError:
                self.errbox = MessageBox(self.mainwin)
                self.errbox.showerror(message="Invalid value for hits")
                return False
        else:
            return False



    def startbot(self):
        self.targeturl = self.targeturlentry.get()
        if self.targeturl == "":
            self.messagelabel.configure(foreground="red", width=400)
            self.msglabeltext.set("Target URL cannot be empty")
            return False
        eps = re.search(self.emptystringpattern, self.targeturl)
        if eps:
            self.messagelabel.configure(foreground="red", width=400)
            self.msglabeltext.set("Target URL is not valid")
            return False
        hps = re.search(self.httppattern, self.targeturl)
        if not hps:
            self.messagelabel.configure(foreground="red", width=400)
            self.msglabeltext.set("Target URL is not valid")
            return False
        self.errmsg = ""
        self.amazonkey = self.amazonkeyentry.get()
        self.spotifyclientid = self.spotifyclientidentry.get()
        self.spotifyclientsecret = self.spotifyclientsecretentry.get()
        if self.amazonkey == "":
            try:
                self.amazonkey = os.environ["AMAZON_APIKEY"]
            except:
                self.errmsg = "\nCould not find Amazon API Key"
        if self.spotifyclientid == "":
            try:
                self.spotifyclientid = os.environ["SPOTIFY_CLIENTID"]
            except:
                self.errmsg = "\nCould not find Spotify Client ID"
        if self.spotifyclientsecret == "":
            try:
                self.spotifyclientsecret = os.environ["SPOTIFY_CLIENTSECRET"]
            except:
                self.errmsg = "\nCould not find Spotify Client Secret"
        if self.errmsg != "":
            self.messagelabel.configure(foreground="red", width=400)
            self.msglabeltext.set(self.errmsg)
            return False
        proxiestext = self.proxytext.get('1.0', 'end-1c')
        proxieslines = proxiestext.split("\n")
        self.proxieslist = []
        self.proxypattern = re.compile("^https\:\/\/\d+\.\d+\.\d+\.\d+\:\d+$", re.IGNORECASE)
        for line in proxieslines:
            if not re.search(self.proxypattern, line):
                continue
            self.proxieslist.append(line)
        amazontargethitscount = self.targetamazonhits.get()
        spotifytargethitscount = self.targetspotifyhits.get()
        appletargethitscount = self.targetapplehits.get()
        self.DEBUG = self.DEBUG_var.get()
        self.humanize = self.humanize_var.get()
        self.logging = self.logging_var.get()
        self.cleanupmedia = self.cleanupmedia_var.get()
        if self.DEBUG:
            print("%s ___ %s ____ %s"%(self.DEBUG, self.humanize, self.logging))
        # Start bot in a background thread...
        self.rt = Thread(target=self.runbot, args=(self.targeturl, amazontargethitscount, spotifytargethitscount, appletargethitscount))
        self.rt.daemon = True
        self.rt.start()
        self.messagelabel.configure(foreground="green", width=400)
        self.msglabeltext.set("Operation in progress...\nAPPLE: 0\nAMAZON: 0\nSPOTIFY: 0")
        # ... and return to user
        return True


    """
    A target count of -1 means the bot should run indefinitely hitting all targets until it is stopped
    (possibly by killing the process).
    """
    def runbot(self, targeturl, amazonsettarget=-1, spotifysettarget=-1, applesettarget=-1):
        self.buzz = BuzzBot(targeturl, self.amazonkey, self.spotifyclientid, self.spotifyclientsecret, self, self.proxieslist)
        self.buzz.DEBUG = self.DEBUG
        self.buzz.humanize = self.humanize
        self.buzz.logging = self.logging
        self.buzz.cleanupmedia = self.cleanupmedia
        self.buzz.settargetcounts(amazonsettarget, spotifysettarget, applesettarget)
        self.buzz.makerequest()
        self.buzz.gethttpresponsecontent()
        urlsdict = self.buzz.getpodcasturls()
        self.threadslist = []
        for sitename in urlsdict.keys():
            siteurl = urlsdict[sitename]
            targetcount = -1
            if sitename.lower() == "apple":
                targetcount = self.buzz.applesettarget
            if sitename.lower() == "amazon":
                targetcount = self.buzz.amazonsettarget
            if sitename.lower() == "spotify":
                targetcount = self.buzz.spotifysettarget
            t = Thread(target=self.buzz.hitpodcast, args=(siteurl, sitename, targetcount))
            t.daemon = True
            t.start()
            self.threadslist.append(t)
        time.sleep(2) # sleep 2 seconds.
        for tj in self.threadslist:
            tj.join()
        """
        for site in self.buzz.hitstatus.keys():
            if self.buzz.hitstatus[site].__len__() > 0:
                self.messagelabel.configure(foreground="green", width=400)
                self.msglabeltext.set("%s : %s"%(site, self.buzz.hitstatus[site][0]))
        """
        self.messagelabel.configure(foreground="blue", width=400)
        curmessagecontent = self.msglabeltext.get()
        curmessagecontent += "\n\nFinished hitting targets."
        self.msglabeltext.set(curmessagecontent)
        return True


    def closebot(self):
        if self.rt is not None:
            self.rt.join()
        if self.buzz is not None and self.buzz.logger is not None:
            self.buzz.logger.close()
        sys.exit()


    def stopbot(self):
        if self.rt is not None:
            self.rt.join()
        return None



# Entry point...
if __name__ == "__main__":
    gui = GUI()


"""
References:
https://github.com/ListenNotes/podcast-api-python
https://www.listennotes.com/podcast-api/docs/?test=1
https://music.amazon.com/podcasts/e934affd-05e2-48d5-8236-6b7f2d02e5e2
https://stackoverflow.com/questions/10791588/getting-container-parent-object-from-within-python

Developer: Supriyo Mitra
Date: 11-08-2022
"""


