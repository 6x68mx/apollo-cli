
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

FORMATS = (
        FormatFlac,
        Format320,
        FormatV0,
        FormatV2
)
