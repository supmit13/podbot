import os, sys, re, time
from datetime import datetime
import random

import subprocess
from multiprocessing import Process, Pool, Queue
from threading import Thread

import urllib, requests
from urllib.parse import urlencode, quote_plus, urlparse

import simplejson as json
from bs4 import BeautifulSoup
import numpy as np
import gzip
import io
import hashlib, base64

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
    
    def __init__(self, apikey):
        self.DEBUG = 1
        self.apikey = apikey
        self.proxies = {'http' : [], 'https' : []}
        self.response = None # This would a response object from Amazon API
        self.content = None # This could be a text chunk or a binary data (like a Podcast content)
        self.podclient = podcast_api.Client(api_key=self.apikey)
        self.results = []
        # HTTP(S) request/response and parameters
        self.httprequest = None
        self.httpresponse = None
        self.httpcontent = None
        try:
            self.proxyhandler = urllib.request.ProxyHandler({'http' : self.proxies['http'][0], 'https': self.proxies['https'][0]})
            self.httpopener = urllib.request.build_opener(urllib.request.HTTPHandler(), urllib.request.HTTPSHandler(), self.proxyhandler)
        except:
            self.httpopener = urllib.request.build_opener(urllib.request.HTTPHandler(), urllib.request.HTTPSHandler())
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
        httpproxycount = self.proxies['http'].__len__() - 1
        httpsproxycount = self.proxies['https'].__len__() - 1
        httprandomctr = random.randint(0, httpproxycount)
        httpsrandomctr = random.randint(0, httpsproxycount)
        self.proxyhandler = urllib.request.ProxyHandler({'http' : self.proxies['http'][httprandomctr], 'https': self.proxies['https'][httpsrandomctr]})
        self.httpopener = urllib.request.build_opener(urllib.request.HTTPHandler(), urllib.request.HTTPSHandler(), self.proxyhandler)
        return self.httpopener


    def makehttprequest(self, requrl):
        self.httprequest = urllib.request.Request(requrl, headers=self.httpheaders)
        try:
            self.httpresponse = self.httpopener.open(self.httprequest)
        except:
            print("Error making request to %s: %s"%(requrl, sys.exc_info()[1].__str__()))
            return None
        self.httpcookies = BuzzBot._getCookieFromResponse(self.httpresponse)
        #print(self.httpresponse.headers)
        self.httpheaders['cookie'] = self.httpcookies
        return self.httpresponse


    def gethttpresponsecontent(self):
        try:
            encodedcontent = self.httpresponse.read()
            self.httpcontent = _decodeGzippedContent(encodedcontent)
        except:
            print("Error reading content: %s"%sys.exc_info()[1].__str__())
            self.httpcontent = None
            return None
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


    def getvisualdict(self, paramstuple):
        urlid, sessid, ipaddr, csrftoken, csrfts, csrfrnd, devid, devtype, siteurl = paramstuple[0], paramstuple[1], paramstuple[2], paramstuple[3], paramstuple[4], paramstuple[5], paramstuple[6], paramstuple[7], paramstuple[8]
        siteurlparts = siteurl.split("/")
        siteurl = "/".join(siteurlparts[2:])
        ts = int(time.time() * 1000)
        httpheaders = {'accept' : '*/*', 'accept-encoding' : 'gzip,deflate', 'accept-language' : 'en-GB,en-US;q=0.9,en;q=0.8', 'cache-control' : 'no-cache', 'content-encoding' : 'amz-1.0', 'content-type' : 'application/json; charset=UTF-8', 'origin' : 'https://music.amazon.com', 'pragma' : 'no-cache', 'referer' : siteurl, 'sec-ch-ua' : '".Not/A)Brand";v="99", "Google Chrome";v="103", "Chromium";v="103"', 'sec-ch-ua-mobile' : '?0', 'sec-ch-ua-platform' : 'Linux', 'sec-fetch-dest' : 'empty', 'sec-fetch-mode' : 'cors', 'sec-fetch-site' : 'same-origin', 'user-agent' : 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/103.0.0.0 Safari/537.36', 'x-amz-target' : 'com.amazon.dmpbrowsevisualservice.skills.DMPBrowseVisualService.ShowPodcastWebSkill', 'x-amzn-requestid' : ''}
        httpheaders['cookie'] = ""
        httpheaders['cookie'] += self.httpheaders['cookie']
        print(httpheaders['cookie'])
        datadict = {"preset":"{\"id\":\"%s\",\"nextToken\":null}"%urlid,"identity":{"__type":"SOACoreInterface.v1_0#Identity","application":{"__type":"SOACoreInterface.v1_0#ApplicationIdentity","version":"2.1"},"user":{"__type":"SOACoreInterface.v1_0#UserIdentity","authentication":""},"request":{"__type":"SOACoreInterface.v1_0#RequestIdentity","id":"2e9db538-680f-44e4-a2bf-bb0d8690132e","sessionId":"%s"%sessid,"ipAddress":"%s"%ipaddr,"timestamp":ts,"domain":"music.amazon.com","csrf":{"__type":"SOACoreInterface.v1_0#Csrf","token":"%s"%csrftoken,"ts":"%s"%csrfts,"rnd":"%s"%csrfrnd}},"device":{"__type":"SOACoreInterface.v1_0#DeviceIdentity","id":"%s"%devid,"typeId":"%s"%devtype,"model":"WEBPLAYER","timeZone":"Asia/Calcutta","language":"en_US","height":"668","width":"738","osVersion":"n/a","manufacturer":"n/a"}},"clientStates":{"deeplink":{"url":"%s"%siteurl,"__type":"Podcast.DeeplinkInterface.v1_0#DeeplinkClientState"},"hidePromptPreference":{"preferenceMap":{},"__type":"Podcast.FollowPromptInterface.v1_0#HidePromptPreferenceClientState"}},"extra":{}}
        postdata = json.dumps(datadict).encode('utf-8')
        httpheaders['content-length'] = postdata.__len__()
        self.httprequest = urllib.request.Request("https://music.amazon.com/EU/api/podcast/browse/visual", data=postdata, headers=httpheaders)
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
    
    def __init__(self, client_id, client_secret):
        self.DEBUG = 1
        self.clientid = client_id
        self.clientsecret = client_secret
        self.redirecturi = "https://localhost:8000/"
        self.spotclient = spotipy.Spotify(auth_manager=SpotifyClientCredentials(client_id=client_id, client_secret=client_secret))
        self.proxies = {'http' : [], 'https' : []}
        self.response = None # This would a response object from Amazon API
        self.content = None # This could be a text chunk or a binary data (like a Podcast content)
        self.results = []
        # HTTP(S) request/response and parameters
        self.httprequest = None
        self.httpresponse = None
        self.httpcontent = None
        try:
            self.proxyhandler = urllib.request.ProxyHandler({'http' : self.proxies['http'][0], 'https': self.proxies['https'][0]})
            self.httpopener = urllib.request.build_opener(urllib.request.HTTPHandler(), urllib.request.HTTPSHandler(), self.proxyhandler)
        except:
            self.httpopener = urllib.request.build_opener(urllib.request.HTTPHandler(), urllib.request.HTTPSHandler())
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
            print("Error making request to %s: %s"%(requrl, sys.exc_info()[1].__str__()))
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
        sp_dc="sp_dc=AQAJlPHtM1FpS3VcivEeBLIeIhPvp1oc34uyEitFyyAaSyvXs8MjoEQwArCRtPO9yMkJwr4x9PMsTXj9RGO9VeLnMTX-Z24HrI_bkT6P76p09HTEwS1OqLTHd_ghJpZNKmrwlEiZMoVs8XvU8__qb_RbGwRbrcg5; " # This value is necessary in cookies for valid requests... Needs to be investigated later for finding out how to create it.
        self.httpheaders['cookie'] = "sss=1; sp_m=in-en; _cs_c=0; " + sp_dc + "sp_ab=%7B%222019_04_premium_menu%22%3A%22control%22%7D; spot=%7B%22t%22%3A1660164332%2C%22m%22%3A%22in-en%22%2C%22p%22%3Anull%7D;_sctr=1|1660156200000; OptanonAlertBoxClosed=2022-08-10T20:43:54.163Z;  ki_r=; ki_t=1660164170739%3B1661184464317%3B1661190235932%3B5%3B21; OptanonConsent=isIABGlobal=false&datestamp=" + day + "+" + mon + "+" + str(dd) + "+" + str(year) + "+" + str(hh) + "%3A" + str(mm) + "%3A" + str(ss) + "+GMT%2B0530+(India+Standard+Time)&version=6.26.0&hosts=&landingPath=NotLandingPage&groups=s00%3A1%2Cf00%3A1%2Cm00%3A1%2Ct00%3A1%2Ci00%3A1%2Cf02%3A1%2Cm02%3A1%2Ct02%3A1&AwaitingReconsent=false&geolocation=IN%3BDL; " + self.httpcookies
        #print(self.httpheaders['cookie'])
        


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
            self.httpcontent = None
            return None
        return str(self.httpcontent)


    def existsincontent(self, regexpattern):
        content = self.httpcontent
        if re.search(regexpattern, content):
            return True
        return False


    def getallepisodes(self):
        episodeurlpattern = re.compile("(https\:\/\/open\.spotify\.com\/episode\/[^\"]+)\"", re.DOTALL)
        allepisodeurls = re.findall(episodeurlpattern, str(self.httpcontent))
        return allepisodeurls


    def player(self, uid):
        scope = "user-read-playback-state,user-modify-playback-state"
        spotobj = spotipy.Spotify(client_credentials_manager=SpotifyOAuth(scope=scope, client_id=self.clientid, client_secret=self.clientsecret, redirect_uri=self.redirecturi))
        devices = spotobj.devices()
        spotobj.start_playback(uris=['spotify:track:%s'%uid])


    def getepisodeinfo(self, episodeids, accesstoken):
        clienttoken = self.getclienttoken()
        #print(accesstoken)
        episodeinfourl = "https://api.spotify.com/v1/episodes?ids=%s&market=from_token"%episodeids
        httpheaders = { 'User-Agent' : r'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/88.0.4324.150 Safari/537.36',  'Accept' : '*/*', 'Accept-Language' : 'en-GB,en-US;q=0.9,en;q=0.8', 'Accept-Encoding' : 'gzip,deflate', 'Cache-control' : 'no-cache', 'Connection' : 'keep-alive', 'Pragma' : 'no-cache', 'Referer' : 'https://open.spotify.com/', 'Sec-Fetch-Site' : 'same-site', 'Sec-Fetch-Mode' : 'cors', 'Sec-Fetch-Dest' : 'empty', 'sec-ch-ua-platform' : 'Linux', 'sec-ch-ua-mobile' : '?0', 'sec-ch-ua' : '".Not/A)Brand";v="99", "Google Chrome";v="103", "Chromium";v="103"', 'Origin' : 'https://open.spotify.com', 'Authorization' : "Bearer %s"%accesstoken, 'client-token' : clienttoken}
        epinforequest = urllib.request.Request(episodeinfourl, headers=httpheaders)
        try:
            self.httpresponse = self.httpopener.open(epinforequest)
        except:
            print("Error making episode info request to %s: %s"%(episodeinfourl, sys.exc_info()[1].__str__()))
            return None
        self.httpcontent = _decodeGzippedContent(self.httpresponse.read())
        try:
            episodeinfodict = json.loads(self.httpcontent)
        except:
            print("Error getting episodes info: %s"%sys.exc_info()[1].__str__())
            return []
        episodemp3list = []
        episodes = episodeinfodict['episodes']
        for ep in episodes:
            playbackurl = ep['external_playback_url']
            episodemp3list.append(playbackurl)
        return episodemp3list


    def getclienttoken(self):
        requesturl = "https://clienttoken.spotify.com/v1/clienttoken"
        cid = "d8a5ed958d274c2e8ee717e6a4b0971d" # This ought to be self.clientid
        data = {"client_data":{"client_version":"1.1.93.595.g4dc93539","client_id":"%s"%cid,"js_sdk_data":{"device_brand":"unknown","device_model":"desktop","os":"Linux","os_version":"unknown"}}}
        databytes = json.dumps(data).encode('utf-8')
        httpheaders = { 'User-Agent' : r'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/88.0.4324.150 Safari/537.36',  'Accept' : 'application/json', 'Accept-Language' : 'en-GB,en-US;q=0.9,en;q=0.8', 'Accept-Encoding' : 'gzip,deflate', 'Cache-control' : 'no-cache', 'Connection' : 'keep-alive', 'Pragma' : 'no-cache', 'Referer' : 'https://open.spotify.com/', 'Sec-Fetch-Site' : 'same-site', 'Sec-Fetch-Mode' : 'cors', 'Sec-Fetch-Dest' : 'empty', 'sec-ch-ua-platform' : 'Linux', 'sec-ch-ua-mobile' : '?0', 'sec-ch-ua' : '".Not/A)Brand";v="99", "Google Chrome";v="103", "Chromium";v="103"', 'Content-Type' : 'application/json', 'Origin' : 'https://open.spotify.com'}
        httpheaders['Content-Length'] = databytes.__len__()
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

    def __init__(self):
        self.DEBUG = 1
        self.proxies = {'http' : [], 'https' : []}
        self.response = None # This would a response object from Amazon API
        self.content = None # This could be a text chunk or a binary data (like a Podcast content)
        self.results = []
        # HTTP(S) request/response and parameters
        self.httprequest = None
        self.httpresponse = None
        self.httpcontent = None
        try:
            self.proxyhandler = urllib.request.ProxyHandler({'http' : self.proxies['http'][0], 'https': self.proxies['https'][0]})
            self.httpopener = urllib.request.build_opener(urllib.request.HTTPHandler(), urllib.request.HTTPSHandler(), self.proxyhandler, NoRedirectHandler())
        except:
            self.httpopener = urllib.request.build_opener(urllib.request.HTTPHandler(), urllib.request.HTTPSHandler(), NoRedirectHandler())
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
        


    def searchforpodcasts(self, searchkey, country="us", limit=20):
        podcasts = podsearch.search(searchkey, country=country, limit=limit)


    def makehttprequest(self, requrl):
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
            self.httpcontent = None
            return None
        return str(self.httpcontent)


    def existsincontent(self, regexpattern):
        content = self.httpcontent
        #print(content)
        if re.search(regexpattern, content):
            return True
        return False


    def listpodcastsonpage(self):
        content = self.httpcontent
        soup = BeautifulSoup(content, features="html.parser")
        allanchortags = soup.find_all("a", {'class' : 'link tracks__track__link--block'})
        podcastlinks = []
        for atag in allanchortags:
            alink = atag['href']
            podcastlinks.append(alink)
        return podcastlinks


    def downloadpodcast(self, podcastpagelink):
        self.makehttprequest(podcastpagelink)
        content = self.gethttpresponsecontent()
        content = content.replace("\\", "")
        assetpattern = re.compile('\"assetUrl\":\"([^\"]+)\"', re.DOTALL)
        aps = re.search(assetpattern, content)
        resourceurl = ""
        if aps:
            resourceurl = aps.groups()[0]
        #print("Resource URL: %s"%resourceurl)
        self.httprequest = urllib.request.Request(resourceurl, headers=self.httpheaders)
        try:
            self.httpresponse = self.httpopener.open(self.httprequest)
        except:
            print("Error making request to %s: %s"%(requrl, sys.exc_info()[1].__str__()))
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
            dumpfile = "dumps/apple_" + t + ".mp3"
            fp = open(dumpfile, "wb")
            fp.write(mediacontent)
            fp.close()
        return mediacontent


class BuzzBot(object):
    
    def __init__(self, podlisturl, amazonkey, spotifyclientid, spotifyclientsecret, proxieslist=[]):
        self.DEBUG = 1
        self.proxies = {'http' : [], 'https' : proxieslist,}
        self.amazonkey = amazonkey
        self.spotifyclientid = spotifyclientid
        self.spotifyclientsecret = spotifyclientsecret
        self.results = []
        # HTTP(S) request/response and parameters
        self.httprequest = None
        self.httpresponse = None
        self.httpcontent = None
        try:
            self.proxyhandler = urllib.request.ProxyHandler({'http' : self.proxies['http'][0], 'https': self.proxies['https'][0]})
            self.httpopener = urllib.request.build_opener(urllib.request.HTTPHandler(), urllib.request.HTTPSHandler(), self.proxyhandler)
        except:
            self.httpopener = urllib.request.build_opener(urllib.request.HTTPHandler(), urllib.request.HTTPSHandler())
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
        

    def makerequest(self):
        self.httprequest = urllib.request.Request(self.requesturl, headers=self.httpheaders)
        try:
            self.httpresponse = self.httpopener.open(self.httprequest)
        except:
            print("Error making request to %s: %s"%(requrl, sys.exc_info()[1].__str__()))
            return None
        self.httpcookies = self.__class__._getCookieFromResponse(self.httpresponse)
        self.httpheaders["cookie"] = self.httpcookies
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
            self.httpcontent = None
            return None
        return str(self.httpcontent)


    def getpodcasturls(self):
        content = self.httpcontent
        soup = BeautifulSoup(content, features="html.parser")
        podcastsites = ['apple', 'google', 'amazon', 'spotify', 'overcast', 'stitcher', 'iheart', 'tun.in', 'podcastaddict', 'castro', 'castbox', 'podchaser', 'pcs.st', 'deezer', 'listennotes', 'player.fm', 'podcastindex', 'podfriend', 'buzzsprout']
        self.results = {}
        if not soup:
            print("Error getting html content: %s"%sys.exc_info()[1].__str__())
            return self.results
        h1tag = soup.find("h1")
        h1contents = h1tag.renderContents().decode('utf-8')
        self.podcasttitle = h1contents
        self.podcasttitle = self.podcasttitle.replace("\n", "").replace("\r", "")
        sectiontag = soup.find("section", {'class' : 'p-8'})
        allanchors = []
        if sectiontag is not None:
            allanchors = sectiontag.find_all("a")
        else:
            print("Could not find the anchor tags for podcasts URLs")
            return self.results
        for anchor in allanchors:
            if anchor is not None and 'href' in str(anchor):
                podcasturl = anchor['href']
                for podsite in podcastsites:
                    if podsite in podcasturl:
                        self.results[podsite] = podcasturl
                    else:
                        pass
        return self.results


    def hitpodcast(self, siteurl, sitename):
        titleregex = makeregex(self.podcasttitle)
        apikey = self.amazonkey
        clientid = self.spotifyclientid
        clientsecret = self.spotifyclientsecret
        if sitename.lower() == "apple":
            applebot = AppleBot()
            applebot.makehttprequest(siteurl)
            applebot.gethttpresponsecontent()
            podcastlinks = applebot.listpodcastsonpage()
            for pclink in podcastlinks:
                resp = applebot.downloadpodcast(pclink)
            # Check to see if self.podcasttitle exists in the retrieved content
            boolret = applebot.existsincontent(titleregex)
            if "apple" in self.hitstatus.keys():
                self.hitstatus['apple'].append(boolret)
            else:
                self.hitstatus['apple'] = []
                self.hitstatus['apple'].append(boolret)
        elif sitename.lower() == "spotify":
            spotbot = SpotifyBot(clientid, clientsecret) # Get this from the environment
            #print("Spotify: %s"%siteurl)
            spotbot.makehttprequest(siteurl)
            spotbot.gethttpresponsecontent()
            episodeurls = spotbot.getallepisodes()
            episodeidlist = []
            episodeurlpattern = re.compile("https\:\/\/open\.spotify\.com\/episode\/([^\"]+)$")
            for epurl in episodeurls:
                eps = re.search(episodeurlpattern, epurl)
                if eps:
                    epid = eps.groups()[0]
                    episodeidlist.append(epid)
            episodeids = ",".join(episodeidlist)
            #print(episodeurls)
            clientid, accesstoken = "", ""
            clientidpattern = re.compile("\"clientId\"\:\"([^\"]+)\"", re.DOTALL)
            accesstokenpattern = re.compile("\"accessToken\"\:\"([^\"]+)\",", re.DOTALL)
            cps = re.search(clientidpattern, spotbot.httpcontent)
            aps = re.search(accesstokenpattern, spotbot.httpcontent)
            if cps:
                clientid = cps.groups()[0]
            if aps:
                accesstoken = aps.groups()[0]
            episodemp3list = spotbot.getepisodeinfo(episodeids, accesstoken)
            httpheaders = {}
            # Get the episodes...
            for epurl in episodemp3list:
                content = spotbot.getepisode(epurl)
                print(epurl)
                t = str(int(time.time() * 1000))
                fs = open("dumps/spotify_%s.mp3"%t, "wb")
                fs.write(content)
                fs.close()
            # Check to see if self.podcasttitle exists in the retrieved content
            boolret = spotbot.existsincontent(titleregex)
            if "spotify" in self.hitstatus.keys():
                self.hitstatus['spotify'].append(boolret)
            else:
                self.hitstatus['spotify'] = []
                self.hitstatus['spotify'].append(boolret)
        elif sitename.lower() == "amazon":
            ambot = AmazonBot(apikey) # Get this from the environment
            print("Amazon: %s"%siteurl)
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
            datadict = ambot.getvisualdict(paramstuple)
            print(datadict)
            # Check to see if self.podcasttitle exists in the retrieved content
            boolret = ambot.existsincontent(titleregex)
            if "amazon" in self.hitstatus.keys():
                self.hitstatus['amazon'].append(boolret)
            else:
                self.hitstatus['amazon'] = []
                self.hitstatus['amazon'].append(boolret)
        else:
            return False
        return boolret



class GUI(object):

    def __init__(self):
        self.emptystringpattern = re.compile("^\s*$")
        self.httppattern = re.compile("^https?", re.IGNORECASE)
        self.amazonkey = ""
        self.spotifyclientid = ""
        self.spotifyclientsecret = ""
        self.mainwin = Tk()

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
        self.runbutton = Button(self.mainwin, text="Start Bot", command=self.startbot)
        self.runbutton.grid(row=6, column=0)
        self.stopbutton = Button(self.mainwin, text="Stop Bot", command=self.stopbot)
        self.stopbutton.grid(row=6, column=1)
        self.closebutton = Button(self.mainwin, text="Close Window", command=self.closebot)
        self.closebutton.grid(row=6, column=2)
        self.messagelabel = Message(self.mainwin, textvariable=self.msglabeltext, bg="white", width=400, relief=SUNKEN)
        self.messagelabel.grid(row=7, columnspan=3)
        
        self.buzz = None
        self.threadslist = []
        self.rt = None
        self.proxieslist = []

        self.mainwin.mainloop()


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
        self.httpspattern = re.compile("^https\:\/\/", re.IGNORECASE)
        for line in proxieslines:
            if not re.search(self.httpspattern, line):
                continue
            self.proxieslist.append(line)
        # Start bot in a background thread...
        self.rt = Thread(target=self.runbot, args=(self.targeturl,))
        self.rt.daemon = True
        self.rt.start()
        self.messagelabel.configure(foreground="green", width=400)
        self.msglabeltext.set("Operation in progress...")
        # ... and return to user
        return True


    def runbot(self, targeturl):
        self.buzz = BuzzBot(targeturl, self.amazonkey, self.spotifyclientid, self.spotifyclientsecret, self.proxieslist)
        self.buzz.makerequest()
        self.buzz.gethttpresponsecontent()
        urlsdict = self.buzz.getpodcasturls()
        self.threadslist = []
        for sitename in urlsdict.keys():
            siteurl = urlsdict[sitename]
            t = Thread(target=self.buzz.hitpodcast, args=(siteurl, sitename,))
            t.daemon = True
            t.start()
            self.threadslist.append(t)
        time.sleep(2) # sleep 2 seconds.
        for tj in self.threadslist:
            tj.join()
        for site in self.buzz.hitstatus.keys():
            if self.buzz.hitstatus[site].__len__() > 0:
                self.messagelabel.configure(foreground="green", width=400)
                self.msglabeltext.set("%s : %s"%(site, self.buzz.hitstatus[site][0]))
        self.messagelabel.configure(foreground="blue", width=400)
        self.msglabeltext.set("Finished hitting targets.")
        return True


    def closebot(self):
        if self.rt is not None:
            self.rt.join()
        sys.exit()


    def stopbot(self):
        if self.rt is not None:
            self.rt.join()
        return None


if __name__ == "__main__":
    gui = GUI()

    """
    # Amazon
    amazonapikey = "c3f9d26365604d04affad02432e9be68"
    spotifyid = sys.argv[2]
    spotifysecret = sys.argv[3]
    amazon = AmazonBot(amazonapikey)
    amazon.searchforpodcasts(searchkey)
    amazon.parsecontent(reqtype='search')
    print(amazon.results[1]['podcastid'])
    amazon.fetchpodcastbyId(amazon.results[1]['podcastid'])
    amazon.parsecontent(reqtype='podcast')
    print("First episode Id: %s"%amazon.results[0]['id'])
    amazon.fetchpodcastepisodebyId(amazon.results[0]['id'])
    amazon.parsecontent(reqtype='episode')
    print("First episode link: %s"%amazon.results[0]['link'])
    print("First episode URL: %s"%amazon.results[0]['urls'][0])
    print("First episode listennotes: %s"%amazon.results[0]['listennotes'])
    listennotesurl = str(amazon.results[0]['listennotes'])
    title = str(amazon.results[0]['title'])
    amazon.makehttprequest(listennotesurl)
    podcastcontent = amazon.gethttpresponsecontent()
    titleregex = makeregex(title)
    if re.search(titleregex, podcastcontent):
        print("Amazon: Hit the page successfully")
    else:
        print("Probably did not get the page correctly")
    #fp = open("dumpamazonpodcast.html", "w")
    #fp.write(podcastcontent)
    #fp.close()
    # Spotify
    spotifybot = SpotifyBot(spotifyid, spotifysecret)
    spotifybot.searchforpodcasts(searchkey)
    #print("First Album URL: %s"%spotifybot.results[0]['albumspotifyurl'])
    #print("First Item URL: %s"%spotifybot.results[0]['itemspotifyurl'])
    #print("First Album ID: %s"%spotifybot.results[0]['albumid'])
    #print("First Item ID: %s"%spotifybot.results[0]['itemid'])
    spotifybot.makehttprequest(spotifybot.results[0]['itemspotifyurl'])
    itemcontent = spotifybot.gethttpresponsecontent()
    searchkeyregex = makeregex(searchkey)
    found = 0
    for spotres in spotifybot.results:
        spotifybot.makehttprequest(spotres['itemspotifyurl'])
        itemcontent = spotifybot.gethttpresponsecontent()
        if re.search(searchkeyregex, itemcontent):
            print("Found podcast on spotify")
            found = 1
            print(spotres['albumspotifyurl'])
            print(spotres['itemspotifyurl'])
            break
    if not found:
        print("Could not find the podcast on spotify")
    #fp = open("dumpspotifyitem.html", "w")
    #fp.write(itemcontent)
    #fp.close()
    """


"""
References:
https://github.com/ListenNotes/podcast-api-python
https://www.listennotes.com/podcast-api/docs/?test=1
https://music.amazon.com/podcasts/e934affd-05e2-48d5-8236-6b7f2d02e5e2

Developer: Supriyo Mitra
Date: 11-08-2022
"""


