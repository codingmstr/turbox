import os, magic

class Checker:

    def __init__ ( self ):

        self.magic = magic.Magic(mime=True)

        self.executable_ext = [
            ".exe", ".msi", ".bat", ".cmd", ".sh"
        ]

        self.executable_types = [
            "application/x-executable",
            "application/x-mach-binary",
            "application/x-msdos-program",
            "application/x-msdownload",
            "application/vnd.microsoft.portable-executable",
            "application/x-elf",
            "application/x-dosexec",
            "application/x-elf-shared-object",
            "application/x-sharedlib",
            "application/x-object",
            "application/x-pie-executable",
            "application/x-staticlib",
            "application/x-appimage",
            "application/x-gameboy-rom",
            "application/x-nintendo-nes-rom",
            "application/x-ms-shortcut",
            "application/vnd.android.package-archive",
            "application/x-msdos-batch",
            "application/x-shellscript",
            "application/x-python-script",
            "application/x-ms-wim",
            "application/octet-stream",
        ]

        self.compressed_types = [
            "application/zip",
            "application/x-tar",
            "application/x-gzip",
            "application/gzip",
            "application/x-bzip2",
            "application/x-xz",
            "application/x-lzma",
            "application/x-arj",
            "application/x-lzx",
            "application/x-xar",
            "application/x-cpio",
            "application/x-rpm",
            "application/x-compress",
            "application/x-7z",
            "application/x-7z-compressed",
            "application/x-rar",
            "application/x-rar-compressed",
            "application/vnd.ms-cab",
            "application/vnd.ms-cab-compressed",
            "application/x-ace",
            "application/x-ace-compressed",
            "application/x-lzh",
            "application/x-lzh-compressed",
        ]

    def mime_type ( self, path: str ):

        try: return self.magic.from_file(path)
        except: return ''

    def extension ( self, path: str ):

        _, extension = os.path.splitext(path)
        return str(extension).lstrip('.')

    def empty ( self, path: str ):

        return not os.stat(path).st_size

    def document ( self, path: str ):

        return 'text/plain' in self.mime_type(path)

    def pdf ( self, path: str ):

        return 'pdf' in self.mime_type(path)

    def csv ( self, path: str ):

        return 'csv' in self.mime_type(path) or path.endswith('.csv')

    def word ( self, path: str ):

        return 'word' in self.mime_type(path) or 'wordprocessingml.document' in self.mime_type(path)

    def excel ( self, path: str ):

        return 'excel' in self.mime_type(path) or 'spreadsheetml.sheet' in self.mime_type(path)

    def ppoint ( self, path: str ):

        return 'powerpoint' in self.mime_type(path) or 'presentationml.presentation' in self.mime_type(path)

    def image ( self, path: str ):

        return 'image' in self.mime_type(path)

    def audio ( self, path: str ):

        return 'audio' in self.mime_type(path)

    def video ( self, path: str ):

        return 'video' in self.mime_type(path)

    def archive ( self, path: str ):

        return self.mime_type(path) in self.compressed_types

    def executable ( self, path: str ):

        return self.mime_type(path) in self.executable_types or str(os.path.splitext(path)[1]).lower() in self.executable_ext

    def type ( self, path: str ):

        methods = [
            ('pdf', self.pdf),
            ('csv', self.csv),
            ('word', self.word),
            ('excel', self.excel),
            ('ppoint', self.ppoint),
            ('image', self.image),
            ('audio', self.audio),
            ('video', self.video),
            ('archive', self.archive),
            ('executable', self.executable),
            ('document', self.document),
        ]
        
        for file_type, method in methods:
            if method(path): return file_type

        return self.mime_type(path).split('/')[0]
