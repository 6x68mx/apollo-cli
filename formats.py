"""
Copyright 2018 6x68mx <6x68mx@gmail.com>

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

class FormatFlac():
    NAME = "FLAC"
    FORMAT = "FLAC"
    BITRATE = "Lossless"
    SUFFIX = ".flac"

    def encode_cmd(dst):
        return ["flac", "--best", "-o", dst, "-"]

def lame_cmd(dst, opts):
    return ["lame", "-S", *opts, "-", dst]

class Format320:
    NAME = "320"
    FORMAT = "MP3"
    BITRATE = "320"
    SUFFIX = ".mp3"

    def encode_cmd(dst):
        return lame_cmd(dst, ["-h", "-b", "320", "--ignore-tag-errors"])

class FormatV0:
    NAME = "V0"
    FORMAT = "MP3"
    BITRATE = "V0 (VBR)"
    SUFFIX = ".mp3"

    def encode_cmd(dst):
        return lame_cmd(dst, ["-V", "0", "--vbr-new", "--ignore-tag-errors"])

class FormatV2:
    NAME = "V2"
    FORMAT = "MP3"
    BITRATE = "V2 (VBR)"
    SUFFIX = ".mp3"

    def encode_cmd(dst):
        return lame_cmd(dst, ["-V", "2", "--vbr-new", "--ignore-tag-errors"])

FORMATS = {
        FormatFlac,
        Format320,
        FormatV0,
        FormatV2
}
