import os, sys, re, time
import string

"""
These routines have been sourced from stackoverflow responses.
Specifically, the following post has been referred to: 
https://stackoverflow.com/questions/1119722/base-62-conversion
Credits: https://stackoverflow.com/users/355230/martineau and https://stackoverflow.com/users/8024/baishampayan-ghose
"""

BASE62 = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
# Remove the `_@` below for base62, now it has 64 characters
"""
BASE_LIST = string.digits + string.letters + '_@'
BASE_DICT = dict((c, i) for i, c in enumerate(BASE_LIST))

def base_decode(string, reverse_base=BASE_DICT):
    length = len(reverse_base)
    ret = 0
    for i, c in enumerate(string[::-1]):
        ret += (length ** i) * reverse_base[c]

    return ret

def base_encode(integer, base=BASE_LIST):
    if integer == 0:
        return base[0]

    length = len(base)
    ret = ''
    while integer != 0:
        ret = base[integer % length] + ret
        integer /= length

    return ret
"""


def decode62(string, alphabet=BASE62):
    """Decode a Base X encoded string into the number

    Arguments:
    - `string`: The encoded string
    - `alphabet`: The alphabet to use for decoding
    """
    base = len(alphabet)
    strlen = len(string)
    num = 0

    idx = 0
    for char in string:
        power = (strlen - (idx + 1))
        num += alphabet.index(char) * (base ** power)
        idx += 1

    return num


if __name__ == "__main__":
    s = sys.argv[1]
    print(decode62(s))

