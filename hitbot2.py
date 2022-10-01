import os, sys, re, time
from datetime import datetime
import random
import shutil

import subprocess
from threading import Thread
import signal

import socks
import socket
import ssl
import urllib, requests
from urllib.parse import urlencode, quote_plus, urlparse
from requests_html import HTMLSession
import ipaddress

import simplejson as json
from bs4 import BeautifulSoup
import numpy as np
import gzip
import io
import hashlib, base64
import weakref
import uuid
import pymysql as MySQLdb

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


# Module level globals: These variables represent the number of hits made on the service platforms at any instant during a run.
AMAZON_HIT_STAT = 0
APPLE_HIT_STAT = 0
SPOTIFY_HIT_STAT = 0
TIMEOUT_S = 60


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


def getrandomint(min_num, max_num):
    l = []
    for i in range(0,9):
        l.append(random.randint(min_num, max_num))
    r = random.choice(l)
    #print("RANDOM: %s"%r)
    return r

def getrandomalphabet():
    l = ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h', 'i', 'j', 'k', 'l', 'm', 'n', 'o', 'p', 'q', 'r', 's', 't', 'u', 'v', 'w', 'x', 'y', 'z']
    x = l[random.randint(0, 25)]
    y = l[random.randint(0, 25)]
    return [x,y]


def getrandomalphanumeric():
    l = ['0', '1', '2', '3', '4', '5','6', '7', '8', '9', 'a', 'b', 'c', 'd', 'e', 'f']
    a = l[random.randint(0, 15)]
    b = l[random.randint(0, 15)]
    return [a,b]


