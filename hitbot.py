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

# Amazon APIs
import boto3
from listennotes import podcast_api

# Spotify APIs
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials

# Apple Podcasts library
import podsearch



class AmazonBot(object):
    
    def __init__(self, apikey):
        self.apikey = apikey
        self.proxies = {'http' : [], 'https' : []}
        self.response = None # This would a response object from Amazon API
        self.content = None # This could be a text chunk or a binary data (like a Podcast content)
        self.podclient = podcast_api.Client(api_key=self.apikey)
        self.results = []
        # HTTP(S) request/response and parameters
        self.httprequest = None
        self.httpresponse = None
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


    def makerequest(self, reqidentifier):
        pass


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
                        title = rd['title_original']
                    except:
                        title = ""
                    try:
                        itunesid = rd['itunes_id']
                    except:
                        itunesid = ""
                    d = {'link' : link, 'audio' : 'audio', 'listennotesurl' : listennotes, 'title' : title, 'itunesid' : itunesid}
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




class SpotifyBot(object):
    
    def __init__(self, client_id, client_secret):
        self.clientid = client_id
        self.clientsecret = client_secret
        self.spotclient = spotipy.Spotify(auth_manager=SpotifyClientCredentials(client_id=client_id, client_secret=client_secret))
        self.proxies = {'http' : [], 'https' : []}
        self.response = None # This would a response object from Amazon API
        self.content = None # This could be a text chunk or a binary data (like a Podcast content)
        self.results = []
        # HTTP(S) request/response and parameters
        self.httprequest = None
        self.httpresponse = None
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


    def searchforpodcasts(self, searchkey, limit=20):
        self.response = self.spotclient.search(q=searchkey, limit=limit)
        self.content = self.response
        url = self.response['tracks']['href']
        items = self.response['tracks']['items']




class AppleBot(object):

    def __init__(self):
        self.proxies = {'http' : [], 'https' : []}
        self.response = None # This would a response object from Amazon API
        self.content = None # This could be a text chunk or a binary data (like a Podcast content)
        self.results = []
        # HTTP(S) request/response and parameters
        self.httprequest = None
        self.httpresponse = None
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


    def searchforpodcasts(self, searchkey, country="us", limit=20):
        podcasts = podsearch.search(searchkey, country=country, limit=limit)




if __name__ == "__main__":
    """
    amazonapikey = "c3f9d26365604d04affad02432e9be68"
    amazon = AmazonBot(amazonapikey)
    """
    spotifyid = sys.argv[1]
    spotifysecret = sys.argv[2]
    searchtext = sys.argv[3] # "Star Wars"
    spotifybot = SpotifyBot(spotifyid, spotifysecret)
    spotifybot.searchforpodcasts(searchtext)



"""
References:
https://github.com/ListenNotes/podcast-api-python
https://www.listennotes.com/podcast-api/docs/?test=1
https://music.amazon.com/podcasts/e934affd-05e2-48d5-8236-6b7f2d02e5e2

Developer: Supriyo Mitra
Date: 11-08-2022
"""


