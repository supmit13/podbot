#!/usr/local/bin/node
// Spotify's code to compute the gid of the track entity.
// This has been inspired and created by looking at spotify's
// javascript code library. - supmit.

var t="0123456789abcdef",n="0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ",o=[];o.length=256;for(var i=0;i<256;i++)o[i]=t[i>>4]+t[15&i];var r=[];r.length=128;for(i=0;i<n.length;++i)r[n.charCodeAt(i)]=i;var a=[];for(i=0;i<16;i++)a[t.charCodeAt(i)]=i;for(i=0;i<6;i++)a["ABCDEF".charCodeAt(i)]=10+i;

function toHex(e){if(22!==e.length)return null;var t,n,i,a,s,l=2.3283064365386963e-10,c=4294967296,u=238328;return t=56800235584*r[e.charCodeAt(0)]+916132832*r[e.charCodeAt(1)]+14776336*r[e.charCodeAt(2)]+238328*r[e.charCodeAt(3)]+3844*r[e.charCodeAt(4)]+62*r[e.charCodeAt(5)]+r[e.charCodeAt(6)],t=(t-=(n=t*l|0)*c)*u+(s=3844*r[e.charCodeAt(7)]+62*r[e.charCodeAt(8)]+r[e.charCodeAt(9)]),t-=(s=t*l|0)*c,n=n*u+s,t=t*u+(s=3844*r[e.charCodeAt(10)]+62*r[e.charCodeAt(11)]+r[e.charCodeAt(12)]),t-=(s=t*l|0)*c,n=n*u+s,n-=(s=n*l|0)*c,i=s,t=t*u+(s=3844*r[e.charCodeAt(13)]+62*r[e.charCodeAt(14)]+r[e.charCodeAt(15)]),t-=(s=t*l|0)*c,n=n*u+s,n-=(s=n*l|0)*c,i=i*u+s,t=t*u+(s=3844*r[e.charCodeAt(16)]+62*r[e.charCodeAt(17)]+r[e.charCodeAt(18)]),t-=(s=t*l|0)*c,n=n*u+s,n-=(s=n*l|0)*c,i=i*u+s,i-=(s=i*l|0)*c,a=s,t=t*u+(s=3844*r[e.charCodeAt(19)]+62*r[e.charCodeAt(20)]+r[e.charCodeAt(21)]),t-=(s=t*l|0)*c,n=n*u+s,n-=(s=n*l|0)*c,i=i*u+s,i-=(s=i*l|0)*c,a=a*u+s,a-=(s=a*l|0)*c,s?null:o[a>>>24]+o[a>>>16&255]+o[a>>>8&255]+o[255&a]+o[i>>>24]+o[i>>>16&255]+o[i>>>8&255]+o[255&i]+o[n>>>24]+o[n>>>16&255]+o[n>>>8&255]+o[255&n]+o[t>>>24]+o[t>>>16&255]+o[t>>>8&255]+o[255&t]}

idtohex = function(e){return 22==e.length?toHex(e):e}
console.log(idtohex("####TRACK_ID####"));