def ip4to6(ipaddr):
    prfx = "2401::"
    prefix6to4 = int(ipaddress.IPv6Address(prfx))
    try:
        ip4 = ipaddress.IPv4Address(ipaddr)
    except:
        return ipaddr # Couldn't convert, so returning the ip4 address
    ip6 = ipaddress.IPv6Address(prefix6to4 | (int(ip4) << 80))
    return ip6


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
        self.selectedproxy = ""
        self.selectedproxyport = "3128"
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
            self.httpresponse = self.httpopener.open(self.httprequest, timeout=TIMEOUT_S)
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
            httpsrandomctr = getrandomint(0, httpsproxycount-1)
            self.proxyhandler = urllib.request.ProxyHandler({'https': self.proxies['https'][httpsrandomctr],})
            self.httpopener = urllib.request.build_opener(urllib.request.HTTPHandler(), self.httpshandler, self.proxyhandler)
            proxparts = self.proxies['https'][httpsrandomctr].split("//")
            if proxparts.__len__() > 1:
                self.selectedproxy = proxparts[1].split(":")[0]
                self.selectedproxyport = proxparts[1].split(":")[1]
            else:
                self.selectedproxy = proxparts[0].split(":")[0]
                self.selectedproxyport = proxparts[0].split(":")[1]
            if self.DEBUG:
                print("Proxy used (Amazon): %s"%self.proxies['https'][httpsrandomctr])
        except:
            print("Error creating opener with proxy: %s"%sys.exc_info()[1].__str__())
            self.httpopener = urllib.request.build_opener(urllib.request.HTTPHandler(), self.httpshandler)
        return self.httpopener


    def makehttprequest(self, requrl):
        if requrl == '' or requrl is None:
            return None
        self.httpopener = self.buildopenerrandomproxy()
        self.httprequest = urllib.request.Request(requrl, headers=self.httpheaders)
        session = HTMLSession()
        if self.proxies['https'].__len__() > 0:
            httpsproxycount = self.proxies['https'].__len__() - 1
            httpsrandomctr = getrandomint(0, httpsproxycount-1)
            try:
                self.httpresponse = session.get(requrl, proxies={'https': self.proxies['https'][httpsrandomctr]}, timeout=TIMEOUT_S)
                if self.DEBUG:
                    print("Proxy used (Amazon): %s"%self.proxies['https'][httpsrandomctr])
            except:
                try:
                    self.httpresponse = session.get(requrl, timeout=TIMEOUT_S)
                except:
                    if self.DEBUG:
                        print("Request to '%s' failed: %s"%(requrl, sys.exc_info()[1].__str__()))
                    return None
        else:
            try:
                self.httpresponse = session.get(requrl, timeout=TIMEOUT_S)
            except:
                if self.DEBUG:
                    print("Request to '%s' failed: %s"%(requrl, sys.exc_info()[1].__str__()))
                return None
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
        content = str(self.httpcontent)
        if re.search(regexpattern, content):
            return True
        return False


    def getvisualdict(self, paramstuple, episodeid="", mediaflag=0, cookies=""):
        urlid, sessid, ipaddr, csrftoken, csrfts, csrfrnd, devid, devtype, siteurl = paramstuple[0], paramstuple[1], paramstuple[2], paramstuple[3], paramstuple[4], paramstuple[5], paramstuple[6], paramstuple[7], paramstuple[8]
        siteurlparts = siteurl.split("/")
        siteurl = "/" + "/".join(siteurlparts[3:])
        ts = int(time.time() * 1000)
        amzrequestid_seed = "707bcf7c-2fde-47e1-9244-0f8245e13d9"
        #amzrequestid_seed = "9bc04d79-b0b8-42dc-b9cb-e66189e84cdc"
        requestidentityid_seed = "0b7c4526-e110-4dc8-932b-42a21a707017"
        amzrequestid_list = list(amzrequestid_seed)
        for ri in range(amzrequestid_list.__len__()):
            amzrequestid_list[ri] = str(amzrequestid_list[ri])
        requestidentityid_list = list(requestidentityid_seed)
        for ir in range(requestidentityid_list.__len__()):
            requestidentityid_list[ir] = str(requestidentityid_list[ir])
        ablist = getrandomalphanumeric()
        randpos1 = random.randint(0, amzrequestid_list.__len__() - 1)
        randpos2 = random.randint(0, amzrequestid_list.__len__() - 1)
        if amzrequestid_list[randpos1] != "-":
            amzrequestid_list[randpos1] = ablist[0]
        if amzrequestid_list[randpos2] != "-":
            amzrequestid_list[randpos2] = ablist[1]
        amzrequestid = ''.join(amzrequestid_list)
        if requestidentityid_list[randpos1] != "-":
            requestidentityid_list[randpos1] = ablist[0]
        if requestidentityid_list[randpos2] != "-":
            requestidentityid_list[randpos2] = ablist[1]
        requestidentityid = ''.join(requestidentityid_list)
        httpheaders = {'accept' : '*/*', 'accept-encoding' : 'gzip,deflate', 'accept-language' : 'en-GB,en-US;q=0.9,en;q=0.8', 'cache-control' : 'no-cache', 'content-encoding' : 'amz-1.0', 'content-type' : 'application/json; charset=UTF-8', 'origin' : 'https://music.amazon.com', 'pragma' : 'no-cache', 'referer' : siteurl, 'sec-ch-ua' : '".Not/A)Brand";v="99", "Google Chrome";v="103", "Chromium";v="103"', 'sec-ch-ua-mobile' : '?0', 'sec-ch-ua-platform' : 'Linux', 'sec-fetch-dest' : 'empty', 'sec-fetch-mode' : 'cors', 'sec-fetch-site' : 'same-origin', 'user-agent' : 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/103.0.0.0 Safari/537.36', 'x-amz-target' : 'com.amazon.dmpbrowsevisualservice.skills.DMPBrowseVisualService.ShowPodcastWebSkill', 'x-amzn-requestid' : amzrequestid}
        httpheaders['cookie'] = ""
        httpheaders['cookie'] += self.httpheaders['cookie']
        self.httpopener = self.buildopenerrandomproxy()
        if mediaflag == 0:
            datadict = {"preset":"{\"id\":\"%s\",\"nextToken\":null}"%urlid,"identity":{"__type":"SOACoreInterface.v1_0#Identity","application":{"__type":"SOACoreInterface.v1_0#ApplicationIdentity","version":"2.1"},"user":{"__type":"SOACoreInterface.v1_0#UserIdentity","authentication":""},"request":{"__type":"SOACoreInterface.v1_0#RequestIdentity","id":"","sessionId":"%s"%sessid,"ipAddress":"%s"%ipaddr,"timestamp":ts,"domain":"music.amazon.com","csrf":{"__type":"SOACoreInterface.v1_0#Csrf","token":"%s"%csrftoken,"ts":"%s"%csrfts,"rnd":"%s"%csrfrnd}},"device":{"__type":"SOACoreInterface.v1_0#DeviceIdentity","id":"%s"%devid,"typeId":"%s"%devtype,"model":"WEBPLAYER","timeZone":"Asia/Calcutta","language":"en_US","height":"668","width":"738","osVersion":"n/a","manufacturer":"n/a"}},"clientStates":{"deeplink":{"url":"%s"%siteurl,"__type":"Podcast.DeeplinkInterface.v1_0#DeeplinkClientState"},"hidePromptPreference":{"preferenceMap":{},"__type":"Podcast.FollowPromptInterface.v1_0#HidePromptPreferenceClientState"}},"extra":{}}
        else:
            httpheaders['x-amz-target'] = "com.amazon.dmpplaybackvisualservice.skills.DMPPlaybackVisualService.PlayPodcastWebSkill"
            datadict = {"preset":"{\"podcastId\":\"%s\",\"startAtEpisodeId\":\"%s\"}"%(urlid, episodeid),"identity":{"__type":"SOACoreInterface.v1_0#Identity","application":{"__type":"SOACoreInterface.v1_0#ApplicationIdentity","version":"2.1"},"user":{"__type":"SOACoreInterface.v1_0#UserIdentity","authentication":""},"request":{"__type":"SOACoreInterface.v1_0#RequestIdentity","id":"%s"%requestidentityid,"sessionId":"%s"%sessid,"ipAddress":"%s"%ipaddr,"timestamp":ts,"domain":"music.amazon.com","csrf":{"__type":"SOACoreInterface.v1_0#Csrf","token":"%s"%csrftoken,"ts":"%s"%csrfts,"rnd":"%s"%csrfrnd}},"device":{"__type":"SOACoreInterface.v1_0#DeviceIdentity","id":"%s"%devid,"typeId":"%s"%devtype,"model":"WEBPLAYER","timeZone":"Asia/Calcutta","language":"en_US","height":"668","width":"738","osVersion":"n/a","manufacturer":"n/a"}},"clientStates":{"deeplink":{"url":"%s"%siteurl,"__type":"Podcast.DeeplinkInterface.v1_0#DeeplinkClientState"}}, "extra":{}}        
        postdata = json.dumps(datadict).encode('utf-8')
        #seedsesstoken = "RLu67mQaxSowz1izN2xQADeJFmrvbiQvS8PTT2ZSXHiI9FcI6A7iId+bx4TKlkzUZctsaUpNVzGEikeX4V0Q4G6rXHS6WcnBHdPXCK/KZo2c2CVGJPmrUycxEYVUmrUwKC37Xy5QeqJVuqSOvWc6n4YZ1wIEl3+ln4aeM0MzKsM1HwPsYW+mkf6WXsXpTA2e"
        seedsesstoken = "0LqsflkijLJIl8OjucajXcCdNbcTOHKzHWMFKeWrPacUkgV5iFfeGwJw+RFnHGgtZhpbhVU0m9XCEBrXslFDjPf0yvSxFLYSBhwoXYDXtFrALKaNvTSGF5jSsPaIeMdgqmbh+BxyjdotsFCiW7+5p7kaVz7jcR2Piu1hDrwx8eJsSTu27nx0Zjm8uW7VqH0e"
        sesslist = list(seedsesstoken)
        xylist = getrandomalphabet()
        randpos1 = random.randint(0, sesslist.__len__() - 1)
        randpos2 = random.randint(0, sesslist.__len__() - 1)
        sesslist[randpos1] = xylist[0]
        sesslist[randpos2] = xylist[1]
        sesstoken = ''.join(sesslist)
        # Cookies should not be repeated.
        sesstokenpattern = re.compile("session\-token=[^;]+;", re.DOTALL)
        ubidmainpattern = re.compile("ubid\-main=\d+\-\d+\-\d+;", re.DOTALL)
        sessidpattern = re.compile("session\-id=[^;]+;", re.DOTALL)
        sessidtimepattern = re.compile("session\-id\-time=[^;]+l;", re.DOTALL)
        cookies = sesstokenpattern.sub("", cookies)
        cookies = ubidmainpattern.sub("", cookies, 1)
        cookies = sessidpattern.sub("", cookies, 1)
        cookies = sessidtimepattern.sub("", cookies, 1)
        httpheaders['cookie'] = cookies + "session-token=" + sesstoken + ";"
        datetzpattern = re.compile("\d{2}\-[a-zA-Z]{3}\-\d{4}\s+\d{2}\:\d{2}\:\d{2}\s+GMT\s*;", re.IGNORECASE|re.DOTALL)
        httpheaders['cookie'] = datetzpattern.sub("", httpheaders['cookie'])
        self.httpcookies = httpheaders['cookie']
        #print(httpheaders['cookie'])
        httpheaders['content-length'] = postdata.__len__()
        requrl = "https://music.amazon.com/EU/api/podcast/browse/visual"
        if mediaflag == 0:
            self.httprequest = urllib.request.Request(requrl, data=postdata, headers=httpheaders)
        else:
            requrl = "https://music.amazon.com/EU/api/podcast/playback/visual"
            self.httprequest = urllib.request.Request(requrl, data=postdata, headers=httpheaders)
        try:
            self.httpresponse = self.httpopener.open(self.httprequest, timeout=TIMEOUT_S)
        except:
            print("Error making request to %s: %s"%(requrl, sys.exc_info()[1].__str__()))
            return {}
        returndata = "{}"
        try:
            returndata = _decodeGzippedContent(self.httpresponse.read())
        except:
            print("Couldn't get content from visual URL - Error: %s"%sys.exc_info()[1].__str__())
        try:
            returndict = json.loads(returndata.encode('utf-8'))
        except:
            print("Error loading json data: %s"%(sys.exc_info()[1].__str__()))
            returndict = {}
        return returndict


    def playbackstartedvisual(self, paramstuple, episodemp3, episodeid):
        urlid, sessid, ipaddr, csrftoken, csrfts, csrfrnd, devid, devtype, siteurl = paramstuple[0], paramstuple[1], paramstuple[2], paramstuple[3], paramstuple[4], paramstuple[5], paramstuple[6], paramstuple[7], paramstuple[8]
        siteurlparts = siteurl.split("/")
        siteurl = "/" + "/".join(siteurlparts[3:])
        ts = int(time.time() * 1000)
        amzrequestid_seed = "707bcf7c-2fde-47e1-9244-0f8245e13d9"
        #amzrequestid_seed = "9bc04d79-b0b8-42dc-b9cb-e66189e84cdc"
        requestidentityid_seed = "0b7c4526-e110-4dc8-932b-42a21a707017"
        amzrequestid_list = list(amzrequestid_seed)
        for ri in range(amzrequestid_list.__len__()):
            amzrequestid_list[ri] = str(amzrequestid_list[ri])
        requestidentityid_list = list(requestidentityid_seed)
        for ir in range(requestidentityid_list.__len__()):
            requestidentityid_list[ir] = str(requestidentityid_list[ir])
        ablist = getrandomalphanumeric()
        randpos1 = random.randint(0, amzrequestid_list.__len__() - 1)
        randpos2 = random.randint(0, amzrequestid_list.__len__() - 1)
        if amzrequestid_list[randpos1] != "-":
            amzrequestid_list[randpos1] = ablist[0]
        if amzrequestid_list[randpos2] != "-":
            amzrequestid_list[randpos2] = ablist[1]
        amzrequestid = ''.join(amzrequestid_list)
        if requestidentityid_list[randpos1] != "-":
            requestidentityid_list[randpos1] = ablist[0]
        if requestidentityid_list[randpos2] != "-":
            requestidentityid_list[randpos2] = ablist[1]
        requestidentityid = ''.join(requestidentityid_list)
        httpheaders = {'accept' : '*/*', 'accept-encoding' : 'gzip,deflate', 'accept-language' : 'en-GB,en-US;q=0.9,en;q=0.8', 'cache-control' : 'no-cache', 'content-encoding' : 'amz-1.0', 'content-type' : 'application/json; charset=UTF-8', 'origin' : 'https://music.amazon.com', 'pragma' : 'no-cache', 'referer' : siteurl, 'sec-ch-ua' : '".Not/A)Brand";v="99", "Google Chrome";v="103", "Chromium";v="103"', 'sec-ch-ua-mobile' : '?0', 'sec-ch-ua-platform' : 'Linux', 'sec-fetch-dest' : 'empty', 'sec-fetch-mode' : 'cors', 'sec-fetch-site' : 'same-origin', 'user-agent' : 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/103.0.0.0 Safari/537.36', 'x-amzn-requestid' : amzrequestid}
        httpheaders['x-amz-target'] = "com.amazon.dmpplaybackvisualservice.skills.DMPPlaybackVisualService.ReportPlaybackMetricOperationsWebSkill"
        t = int(time.time() * 1000)
        pbrequested = t - 875467
        pbstarted = t - 871522
        updatedtime = t - 871508
        #opsid_seed = "8aa0b51c-7426-4957-9e1e-27b81b8249f0"
        opsid_seed = "bbd8d367-bcbc-4220-8344-6a442ebd2e6e"
        opsid_list = list(opsid_seed)
        for o in range(len(opsid_list)):
            opsid_list[o] = str(opsid_list[o])
        ablist = getrandomalphanumeric()
        randpos1 = random.randint(0, opsid_list.__len__() - 1)
        randpos2 = random.randint(0, opsid_list.__len__() - 1)
        if opsid_list[randpos1] != "-":
            opsid_list[randpos1] = ablist[0]
        if opsid_list[randpos2] != "-":
            opsid_list[randpos2] = ablist[1]
        opsid = ''.join(opsid_list)
        playbackmetric = {"operations":[{"id":"%s"%opsid,"element":{"id":"%s"%episodeid,"mediaCollectionType":"PODCAST","playbackSignalType":"PLAYBACK_STARTED","currentProgressMilliseconds":0,"playbackRequestedAtTimestampMilliseconds":pbrequested,"metricsPreset":"","isMediaDownloaded":False,"currentPlaybackSpeed":1,"playbackStartOffsetMilliseconds":0,"playbackStartedAtTimestampMilliseconds":pbstarted,"initialPlaybackStartDelayMilliseconds":3945,"rebufferDurationMilliseconds":0,"rebufferCount":0,"pageType":"","audioUri":"%s"%episodemp3,"podcastShowVariantId":"","podcastEpisodeVariantId":"","__type":"Podcast.PlaybackMetricsInterface.v1_0#PlaybackMetricWriteElement","interface":"Podcast.Web.PlaybackMetricsInterface.PlaybackMetricWriteElement"},"condition":{"updatedTime":updatedtime,"__type":"SOAAppSyncInterface.v1_0#TimeConditionElement"},"__type":"SOAAppSyncInterface.v1_0#OperationElement"}],"__type":"Podcast.PlaybackMetricsInterface.v1_0#PlaybackMetricsOperationsClientState"}
        datadict = {"preset":"{\"podcastId\":\"%s\",\"startAtEpisodeId\":\"%s\"}"%(urlid, episodeid),"identity":{"__type":"SOACoreInterface.v1_0#Identity","application":{"__type":"SOACoreInterface.v1_0#ApplicationIdentity","version":"2.1"},"user":{"__type":"SOACoreInterface.v1_0#UserIdentity","authentication":""},"request":{"__type":"SOACoreInterface.v1_0#RequestIdentity","id":"%s"%requestidentityid,"sessionId":"%s"%sessid,"ipAddress":"%s"%ipaddr,"timestamp":ts,"domain":"music.amazon.com","csrf":{"__type":"SOACoreInterface.v1_0#Csrf","token":"%s"%csrftoken,"ts":"%s"%csrfts,"rnd":"%s"%csrfrnd}},"device":{"__type":"SOACoreInterface.v1_0#DeviceIdentity","id":"%s"%devid,"typeId":"%s"%devtype,"model":"WEBPLAYER","timeZone":"Asia/Calcutta","language":"en_US","height":"668","width":"797","osVersion":"n/a","manufacturer":"n/a"}},"clientStates":{"deeplink":{"url":"%s"%siteurl,"__type":"Podcast.DeeplinkInterface.v1_0#DeeplinkClientState"}}, "playbackMetric" : playbackmetric, "extra":{}}       
        postdata = json.dumps(datadict).encode('utf-8')
        httpheaders['cookie'] = self.httpcookies
        httpheaders['content-length'] = postdata.__len__()
        requrl = "https://music.amazon.com/NA/api/podcast/playback/visual"
        self.httpopener = self.buildopenerrandomproxy()
        self.httprequest = urllib.request.Request(requrl, data=postdata, headers=httpheaders)
        try:
            self.httpresponse = self.httpopener.open(self.httprequest, timeout=TIMEOUT_S)
            print("Successfully made request to Amazon playback URL")
        except:
            print("Error making request to %s: %s"%(requrl, sys.exc_info()[1].__str__()))
            return {}
        returndata = "{}"
        try:
            returndata = _decodeGzippedContent(self.httpresponse.read())
        except:
            print("Could not get content from amazon playback URL - Error: %s"%sys.exc_info()[1].__str__())
        try:
            returndict = json.loads(returndata.encode('utf-8'))
        except:
            print("Error loading json data: %s"%(sys.exc_info()[1].__str__()))
            returndict = {}
        return returndict


    def getpandatoken(self, devicetype, epurl, cookies):
        pandaurl = "https://music.amazon.com/horizonte/pandaToken?deviceType=%s"%devicetype
        httpheaders = {'accept' : '*/*', 'accept-encoding' : 'gzip,deflate', 'accept-language' : 'en-GB,en-US;q=0.9,en;q=0.8', 'cache-control' : 'no-cache', 'pragma' : 'no-cache', 'referer' : epurl, 'sec-ch-ua' : '".Not/A)Brand";v="99", "Google Chrome";v="103", "Chromium";v="103"', 'sec-ch-ua-mobile' : '?0', 'sec-ch-ua-platform' : 'Linux', 'sec-fetch-dest' : 'empty', 'sec-fetch-mode' : 'cors', 'sec-fetch-site' : 'same-origin', 'user-agent' : 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/103.0.0.0 Safari/537.36'}
        #seedsesstoken = "SLu67mQaxSowz1izN2xQADeJFmrvbiQvS8PTT2ZSXHiI9FcI6A7iId+bx4TKlkzUZctsaUpNVzGEikeX4V0Q4G6rXHS6WcnBHdPXCK/KZo2c2CVGJPmrUycxEYVUmrUwKC37Xy5QeqJVuqSOvWc6n4YZ1wIEl3+ln4aeM0MzKsM1HwPsYW+mkf6WXsXpTA2f"
        seedsesstoken = "0LqsflkijLJIl8OjucajXcCdNbcTOHKzHWMFKeWrPacUkgV5iFfeGwJw+RFnHGgtZhpbhVU0m9XCEBrXslFDjPf0yvSxFLYSBhwoXYDXtFrALKaNvTSGF5jSsPaIeMdgqmbh+BxyjdotsFCiW7+5p7kaVz7jcR2Piu1hDrwx8eJsSTu27nx0Zjm8uW7VqH0e"
        sesslist = list(seedsesstoken)
        xylist = getrandomalphabet()
        randpos1 = random.randint(0, sesslist.__len__() - 1)
        randpos2 = random.randint(0, sesslist.__len__() - 1)
        sesslist[randpos1] = xylist[0]
        sesslist[randpos2] = xylist[1]
        sesstoken = ''.join(sesslist)
        httpheaders['cookie'] = cookies + "at_check=true; AMCVS_4A8581745834114C0A495E2B%40AdobeOrg=1; _mkto_trk=id:365-EFI-026&token:_mch-amazon.com-1661573838751-32752; mbox=session#47a708d83a684d8d9abc1df36d931572#1661575787|PC#47a708d83a684d8d9abc1df36d931572.31_0#1724818727; s_nr=1661573929087-New; s_lv=1661573929088; aws-mkto-trk=id%3A112-TZM-766%26token%3A_mch-aws.amazon.com-1657275509942-54640; aws_lang=en; s_campaign=ps%7C32f4fbd0-ffda-4695-a60c-8857fab7d0dd; aws-target-data=%7B%22support%22%3A%221%22%7D; s_eVar60=32f4fbd0-ffda-4695-a60c-8857fab7d0dd; aws-target-visitor-id=1662458172618-844632.31_0; awsc-color-theme=light; awsc-uh-opt-in=optedOut; noflush_awsccs_sid=2fa6f329955100ea8c9656162961f228b20b18c1e8c9abcb29a498d31f709f17; AMCV_7742037254C95E840A4C98A6%40AdobeOrg=1585540135%7CMCIDTS%7C19243%7CMCMID%7C86123343969842436782305730671676825045%7CMCAAMLH-1663176902%7C12%7CMCAAMB-1663176902%7CRKhpRz8krg2tLO6pguXWp5olkAcUniQYPHaMWWgdJ3xzPWQmdj0y%7CMCOPTOUT-1662579302s%7CNONE%7CMCAID%7CNONE%7CMCSYNCSOP%7C411-19248%7CvVersion%7C4.4.0; s_sq=%5B%5BB%5D%5D; session-token=" + sesstoken + ";"
        beginspacepattern = re.compile("^\s+")
        domainpattern = re.compile("Domain", re.IGNORECASE)
        expirespattern = re.compile("Expires", re.IGNORECASE)
        pathpattern = re.compile("Path", re.IGNORECASE)
        cookiestr = ""
        try:
            response = requests.get(pandaurl, headers=httpheaders, timeout=TIMEOUT_S)
            cookieslist = response.headers['set-cookie'].split(",")
            for c in cookieslist:
                cparts = c.split(";")
                for cp in cparts:
                    cp = str(cp)
                    cp = beginspacepattern.sub("", cp)
                    if re.search(domainpattern, cp) or re.search(expirespattern, cp) or re.search(pathpattern, cp):
                        continue
                    else:
                        cookiestr += str(cp) + ";"
        except:
            cookiestr = ""
            print("Error in getpandatoken: %s"%sys.exc_info()[1].__str__())
        #print(cookiestr)
        return cookiestr


    def clearmusicqueuerequest(self, csrftoken, csrfts, deviceid, episodeurl, rnd, sessid, podcastdomain):
        ts = int(time.time() * 1000)
        amzreqid_seed = "5d365441-7cb5-408f-ac6b-4d30ec8eb5c1"
        amzreqid_list = list(amzreqid_seed)
        ablist = getrandomalphanumeric()
        randpos1 = random.randint(0, amzreqid_list.__len__() - 1)
        randpos2 = random.randint(0, amzreqid_list.__len__() - 1)
        if amzreqid_list[randpos1] == "-":
            randpos1 += 1
        if amzreqid_list[randpos2] == "-":
            randpos2 += 1
        amzreqid_list[randpos1] = ablist[0]
        amzreqid_list[randpos2] = ablist[1]
        amzreqid = ''.join(amzreqid_list)
        httpheaders = {'accept' : '*/*', 'accept-encoding' : 'gzip,deflate', 'accept-language' : 'en-GB,en-US;q=0.9,en;q=0.8', 'cache-control' : 'no-cache', 'pragma' : 'no-cache', 'referer' : 'https://music.amazon.com/', 'origin' : 'https://music.amazon.com', 'sec-ch-ua' : '".Not/A)Brand";v="99", "Google Chrome";v="103", "Chromium";v="103"', 'sec-ch-ua-mobile' : '?0', 'sec-ch-ua-platform' : 'Linux', 'sec-fetch-dest' : 'empty', 'sec-fetch-mode' : 'cors', 'sec-fetch-site' : 'cross-site', 'user-agent' : 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/103.0.0.0 Safari/537.36', 'content-type' : 'text/plain;charset=UTF-8', 'content-length' : '2', 'x-amzn-affiliate-tags' : '', 'x-amzn-application-version' : '1.0.10995.0', 'x-amzn-authentication' : '{"interface":"ClientAuthenticationInterface.v1_0.ClientTokenElement","accessToken":""}', 'x-amzn-csrf' : '{"interface":"CSRFInterface.v1_0.CSRFHeaderElement","token":"%s","timestamp":"%s","rndNonce":"%s"}'%(csrftoken, csrfts, rnd), 'x-amzn-currency-of-preference' : 'USD', 'x-amzn-device-family' : 'WebPlayer', 'x-amzn-device-height' : '1080', 'x-amzn-device-id' : deviceid, 'x-amzn-device-language' : 'en-US', 'x-amzn-device-model' : 'WEBPLAYER', 'x-amzn-device-time-zone' : 'Asia/Calcutta', 'x-amzn-device-width' : '1920', 'x-amzn-feature-flags' : '', 'x-amzn-music-domain' : 'music.amazon.com', 'x-amzn-os-version' : '1.0', 'x-amzn-page-url' : episodeurl, 'x-amzn-ref-marker' : '', 'x-amzn-referer' : podcastdomain, 'x-amzn-request-id' : '%s'%amzreqid, 'x-amzn-session-id' : sessid, 'x-amzn-timestamp' : ts, 'x-amzn-user-agent' : 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/103.0.0.0 Safari/537.36', 'x-amzn-video-player-token' : '', 'x-amzn-weblab-id-overrides' : ''}
        requesturl = 'https://na.mesk.skill.music.a2z.com/api/clearMusicQueue'
        amzopener = self.buildopenerrandomproxy()
        payload = b"{}"
        amzrequest = urllib.request.Request(requesturl, data=payload, headers=httpheaders)
        try:
            amzresponse = amzopener.open(amzrequest, timeout=TIMEOUT_S)
        except:
            amzresponse = None
            print("clearmusicqueue request failed: %s"%sys.exc_info()[1].__str__())
        # We don't expect any meaningful data from this request. This is simply to make our masquerade look genuine
        if amzresponse is not None:
            print("Successfully made clearmusicqueue request")
        else:
            print("clearmusicqueue request failed. See error above.")
        return None


class SpotifyBot(object):
    
    def __init__(self, client_id, client_secret, proxies):
        self.DEBUG = False
        self.humanize = True
        self.logging = True
        self.clientid = client_id
        self.clientsecret = client_secret
        self.redirecturi = "https://localhost:8000/"
        self.playlistid = ""
        self.ispodcast = True
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
            self.httpresponse = self.httpopener.open(self.httprequest, timeout=TIMEOUT_S)
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
        self.httpheaders['cookie'] = "sss=1; sp_ab=%7B%222019_04_premium_menu%22%3A%22control%22%7D; spot=%7B%22t%22%3A1660164332%2C%22m%22%3A%22in-en%22%2C%22p%22%3Anull%7D;_sctr=1|1660156200000; OptanonAlertBoxClosed=2022-09-19T21:28:38.589Z; ki_r=; ki_t=1663622222898%3B1663943862664%3B1663967345225%3B4%3B31;OptanonConsent=isIABGlobal=false&datestamp=" + day + "+" + mon + "+" + str(dd) + "+" + str(year) + "+" + str(hh) + "%3A" + str(mm) + "%3A" + str(ss) + "+GMT%2B0530+(India+Standard+Time)&version=6.26.0&hosts=&landingPath=NotLandingPage&groups=s00%3A1%2Cf00%3A1%2Cm00%3A1%2Ct00%3A1%2Ci00%3A1%2Cf02%3A1%2Cm02%3A1%2Ct02%3A1&AwaitingReconsent=false&geolocation=IN%3BDL; " + self.httpcookies
        #self.httpheaders['cookie'] = "sss=1; sp_adid=dab9886a-26b8-426c-b587-4deafa6317d6; sp_m=in-en; _gcl_au=1.1.769434751.1660164171; _cs_c=0; _scid=357dc4b2-eaa2-47c7-9f9a-9e2cbe9b7d5a; _fbp=fb.1.1660164171920.249213084; _sctr=1|1660156200000; OptanonAlertBoxClosed=2022-08-10T20:43:54.163Z; sp_phash=a2c17ae575b28126b4c5aa2b5fd872d2d196352e; sp_gaid=0088fcade00809beb262d750ca91434142a10eb4a69cbdff9c7404; spot=%7B%22t%22%3A1660164332%2C%22m%22%3A%22in-en%22%2C%22p%22%3Anull%7D; sp_t=a2f20bfc3a23619df074952c61af1c0f; sp_last_utm=%7B%22utm_campaign%22%3A%22your_account%22%2C%22utm_medium%22%3A%22menu%22%2C%22utm_source%22%3A%22spotify%22%7D; _cs_id=2e855292-0381-a776-8bb4-d86b89592613.1660164171.2.1660415644.1660415644.1.1694328171610; _ga_S35RN5WNT2=GS1.1.1660415644.2.1.1660415662.42; sss=1; sp_landing=https%3A%2F%2Fopen.spotify.com%2Fservice-worker.js.map%3Fsp_cid%3Da2f20bfc3a23619df074952c61af1c0f%26device%3Ddesktop; _gid=GA1.2.1290307347.1663020057; _ga_ZWG1NSHWD8=GS1.1.1663020057.27.0.1663020057.0.0.0; OptanonConsent=isIABGlobal=false&datestamp=Tue+Sep+13+2022+03%3A30%3A57+GMT%2B0530+(India+Standard+Time)&version=6.26.0&hosts=&landingPath=NotLandingPage&groups=s00%3A1%2Cf00%3A1%2Cm00%3A1%2Ct00%3A1%2Ci00%3A1%2Cf02%3A1%2Cm02%3A1%2Ct02%3A1&AwaitingReconsent=false&geolocation=IN%3BDL; ki_t=1660164170739%3B1663020058642%3B1663020058642%3B13%3B42; ki_r=; _ga=GA1.2.190256731.1660163979"
        if self.DEBUG:
            print("Cookie Sent: %s"%self.httpheaders['cookie'])
        

    def buildopenerrandomproxy(self):
        httpsproxycount = self.proxies['https'].__len__() - 1
        self.context = createrequestcontext()
        self.httpshandler = urllib.request.HTTPSHandler(context=self.context)
        try:
            httpsrandomctr = getrandomint(0, httpsproxycount-1)
            self.proxyhandler = urllib.request.ProxyHandler({'https': self.proxies['https'][httpsrandomctr],})
            self.httpopener = urllib.request.build_opener(urllib.request.HTTPHandler(), self.httpshandler, self.proxyhandler)
            if self.DEBUG:
                print("Proxy used (Spotify): %s"%self.proxies['https'][httpsrandomctr])
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
        if requrl == '' or requrl is None:
            return None
        self.httpopener = self.buildopenerrandomproxy()
        if headers is None:
            headers = self.httpheaders
        self.httprequest = urllib.request.Request(requrl, headers=headers)
        self.httpresponse = None
        try:
            self.httpresponse = self.httpopener.open(self.httprequest, timeout=TIMEOUT_S)
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
        if re.search(regexpattern, content):
            return True
        return False


    def gettrackcontent(self, episodeid, accesstoken, clienttoken, dumpdir):
        tstr = str(int(time.time() * 1000))
        temptrackjs = "temp_sp_track_%s.js"%tstr
        fj = open("sp_track.js", "r")
        jscontent = fj.read()
        fj.close()
        jspattern = re.compile("####TRACK_ID####", re.DOTALL)
        trackjscontent = jspattern.sub(episodeid, jscontent)
        fj = open(temptrackjs, "w")
        fj.write(trackjscontent)
        fj.close()
        os.chown(temptrackjs, os.geteuid(), os.getegid())
        os.chmod(temptrackjs, 0o755)
        cmd = "./%s %s"%(temptrackjs, episodeid)
        outstr = subprocess.check_output(cmd, shell=True)
        outstr = str(outstr).replace("\\n", "").replace("\\r", "")
        outstr = outstr.replace("b'", "").replace("'", "")
        # Remove the temporary track js file 
        os.unlink(temptrackjs)
        requesturl = "https://spclient.wg.spotify.com/metadata/4/track/%s?market=from_token"%outstr
        httpheaders = { 'User-Agent' : r'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/88.0.4324.150 Safari/537.36',  'Accept' : 'application/json', 'Accept-Language' : 'en', 'Referer' : 'https://open.spotify.com/', 'sec-ch-ua-platform' : 'Linux', 'sec-ch-ua-mobile' : '?0', 'sec-ch-ua' : '".Not/A)Brand";v="99", "Google Chrome";v="103", "Chromium";v="103"', 'Authorization' : "Bearer %s"%accesstoken, 'client-token' : clienttoken, 'app-platform' : 'WebPlayer'}
        httpheaders['spotify-app-version'] = "1.1.95.750.g9444fb59"
        epinforequest = urllib.request.Request(requesturl, headers=httpheaders)
        if self.DEBUG:
            print("Requesting Track metadata from %s"%requesturl)
        try:
            self.httpresponse = self.httpopener.open(epinforequest, timeout=TIMEOUT_S)
        except:
            print("Error making episode info request to %s: %s"%(requesturl, sys.exc_info()[1].__str__()))
            return None
        self.httpcontent = "{}"
        try:
            self.httpcontent = _decodeGzippedContent(self.httpresponse.read())
        except:
            print("Could not read content from episode info request - Error: %s"%sys.exc_info()[1].__str__())
        audioduration = 0
        try:
            jsondata = json.loads(self.httpcontent)
            fileslist = jsondata['file']
            audioduration = int(jsondata['duration'])
        except:
            print("Could not find json content from response to track metadata request: %s"%sys.exc_info()[1].__str__())
            return None
        audiosize = audioduration/1000 * 44100/8 # 44100 bits/sec bitrate for 'audioduration' millisecs.
        if self.DEBUG:
            print("Track metadata request from %s successful."%requesturl)
            print("Audio size: %s"%str(audiosize))
        fid = ""
        for f in fileslist:
            if f['format'] == "MP4_128":
                fid = f['file_id']
        if fid == "":
            for f in fileslist:
                if f['format'] == "MP4_128_DUAL":
                    fid = f['file_id']
        if fid == "":
            for f in fileslist:
                if f['format'] == "MP4_256":
                    fid = f['file_id']
        if self.DEBUG:
            print("FILE ID: %s"%fid)
        requesturl = "https://gae2-spclient.spotify.com/storage-resolve/v2/files/audio/interactive/10/%s?version=10000000&product=9&platform=39&alt=json"%fid
        httpheaders = { 'User-Agent' : r'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/88.0.4324.150 Safari/537.36',  'Accept' : '*/*', 'Accept-Language' : 'en-GB,en-US;q=0.9,en;q=0.8', 'Accept-Encoding' : 'gzip,deflate', 'Cache-control' : 'no-cache', 'Connection' : 'keep-alive', 'Pragma' : 'no-cache', 'Referer' : 'https://open.spotify.com/', 'Sec-Fetch-Site' : 'same-site', 'Sec-Fetch-Mode' : 'cors', 'Sec-Fetch-Dest' : 'empty', 'sec-ch-ua-platform' : 'Linux', 'sec-ch-ua-mobile' : '?0', 'sec-ch-ua' : '".Not/A)Brand";v="99", "Google Chrome";v="103", "Chromium";v="103"', 'Origin' : 'https://open.spotify.com', 'Authorization' : "Bearer %s"%accesstoken, 'client-token' : clienttoken}
        trackinforequest = urllib.request.Request(requesturl, headers=httpheaders)
        if self.DEBUG:
            print("Making track media URL request from %s"%requesturl)
        try:
            self.httpresponse = self.httpopener.open(trackinforequest, timeout=TIMEOUT_S)
        except:
            print("Error making track info request to %s: %s"%(requesturl, sys.exc_info()[1].__str__()))
            return None
        self.httpcontent = "{}"
        try:
            self.httpcontent = _decodeGzippedContent(self.httpresponse.read())
        except:
            print("Could not get data containing cdnurl - Error: %s"%sys.exc_info()[1].__str__())
        cdnurl = ""
        try:
            jsondata = json.loads(self.httpcontent)
            cdnurl = jsondata['cdnurl'][0]
        except:
            print("Could not get json data from track info request")
            return None
        # We do have the CDN URL now, but we still need to send a request to 'https://gae2-spclient.spotify.com/melody/v1/msg/batch'
        batchurl = "https://gae2-spclient.spotify.com/melody/v1/msg/batch"
        batchheaders = { 'User-Agent' : r'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/88.0.4324.150 Safari/537.36',  'Accept' : '*/*', 'Accept-Language' : 'en-GB,en-US;q=0.9,en;q=0.8', 'Accept-Encoding' : 'gzip,deflate', 'Cache-control' : 'no-cache', 'Pragma' : 'no-cache', 'Referer' : 'https://open.spotify.com/', 'Sec-Fetch-Site' : 'same-site', 'Sec-Fetch-Mode' : 'cors', 'Sec-Fetch-Dest' : 'empty', 'sec-ch-ua-platform' : 'Linux', 'sec-ch-ua-mobile' : '?0', 'sec-ch-ua' : '".Not/A)Brand";v="99", "Google Chrome";v="103", "Chromium";v="103"', 'content-type' : 'text/plain;charset=UTF-8', 'Origin' : 'https://open.spotify.com', 'Authorization' : "Bearer %s"%accesstoken, 'client-token' : clienttoken}
        u = uuid.uuid1()
        t = (u.time - 0x01b21dd213814000)*100/1e9
        playbackid = str(u).replace("-", "")
        batchdata = {"messages":[{"type":"jssdk_playback_start","message":{"play_track":"spotify:track:%s"%episodeid,"file_id":"%s"%fid,"playback_id":"%s"%playbackid,"session_id":str(t),"ms_start_position":0,"initially_paused":False,"client_id":"","correlation_id":""}}],"sdk_id":"harmony:4.27.0","platform":"web_player linux undefined;chrome 103.0.0.0;desktop","client_version":"0.0.0"}
        batchpostdata = json.dumps(batchdata).encode('utf-8')
        batchheaders['content-length'] = batchpostdata.__len__()
        batchrequest = urllib.request.Request(batchurl, data=batchpostdata, headers=batchheaders)
        try:
            batchresponse = self.httpopener.open(batchrequest, timeout=TIMEOUT_S)
            batchcontent = _decodeGzippedContent(batchresponse.read())
            batchjson = json.loads(batchcontent)
            if batchjson['status'] == 202:
                print("Successfully made batch request")
            else:
                print("Batch request probably didn't succeed. Response - status: %s"%batchjson['status'])
        except:
            print("Error making batch request to %s: %s"%(batchurl, sys.exc_info()[1].__str__()))
        # We don't care about the response from the above request. It should send {'status' : 202} as response content, but we proceed with the next request even if it doesn't. The request above serves to increase the chances of a hit taking place.
        httpheaders = { 'User-Agent' : r'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/88.0.4324.150 Safari/537.36',  'Accept' : '*/*', 'Accept-Language' : 'en-GB,en-US;q=0.9,en;q=0.8', 'Accept-Encoding' : 'identity', 'Cache-control' : 'no-cache', 'Connection' : 'keep-alive', 'Pragma' : 'no-cache', 'Referer' : 'https://open.spotify.com/', 'Sec-Fetch-Site' : 'cross-site', 'Sec-Fetch-Mode' : 'cors', 'Sec-Fetch-Dest' : 'empty', 'sec-ch-ua-platform' : 'Linux', 'sec-ch-ua-mobile' : '?0', 'sec-ch-ua' : '".Not/A)Brand";v="99", "Google Chrome";v="103", "Chromium";v="103"', 'Origin' : 'https://open.spotify.com', 'Host' : 'audio-fa.scdn.co', 'range' : "bytes=0-"}
        if self.DEBUG:
            print("Spotify CDN Url: %s"%cdnurl)
        trackcontentrequest = urllib.request.Request(cdnurl, headers=httpheaders)
        trackcontent = b""
        try:
            trackcontentresponse = self.httpopener.open(trackcontentrequest, timeout=TIMEOUT_S) # Wait for 60 secs only.
            trackcontent = trackcontentresponse.read()
        except:
            print("Error making track content request to %s: %s"%(cdnurl, sys.exc_info()[1].__str__()))
            return None
        if self.DEBUG:
            print("Track media URL request from %s successful."%cdnurl)
        if self.DEBUG:
            outfile = dumpdir + os.path.sep + "spotify_track_%s.mp3"%str(int(time.time() * 1000))
            of = open(outfile, "wb")
            of.write(trackcontent)
            of.close()
        return cdnurl
        


    def getepisodemp3url(self, episodeid, accesstoken, clienttoken, dumpdir, itemtype="episode"):
        episodeurl = "https://spclient.wg.spotify.com/soundfinder/v1/unauth/episode/%s/com.widevine.alpha?market=IN"%episodeid
        if itemtype == "track":
            #episodeurl = "https://api.spotify.com/v1/tracks/%s"%episodeid
            retval = self.gettrackcontent(episodeid, accesstoken, clienttoken, dumpdir)
            if retval is not None:
                return retval
            else: # May be we have a podcast episode dressed as a track in a playlist.
                pass
        httpheaders = { 'User-Agent' : r'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/88.0.4324.150 Safari/537.36',  'Accept' : 'application/json', 'Accept-Language' : 'en', 'Accept-Encoding' : 'gzip,deflate', 'Cache-control' : 'no-cache', 'Connection' : 'keep-alive', 'Pragma' : 'no-cache', 'Referer' : 'https://open.spotify.com/', 'Sec-Fetch-Site' : 'same-site', 'Sec-Fetch-Mode' : 'cors', 'Sec-Fetch-Dest' : 'empty', 'sec-ch-ua-platform' : 'Linux', 'sec-ch-ua-mobile' : '?0', 'sec-ch-ua' : '".Not/A)Brand";v="99", "Google Chrome";v="103", "Chromium";v="103"', 'Origin' : 'https://open.spotify.com', 'Authorization' : "Bearer %s"%accesstoken, 'client-token' : clienttoken, 'app-platform' : 'WebPlayer'}
        if self.DEBUG:
            print("Spotify Episode URL: %s"%episodeurl)
            print("Spotify Access Token: %s"%accesstoken)
            print("Spotify Client Token: %s"%clienttoken)
        self.httpopener = self.buildopenerrandomproxy()
        epinforequest = urllib.request.Request(episodeurl, headers=httpheaders)
        try:
            self.httpresponse = self.httpopener.open(epinforequest,timeout=TIMEOUT_S) # Wait for a minute. If nothing comes out of it, quit.
        except:
            print("Error making episode info request to %s: %s"%(episodeurl, sys.exc_info()[1].__str__()))
            return ""
        self.httpcontent = "{}"
        try:
            self.httpcontent = _decodeGzippedContent(self.httpresponse.read())
        except:
            print("Could not retrieve episode URL - Error: %s"%sys.exc_info()[1].__str__())
        mp3url = ""
        self.ispodcast = True # This is set to True for itemtype='episode' and for those itemtype='track' whose content is actually a podcast episode arranged as a playlist.
        try:
            contentdict = json.loads(self.httpcontent)
            if itemtype == "episode":
                mp3url = contentdict['passthroughUrl']
            elif itemtype == "track": # This is for episodes of podcasts that have been arranged as a playlist (and hence, called 'track').
                mp3url = contentdict['tracks']['items'][i]['track']['external_playback_url']
            else:
                print("Given itemtype %s is not handled"%itemtype)
                mp3url = ""
        except:
            print("Error in getting mp3 URL: %s"%sys.exc_info()[1].__str__())
        return mp3url



    def getallepisodes(self):
        episodeurlpattern = re.compile("(https\:\/\/open\.spotify\.com\/episode\/[^\"]+)\"", re.DOTALL)
        allepisodeurls = re.findall(episodeurlpattern, str(self.httpcontent))
        if allepisodeurls.__len__() == 0: # Possibly this is a playlist, so there will be tracks.
            trackurlpattern = re.compile("(https\:\/\/open\.spotify\.com\/track\/[^\"]+)\"", re.DOTALL)
            uniqueurlsdict = {}
            alltrackurls = re.findall(trackurlpattern, str(self.httpcontent))
            allepisodeurls = []
            for epurl in alltrackurls:
                if epurl in uniqueurlsdict.keys():
                    continue
                uniqueurlsdict[epurl] = 1
                allepisodeurls.append(epurl)
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
            self.httpresponse = self.httpopener.open(clienttokenrequest, timeout=TIMEOUT_S)
        except:
            print("Error making client token request to %s: %s"%(requesturl, sys.exc_info()[1].__str__()))
            return ""
        self.httpcontent = "{}"
        try:
            self.httpcontent = _decodeGzippedContent(self.httpresponse.read())
        except:
            print("Could not get content for client token - Error: %s"%sys.exc_info()[1].__str__())
        try:
            respdict = json.loads(self.httpcontent)
            clienttoken = respdict['granted_token']['token']
        except:
            clienttoken = ""
        return clienttoken


    def getepisode(self, epurl):
        httpheaders = { 'User-Agent' : r'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/88.0.4324.150 Safari/537.36',  'Accept' : '*/*', 'Accept-Language' : 'en-GB,en-US;q=0.9,en;q=0.8', 'Accept-Encoding' : 'identity;q=1, *;q=0', 'Cache-control' : 'no-cache', 'Connection' : 'keep-alive', 'Pragma' : 'no-cache', 'Referer' : 'https://open.spotify.com/', 'Sec-Fetch-Site' : 'cross-site', 'Sec-Fetch-Mode' : 'no-cors', 'Sec-Fetch-Dest' : 'audio', 'sec-ch-ua-platform' : 'Linux', 'sec-ch-ua-mobile' : '?0', 'sec-ch-ua' : '".Not/A)Brand";v="99", "Google Chrome";v="103", "Chromium";v="103"', 'Origin' : 'https://open.spotify.com', 'range' : 'bytes=0-', 'Cookie' : self.httpheaders['cookie']}
        if self.DEBUG:
            print("Spotify Cookie: %s"%self.httpheaders['cookie'])
        self.makehttprequest(epurl, headers=httpheaders)
        try:
            content = self.httpresponse.read() # Actually, we don't need the content.
        except:
            content = ""
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
        self.httpheaders = { 'User-Agent' : r'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/88.0.4324.150 Safari/537.36',  'Accept' : 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9', 'Accept-Language' : 'en-us,en;q=0.5', 'Accept-Encoding' : 'gzip,deflate', 'Accept-Charset' : 'ISO-8859-1,utf-8;q=0.7,*;q=0.7', 'Connection' : 'keep-alive', }
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
            httpsrandomctr = getrandomint(0, httpsproxycount-1)
            self.proxyhandler = urllib.request.ProxyHandler({'https': self.proxies['https'][httpsrandomctr],})
            self.httpopener = urllib.request.build_opener(urllib.request.HTTPHandler(), self.httpshandler, self.proxyhandler, NoRedirectHandler())
            if self.DEBUG:
                print("Proxy used (Apple): %s"%self.proxies['https'][httpsrandomctr])
        except:
            print("Error creating opener with proxy: %s"%sys.exc_info()[1].__str__())
            self.httpopener = urllib.request.build_opener(urllib.request.HTTPHandler(), self.httpshandler, NoRedirectHandler())
        return self.httpopener
        


    def searchforpodcasts(self, searchkey, country="us", limit=20):
        podcasts = podsearch.search(searchkey, country=country, limit=limit)


    def makehttprequest(self, requrl):
        if requrl == '' or requrl is None:
            return None
        self.httpopener = self.buildopenerrandomproxy()
        self.httprequest = urllib.request.Request(requrl, headers=self.httpheaders)
        try:
            self.httpresponse = self.httpopener.open(self.httprequest, timeout=TIMEOUT_S)
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
        if resourceurl == "":
            print("Can't download apple podcast - Error: URL is ''")
            return None
        self.httpopener = self.buildopenerrandomproxy()
        #print("Resource URL: %s"%resourceurl)
        self.httprequest = urllib.request.Request(resourceurl, headers=self.httpheaders)
        try:
            self.httpresponse = self.httpopener.open(self.httprequest, timeout=TIMEOUT_S)
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
            self.httpresponse = self.httpopener.open(self.httprequest, timeout=TIMEOUT_S)
            content = self.httpresponse.read()
            redirecturlpattern = re.compile("href=\"([^\"]+)\"", re.DOTALL|re.IGNORECASE)
            rps = re.search(redirecturlpattern, str(content))
            if rps:
                mediaurl = rps.groups()[0]
            else:
                mediaurl = ""
        except:
            print("Error getting MediaURL (Apple) from '%s': %s"%(location, sys.exc_info()[1].__str__()))
            mediaurl = ""
        mediaurl = mediaurl.replace("amp;", "")
        #print("Media URL: %s"%mediaurl)
        httpheaders = { 'User-Agent' : r'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/88.0.4324.150 Safari/537.36',  'Accept' : '*/*', 'Accept-Language' : 'en-GB,en-US;q=0.9,en;q=0.8', 'Accept-Encoding' : 'identity;q=1, *;q=0', 'Accept-Charset' : 'ISO-8859-1,utf-8;q=0.7,*;q=0.7', 'Cache-control' : 'no-cache', 'Connection' : 'keep-alive', 'Pragma' : 'no-cache', 'Referer' : 'https://podcasts.apple.com/', 'Sec-Fetch-Site' : 'cross-site', 'Sec-Fetch-Mode' : 'no-cors', 'Sec-Fetch-Dest' : 'audio', 'sec-ch-ua-platform' : 'Linux', 'sec-ch-ua-mobile' : '?0', 'sec-ch-ua' : '".Not/A)Brand";v="99", "Google Chrome";v="103", "Chromium";v="103"', 'range' : 'bytes=0-'}
        try:
            self.httprequest = urllib.request.Request(mediaurl, headers=httpheaders)
            self.httpresponse = self.httpopener.open(self.httprequest, timeout=TIMEOUT_S)
            mediacontent = self.httpresponse.read()
        except:
            print("Error in making media request for Apple: %s"%sys.exc_info()[1].__str__())
            mediacontent = b""
        if self.DEBUG and mediacontent != b"":
            t = str(int(time.time() * 1000))
            dumpfile = dumpdir + os.path.sep + "apple_" + t + ".mp3"
            fp = open(dumpfile, "wb")
            fp.write(mediacontent)
            fp.close()
        return mediacontent


    def requestwebexp(self, siteurl, pageid, cookies):
        requesturl = "https://xp.apple.com/report/2/xp_amp_web_exp"
        t = int(time.time() * 1000)
        clientid = "4zWHHWZoJz3Nk5UZz7TTz4Qaz8q8z8Ystbxv5"
        clienteventid1 = "1_1_svwqg2Mshuc24ibcJ2WH9DI0"
        clienteventid2 = "1_1_phzd02cMYum2hoOK41f7e7h2"
        jsondata = {"deliveryVersion":"1.0","postTime":t,"events":[{"storeFront":"us","eventTime":(t -1000),"type":"launch","openUrl":"%s"%siteurl,"refUrl":"","extRefUrl":"","app":"web-experience-app","appVersion":"2234.1.0","baseVersion":1,"constraintProfiles":["AMPWeb"],"clientEventId":"%s"%clienteventid1,"isSignedIn":False,"pageUrl":"%s"%siteurl,"pixelRatio":1,"resourceRevNum":"2234.1.0","screenHeight":768,"screenWidth":1366,"timezoneOffset":-330,"userAgent":"Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/103.0.0.0 Safari/537.36","windowInnerHeight":607,"windowInnerWidth":788,"windowOuterHeight":741,"windowOuterWidth":1299,"xpPostFrequency":60000,"xpSendMethod":"javascript","xpVersionMetricsKit":"7.3.5","eventType":"enter","eventVersion":1,"clientId":"%s"%clientid},{"pageId":"%s"%pageid,"pageType":"Podcast","pageContext":"iTunes","storeFront":"us","isSignedIn":False,"userType":"signedOut","osLanguage":"en-GB","osLanguages":["en-GB","en-US","en"],"page":"Podcast_%s"%pageid,"pageUrl":"%s"%siteurl,"refUrl":"","extRefUrl":"","app":"web-experience-app","appVersion":"2234.1.0","baseVersion":1,"constraintProfiles":["AMPWeb"],"clientEventId":"%s"%clienteventid2,"eventTime":(t - 500),"pixelRatio":1,"resourceRevNum":"2234.1.0","screenHeight":768,"screenWidth":1366,"timezoneOffset":-330,"userAgent":"Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/103.0.0.0 Safari/537.36","windowInnerHeight":607,"windowInnerWidth":788,"windowOuterHeight":741,"windowOuterWidth":1299,"xpPostFrequency":60000,"xpSendMethod":"javascript","xpVersionMetricsKit":"7.3.5","eventType":"page","eventVersion":1,"pageHistory":[],"clientId":"%s"%clientid}]}
        postdata = json.dumps(jsondata).encode('utf-8')
        httpheaders = { 'User-Agent' : r'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/88.0.4324.150 Safari/537.36',  'Accept' : '*/*', 'Accept-Language' : 'en-GB,en-US;q=0.9,en;q=0.8', 'Accept-Encoding' : 'gzip, deflate', 'Cache-control' : 'no-cache', 'Connection' : 'keep-alive', 'Pragma' : 'no-cache', 'Referer' : 'https://podcasts.apple.com/', 'Origin' : 'https://podcasts.apple.com/', 'Host' : 'xp.apple.com', 'Sec-Fetch-Site' : 'same-site', 'Sec-Fetch-Mode' : 'cors', 'Sec-Fetch-Dest' : 'empty', 'sec-ch-ua-platform' : 'Linux', 'sec-ch-ua-mobile' : '?0', 'sec-ch-ua' : '".Not/A)Brand";v="99", "Google Chrome";v="103", "Chromium";v="103"', 'Content-type' : 'application/json'}
        httpheaders['Cookie'] = cookies
        httpheaders['Content-Length'] = postdata.__len__()
        opener = self.buildopenerrandomproxy()
        request = urllib.request.Request(requesturl, data=postdata, headers=httpheaders)
        try:
            response = opener.open(request, timeout=TIMEOUT_S)
        except:
            print("Error sending request to xp_amp_web_exp (Apple): %s"%sys.exc_info()[1].__str__())
            response = None
        return response


class BuzzBot(object):
    
    def __init__(self, podlisturl, amazonkey, spotifyclientid, spotifyclientsecret, parent, proxieslist=[]):
        self.DEBUG = False
        self.humanize = True
        self.logging = True
        self.cleanupmedia = True
        self.platformonly = None
        self.parent = weakref.ref(parent)
        self.quitflag = False
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
            httpsrandomctr = getrandomint(0, httpsproxycount-1)
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


    def buildopenergivenproxy(self, httpsproxyipport):
        self.context = createrequestcontext()
        self.httpshandler = urllib.request.HTTPSHandler(context=self.context)
        try:
            self.proxyhandler = urllib.request.ProxyHandler({'https': 'https://' + httpsproxyipport,})
            httpopener = urllib.request.build_opener(urllib.request.HTTPHandler(), self.httpshandler, self.proxyhandler)
            if self.logging:
                self.logger.write("Created opener using proxy %s\n"%httpsproxyipport)
        except:
            print("Error creating opener with proxy: %s"%sys.exc_info()[1].__str__())
            if self.logging:
                self.logger.write("Error creating opener with proxy: %s"%sys.exc_info()[1].__str__())
            httpopener = urllib.request.build_opener(urllib.request.HTTPHandler(), urllib.request.HTTPSHandler())
        return httpopener


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
            self.httpresponse = self.httpopener.open(self.httprequest, timeout=TIMEOUT_S)
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
        if lastHttpResponse is None:
            return cookies
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


    def hitpodcast(self, siteurl, sitename, targetcount=-1, dbid=-1, statusfile=None, desktop=True):
        global AMAZON_HIT_STAT
        global SPOTIFY_HIT_STAT
        global APPLE_HIT_STAT
        titleregex = makeregex(self.podcasttitle)
        apikey = self.amazonkey
        spotifyclientid = self.spotifyclientid
        spotifyclientsecret = self.spotifyclientsecret
        ctr = 0
        if targetcount == -1:
            targetcount = 10000 # We set this to 10000, a suitably large number of hits
        if self.logging:
            self.logger.write("Starting podcast hits for '%s': Target count = %s\n"%(sitename, targetcount))
        fsf = None
        if statusfile is not None:
            if not os.path.exists(statusfile):
                fsf = open(statusfile, "w")
            else:
                fsf = open(statusfile, "a")
            fsf.write("Starting podcast hits for '%s': Target count = %s\n"%(sitename, targetcount))
        if sitename.lower() == "apple":
            if self.DEBUG:
                print(siteurl)
            if self.logging:
                self.logger.write("Apple URL: %s\n"%siteurl)
            if fsf is not None:
                fsf.write("Apple URL: %s\n"%siteurl)
            statuspattern = re.compile("APPLE\:\s+\d+", re.DOTALL)
            applebot = None
            pageidpattern = re.compile("id(\d+)$")
            pps = re.search(pageidpattern, siteurl)
            pageid = ""
            if pps:
                pageid = pps.groups()[0]
            while ctr < targetcount :
                applebot = AppleBot(self.proxies)
                applebot.DEBUG = self.DEBUG
                applebot.humanize = self.humanize
                applebot.logging = self.logging
                resp = applebot.makehttprequest(siteurl)
                cookies = BuzzBot._getCookieFromResponse(resp)
                applebot.gethttpresponsecontent()
                podcastlinks = applebot.listpodcastsonpage()
                if self.DEBUG:
                    print("APPLE ITERATION #%s ======================="%ctr)
                if self.logging:
                    self.logger.write("APPLE ITERATION #%s =======================\n"%ctr)
                if fsf is not None:
                    fsf.write("APPLE ITERATION #%s =======================\n"%ctr)
                for pclink in podcastlinks:
                    if self.quitflag == True:
                        print("Quit signal received. Terminating apple child.")
                        return None
                    resp = applebot.requestwebexp(siteurl, pageid, cookies)
                    if resp is not None:
                        if applebot.DEBUG:
                            print("Sent request to web_exp")
                    if self.logging:
                        self.logger.write("Getting Apple podcast mp3 from %s\n"%pclink)
                    if fsf is not None:
                        fsf.write("APPLE ITERATION #%s =======================\n"%ctr)
                    if self.humanize:
                        ht = getrandominterval(5)
                        time.sleep(ht)
                    resp = applebot.downloadpodcast(pclink, self.dumpdir)
                    APPLE_HIT_STAT += 1
                    if desktop:
                        curmessagecontent = self.msglabeltext.get()
                        replacementmessage = "APPLE: %s"%APPLE_HIT_STAT
                        curmessagecontent = statuspattern.sub(replacementmessage, curmessagecontent)
                        self.msglabeltext.set(curmessagecontent)
                    if fsf is not None:
                        fsf.write("APPLE: %s"%APPLE_HIT_STAT)
                ctr += 1
            if dbid > -1: # This could be a valid id if the request came from the web interface
                dbconn = MySQLdb.connect(host='localhost', user='hituser', password='hitpasswd', db='hitdb')
                cursorobj = dbconn.cursor()
                sql = "update hitweb_manager set actualcount=%s, endtime=NOW() where id=%s"%(APPLE_HIT_STAT, dbid)
                cursorobj.execute()
                dbconn.commit()
                dbconn.close()
            # Check to see if self.podcasttitle exists in the retrieved content
            boolret = False
            if applebot is not None:
                boolret = applebot.existsincontent(titleregex)
                if "apple" in self.hitstatus.keys():
                    self.hitstatus['apple'].append(boolret)
                else:
                    self.hitstatus['apple'] = []
                    self.hitstatus['apple'].append(boolret)
        elif sitename.lower() == "spotify":
            statuspattern = re.compile("SPOTIFY\:\s+\d+", re.DOTALL)
            spotbot = None
            while ctr < targetcount:
                spotbot = SpotifyBot(spotifyclientid, spotifyclientsecret, self.proxies) # Get this from the environment
                if self.DEBUG:
                    print("Spotify: %s"%siteurl)
                if self.logging:
                    self.logger.write("Spotify URL: %s\n"%siteurl)
                if fsf is not None:
                    fsf.write("Spotify URL: %s\n"%siteurl)
                playlistpattern = re.compile("https\:\/\/open\.spotify\.com\/playlist\/([a-zA-Z\d]+)$", re.IGNORECASE)
                spps = re.search(playlistpattern, siteurl)
                if spps:
                    spotbot.playlistid = spps.groups()[0]
                spotbot.DEBUG = self.DEBUG
                spotbot.humanize = self.humanize
                spotbot.logging = self.logging
                spotbot.makehttprequest(siteurl)
                spotbot.gethttpresponsecontent()
                episodeurls = spotbot.getallepisodes()
                episodeidlist = []
                episodeurlpattern = re.compile("https\:\/\/open\.spotify\.com\/episode\/([^\"]+)$")
                trackurlpattern = re.compile("https\:\/\/open\.spotify\.com\/track\/([^\"]+)$")
                episodeitemlist = []
                itemtype = "episode"
                for epurl in episodeurls:
                    eps = re.search(episodeurlpattern, epurl)
                    tps = re.search(trackurlpattern, epurl)
                    if eps:
                        epid = eps.groups()[0]
                        episodeidlist.append(epid)
                    elif tps:
                        trid = tps.groups()[0]
                        episodeidlist.append(trid)
                        itemtype = "track"
                episodeids = ",".join(episodeidlist)
                if self.logging:
                    self.logger.write("Spotify episode Ids: %s\n"%episodeids)
                if fsf is not None:
                    fsf.write("Spotify episode Ids: %s\n"%episodeids)
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
                if self.DEBUG:
                    print("SPOTIFY ITERATION #%s ======================="%ctr)
                if self.logging:
                    self.logger.write("SPOTIFY ITERATION #%s =======================\n"%ctr)
                if fsf is not None:
                    fsf.write("SPOTIFY ITERATION #%s =======================\n"%ctr)
                spotmp3list = []
                for eid in episodeidlist:
                    spotbot.ispodcast = False
                    epmp3url = spotbot.getepisodemp3url(eid, accesstoken, clienttoken, self.dumpdir, itemtype)
                    if self.DEBUG:
                        print("Spotify mp3 URL: %s"%epmp3url)
                    if self.logging:
                        self.logger.write("Spotify mp3 URL: %s\n"%epmp3url)
                    if fsf is not None:
                        fsf.write("Spotify mp3 URL: %s\n"%epmp3url)
                    if itemtype == "track" and spotbot.ispodcast == False: # If we have a track, then we are already hitting the target through "getepisodemp3url"
                        SPOTIFY_HIT_STAT += 1
                        curmessagecontent = self.msglabeltext.get()
                        replacementmessage = "SPOTIFY: %s"%SPOTIFY_HIT_STAT
                        curmessagecontent = statuspattern.sub(replacementmessage, curmessagecontent)
                        self.msglabeltext.set(curmessagecontent)
                        if fsf is not None:
                            fsf.write("SPOTIFY: %s"%SPOTIFY_HIT_STAT)
                    spotmp3list.append(epmp3url)
                for epurl in spotmp3list:
                    if self.quitflag == True:
                        print("Quit signal received. Terminating spotify child.")
                        return None
                    if self.humanize:
                        ht = getrandominterval(5)
                        time.sleep(ht)
                    if spotbot.ispodcast == True:
                        content = spotbot.getepisode(epurl)
                    if self.logging:
                        self.logger.write("Got Spotify mp3 from %s\n"%epurl)
                    if self.DEBUG:
                        if spotbot.ispodcast == True:
                            if type(content) == str or content is None:
                                continue # We are expecting mp3 content, but if there is an error in the respone, we might get a string.
                            t = str(int(time.time() * 1000))
                            fs = open(self.dumpdir + os.path.sep + "spotify_%s.mp3"%t, "wb")
                            fs.write(content)
                            fs.close()
                    if spotbot.ispodcast == True:
                        SPOTIFY_HIT_STAT += 1
                        if desktop:
                            curmessagecontent = self.msglabeltext.get()
                            replacementmessage = "SPOTIFY: %s"%SPOTIFY_HIT_STAT
                            curmessagecontent = statuspattern.sub(replacementmessage, curmessagecontent)
                            self.msglabeltext.set(curmessagecontent)
                        if fsf is not None:
                            fsf.write("SPOTIFY: %s"%SPOTIFY_HIT_STAT)
                ctr += 1
            if dbid > -1: # This could be a valid id if the request came from the web interface
                dbconn = MySQLdb.connect(host='localhost', user='hituser', password='hitpasswd', db='hitdb')
                cursorobj = dbconn.cursor()
                sql = "update hitweb_manager set actualcount=%s, endtime=NOW() where id=%s"%(SPOTIFY_HIT_STAT, dbid)
                cursorobj.execute()
                dbconn.commit()
                dbconn.close()
            # Check to see if self.podcasttitle exists in the retrieved content
            boolret = False
            if spotbot is not None:
                boolret = spotbot.existsincontent(titleregex)
                if "spotify" in self.hitstatus.keys():
                    self.hitstatus['spotify'].append(boolret)
                else:
                    self.hitstatus['spotify'] = []
                    self.hitstatus['spotify'].append(boolret)
        elif sitename.lower() == "amazon":
            if self.DEBUG:
                print("Amazon: %s"%siteurl)
            if self.logging:
                self.logger.write("Amazon URL: %s\n"%siteurl)
            if fsf is not None:
                fsf.write("Amazon URL: %s\n"%siteurl)
            podcastmainurlparts = siteurl.split("/")
            podcastdomain = podcastmainurlparts[2]
            statuspattern = re.compile("AMAZON\:\s+\d+", re.DOTALL)
            idpattern = re.compile("https\:\/\/music\.amazon\.com\/podcasts\/(.*)$")
            idps = re.search(idpattern, siteurl)
            urlid = ""
            if idps:
                urlid = idps.groups()[0]
            else:
                pass # If urlid can't be found, then there is actually not much we can do.
            ctr = 0
            ambot = None
            while ctr < targetcount:
                ambot = AmazonBot(apikey, self.proxies) # Get this from the environment
                ambot.DEBUG = self.DEBUG
                ambot.humanize = self.humanize
                ambot.logging = self.logging
                ambot.makehttprequest(siteurl)
                ambot.gethttpresponsecontent()
                proxyip = ambot.selectedproxy
                proxyport = ambot.selectedproxyport
                devicetypepattern = re.compile("\"deviceType\"\:\s*\"([^\"]+)\",", re.DOTALL)
                deviceidpattern = re.compile("\"deviceId\"\:\s*\"?([\d]+)\"?,", re.DOTALL)
                faviconpattern = re.compile("\"faviconUrl\"\:\s*\"([^\"]+)\",", re.DOTALL)
                marketplacepattern = re.compile("\"marketplaceId\"\:\s*\"([^\"]+)\",", re.DOTALL)
                sessionidpattern = re.compile("\"sessionId\"\:\s*\"([^\"]+)\",", re.DOTALL)
                ipaddresspattern = re.compile("\"ipAddress\"\:\s*\"([^\"]+)\",", re.DOTALL)
                csrftokenpattern = re.compile("\"token\"\:\s*\"([^\"]+)\",", re.DOTALL)
                csrftspattern = re.compile("\"ts\"\:\s*\"([^\"]+)\",", re.DOTALL)
                csrfrndpattern = re.compile("\"rnd\"\:\s*\"?([\d]+)\"?,", re.DOTALL)
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
                #ipaddr = ip4to6(proxyip)
                ipaddr = proxyip
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
                iplist = []
                for eurl in episodeurls:
                    if self.logging:
                        self.logger.write("Fetching Amazon episode URL: %s\n"%eurl)
                    if fsf is not None:
                        fsf.write("Fetching Amazon episode URL: %s\n"%eurl)
                    response = ambot.makehttprequest(eurl)
                    #print(response.headers)
                    if 'set-cookie' in response.headers.keys():
                        cookies = response.headers['set-cookie']
                    else:
                        cookies = ""
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
                    randomint = random.randint(0, 9)
                    randpos = random.randint(0, 16)
                    devid = "13142066350023546"
                    devidlist = list(devid)
                    devidlist[randpos] = randomint
                    for i in range(devidlist.__len__()):
                        devidlist[i] = str(devidlist[i])
                    devid = ''.join(devidlist)
                    csrfrnd = "1387173668"
                    csrfrndlist = list(csrfrnd)
                    randomint = random.randint(0, 9)
                    randpos = random.randint(0, 9)
                    csrfrndlist[randpos] = randomint
                    for i in range(csrfrndlist.__len__()):
                        csrfrndlist[i] = str(csrfrndlist[i])
                    csrfrnd = ''.join(csrfrndlist)
                    proxyip = ambot.selectedproxy
                    #ipaddr = ip4to6(proxyip)
                    ipaddr = proxyip
                    iplist.append(proxyip + ":" + ambot.selectedproxyport)
                    params = (urlid, sessid, ipaddr, csrftoken, csrfts, csrfrnd, devid, devtype, eurl)
                    mediaidpattern = re.compile("\"mediaId\"\:\"(https:\/\/[^\"]+)\",", re.DOTALL)
                    mflag = 1
                    if self.logging:
                        self.logger.write("Amazon 'visual' url second request parameters:\n urlid: %s\nsessid: %s\nipaddr: %s\ncsrftoken: %s\ncsrfts: %s\ncsrfrnd: %s\ndevid: %s\ndevtype: %s\n"%(urlid, sessid, ipaddr, csrftoken, csrfts, csrfrnd, devid, devtype))
                    if self.humanize:
                        ht = getrandominterval(5)
                        time.sleep(ht)
                    cookiestr = ambot.getpandatoken(devtype, eurl, cookies)
                    mediadict = ambot.getvisualdict(params, episodeids[ectr], mflag, cookies=cookiestr)
                    #print(mediadict)
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
                        if fsf is not None:
                            fsf.write("Error in extracting Amazon media links: %s\n"%sys.exc_info()[1].__str__())
                    # Need to hit "visual" url again, just to make the download count. This is insane.
                    ambot.playbackstartedvisual(params, mediaurl, episodeids[ectr])
                    ambot.clearmusicqueuerequest(csrftoken, csrfts, devid, eurl, csrfrnd, sessid, podcastdomain)
                    ectr += 1
                if self.logging:
                    self.logger.write("Amazon media links: %s\n"%("\n".join(mediaurlslist),)) 
                if self.DEBUG:
                    print("AMAZON ITERATION #%s ======================="%ctr)
                if self.logging:
                    self.logger.write("AMAZON ITERATION #%s =======================\n"%ctr)
                if fsf is not None:
                    fsf.write("AMAZON ITERATION #%s =======================\n"%ctr)
                ipctr = 0
                for mediaurl in mediaurlslist:
                    if self.quitflag == True:
                        print("Quit signal received. Terminating amazon child.")
                        return None
                    httpheaders = {}
                    httpheaders['Referer'] = "https://music.amazon.com/"
                    httpheaders['range'] = "bytes=0-"
                    httpheaders['sec-fetch-dest'] = "audio"
                    httpheaders['sec-fetch-mode'] = "no-cors"
                    httpheaders['sec-fetch-site'] = "cross-site"
                    httpheaders['Accept-Encoding'] = "identity;q=1, *;q=0"
                    httpheaders['Accept-Language'] = "en-GB,en-US;q=0.9,en;q=0.8"
                    httpheaders['Accept'] = "*/*"
                    httpheaders['pragma'] = "no-cache"
                    httpheaders['cache-control'] = "no-cache"
                    httpheaders['sec-ch-ua'] = '".Not/A)Brand";v="99", "Google Chrome";v="103", "Chromium";v="103"'
                    httpheaders['sec-ch-ua-mobile'] = '?0'
                    httpheaders['sec-ch-ua-platform'] = '"Linux"'
                    httpheaders['user-agent'] = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/103.0.0.0 Safari/537.36"
                    if self.humanize:
                        ht = getrandominterval(5)
                        time.sleep(ht)
                    #response = ambot.makehttprequest(mediaurl)
                    proxyipport = iplist[ipctr]
                    #amzopener = ambot.buildopenerrandomproxy()
                    amzopener = self.buildopenergivenproxy(proxyipport)
                    amzrequest = urllib.request.Request(mediaurl, headers=httpheaders)
                    try:
                        response = amzopener.open(amzrequest, timeout=TIMEOUT_S)
                    except:
                        print("Error fetching media for Amazon podcast: %s"%sys.exc_info()[1].__str__())
                        response = None
                    if self.DEBUG:
                        print("Getting mp3 from Amazon: %s"%mediaurl)
                    if self.logging:
                        self.logger.write("Getting mp3 from Amazon: %s\n"%mediaurl)
                    if fsf is not None:
                        fsf.write("Getting mp3 from Amazon: %s\n"%mediaurl)
                    AMAZON_HIT_STAT += 1
                    if desktop:
                        curmessagecontent = self.msglabeltext.get()
                        replacementmessage = "AMAZON: %s"%AMAZON_HIT_STAT
                        curmessagecontent = statuspattern.sub(replacementmessage, curmessagecontent)
                        self.msglabeltext.set(curmessagecontent)
                    if self.logging:
                        self.logger.write("Fetched Amazon URL: %s\n"%mediaurl)
                    if fsf is not None:
                        fsf.write("Fetched Amazon URL: %s\n"%mediaurl)
                        fsf.write("AMAZON: %s"%AMAZON_HIT_STAT)
                    if self.DEBUG:
                        t = str(int(time.time() * 1000))
                        if response is not None:
                            try:
                                fa = open(self.dumpdir + os.path.sep + "amazon_%s.mp3"%t, "wb")
                                fa.write(response.read())
                                fa.close()
                            except:
                                print("Could not read response from Amazon mp3 url: %s"%sys.exc_info()[1].__str__())
                        else:
                            print("Couldn't read response from Amazon mp3 media URL.")
                    else:
                        pass
                    ipctr += 1
                ctr += 1
            if dbid > -1: # This could be a valid id if the request came from the web interface
                dbconn = MySQLdb.connect(host='localhost', user='hituser', password='hitpasswd', db='hitdb')
                cursorobj = dbconn.cursor()
                sql = "update hitweb_manager set actualcount=%s, endtime=NOW() where id=%s"%(AMAZON_HIT_STAT, dbid)
                cursorobj.execute()
                dbconn.commit()
                dbconn.close()
            # Check to see if self.podcasttitle exists in the retrieved content
            boolret = False
            if ambot is not None:
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
        if fsf is not None:
            fsf.close()
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
        self.targetamazonhits.grid(row=6, column=1, columnspan=2)
        self.amazononly_var = IntVar()
        self.amazononly = False
        self.amazononlychkbtn = Checkbutton(self.mainwin, text = "Amazon Only", variable = self.amazononly_var, onvalue = 1, offvalue = 0, height=2, width = 10, command=self.deactivateotherplatforms)
        self.amazononlychkbtn.grid(row=6, column=2)
        self.targetcountspotifylbl = StringVar()
        self.targetcountspotifylabel = Label(self.mainwin, textvariable=self.targetcountspotifylbl, width=25, justify=LEFT, relief=RAISED)
        self.targetcountspotifylabel.grid(row=7, column=0, sticky=W)
        self.targetcountspotifylbl.set("Spotify Hits: ")
        #self.targetspotifyhits = Entry(self.mainwin, width=40, borderwidth=1)
        self.defaultspotifyhits = StringVar()
        self.defaultspotifyhits.set(-1)
        self.targetspotifyhits = ttk.Combobox(self.mainwin, textvariable=self.defaultspotifyhits, values=[i for i in range(-1,1000)], validatecommand=self.valcmd)
        self.targetspotifyhits.grid(row=7, column=1, columnspan=2)
        self.spotifyonly_var = IntVar()
        self.spotifyonly = False
        self.spotifyonlychkbtn = Checkbutton(self.mainwin, text = "Spotify Only", variable = self.spotifyonly_var, onvalue = 1, offvalue = 0, height=2, width = 10, command=self.deactivateotherplatforms)
        self.spotifyonlychkbtn.grid(row=7, column=2)
        self.targetcountapplelbl = StringVar()
        self.targetcountapplelabel = Label(self.mainwin, textvariable=self.targetcountapplelbl, width=25, justify=LEFT, relief=RAISED)
        self.targetcountapplelabel.grid(row=8, column=0, sticky=W)
        self.targetcountapplelbl.set("Apple Hits: ")
        #self.targetapplehits = Entry(self.mainwin, width=40, borderwidth=1)
        self.defaultapplehits = StringVar()
        self.defaultapplehits.set(-1)
        self.targetapplehits = ttk.Combobox(self.mainwin, textvariable=self.defaultapplehits, values=[i for i in range(-1,1000)], validatecommand=self.valcmd)
        self.targetapplehits.grid(row=8, column=1, columnspan=2)
        self.appleonly_var = IntVar()
        self.appleonly = False
        self.appleonlychkbtn = Checkbutton(self.mainwin, text = "Apple Only", variable = self.appleonly_var, onvalue = 1, offvalue = 0, height=2, width = 10, command=self.deactivateotherplatforms)
        self.appleonlychkbtn.grid(row=8, column=2)
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
        self.messagelabel = Message(self.mainwin, textvariable=self.msglabeltext, bg="white", width=45, borderwidth=4, relief="groove")
        self.messagelabel.grid(row=11, columnspan=4)

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


    # Signal handler to handle ctrl+c interrupt
    def handler(self, signum, frame):
        print("Terminating all threads...")
        exit(1)


    def startbot(self):
        self.runbutton.config(state=DISABLED)
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
        self.proxypattern = re.compile("^https\:\/\/\d+\.\d+\.\d+\.\d+\:\d+", re.IGNORECASE)
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
        signal.signal(signal.SIGINT, self.handler)
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
            if sitename.lower() == "apple":
                targetcount = self.buzz.applesettarget
                if self.amazononly == True or self.spotifyonly == True:
                    targetcount = 0
            if sitename.lower() == "amazon":
                targetcount = self.buzz.amazonsettarget
                if self.appleonly == True or self.spotifyonly == True:
                    targetcount = 0
            if sitename.lower() == "spotify":
                targetcount = self.buzz.spotifysettarget
                if self.appleonly == True or self.amazononly == True:
                    targetcount = 0
            # If targetcount is 0, then there is no reason to start a thread
            if targetcount == 0:
                continue
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
        # Write this message in history
        historyfile = os.getcwd() + os.path.sep + "hitbot2_" + time.strftime("%Y%m%d%H%M%S",time.localtime()) + ".history"
        if not os.path.exists(historyfile):
            fh = open(historyfile, "w")
        else:
            fh = open(historyfile, "a")
        fh.write(curmessagecontent + "\n=================================\n\n")
        fh.close()
        self.runbutton.config(state=ACTIVE)
        return True


    def closebot(self):
        try:
            self.buzz.quitflag = True
        except:
            print("No object called 'buzz'")
        if self.rt is not None:
            self.rt.join()
        # Write this message in history
        curmessagecontent = self.msglabeltext.get()
        historyfile = os.getcwd() + os.path.sep + "hitbot2_" + time.strftime("%Y%m%d%H%M%S",time.localtime()) + ".history"
        if not os.path.exists(historyfile):
            fh = open(historyfile, "w")
        else:
            fh = open(historyfile, "a")
        fh.write(curmessagecontent + "\n=================================\n\n")
        fh.close()
        if self.buzz is not None and self.buzz.logger is not None:
            self.buzz.logger.close()
        self.runbutton.config(state=ACTIVE)
        sys.exit()


    def stopbot(self):
        """
        if os.name == 'posix':
            signal.SIGINT # On linux or macOSX
        else:
            signal.CTRL_C_EVENT # On windows family
        """
        self.closebot()


    def deactivateotherplatforms(self):
        if self.amazononly_var.get() == 1:
            self.spotifyonly_var.set(0)
            self.spotifyonly = False
            self.spotifyonlychkbtn.config(state=DISABLED)
            self.targetspotifyhits.config(state=DISABLED)
            self.appleonly_var.set(0)
            self.appleonly = False
            self.appleonlychkbtn.config(state=DISABLED)
            self.targetapplehits.config(state=DISABLED)
            self.amazononly = True
            self.amazononlychkbtn.config(state=ACTIVE)
            self.targetamazonhits.config(state=ACTIVE)
        elif self.spotifyonly_var.get() == 1:
            self.appleonly_var.set(0)
            self.appleonly = False
            self.appleonlychkbtn.config(state=DISABLED)
            self.targetapplehits.config(state=DISABLED)
            self.amazononly_var.set(0)
            self.amazononly = False
            self.amazononlychkbtn.config(state=DISABLED)
            self.targetamazonhits.config(state=DISABLED)
            self.spotifyonly = True
            self.spotifyonlychkbtn.config(state=ACTIVE)
            self.targetspotifyhits.config(state=ACTIVE)
        elif self.appleonly_var.get() == 1:
            self.spotifyonly_var.set(0)
            self.spotifyonly = False
            self.spotifyonlychkbtn.config(state=DISABLED)
            self.targetspotifyhits.config(state=DISABLED)
            self.amazononly_var.set(0)
            self.amazononly = False
            self.amazononlychkbtn.config(state=DISABLED)
            self.targetamazonhits.config(state=DISABLED)
            self.appleonly = True
            self.appleonlychkbtn.config(state=ACTIVE)
            self.targetapplehits.config(state=ACTIVE)
        else:
            self.spotifyonly_var.set(0)
            self.spotifyonly = False
            self.spotifyonlychkbtn.config(state=ACTIVE)
            self.targetspotifyhits.config(state=ACTIVE)
            self.appleonly_var.set(0)
            self.appleonly = False
            self.appleonlychkbtn.config(state=ACTIVE)
            self.targetapplehits.config(state=ACTIVE)
            self.amazononly_var.set(0)
            self.amazononly = False
            self.amazononlychkbtn.config(state=ACTIVE)
            self.targetamazonhits.config(state=ACTIVE)



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


