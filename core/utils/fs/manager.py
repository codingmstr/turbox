from pydrive2.auth import GoogleAuth
from pydrive2.drive import GoogleDrive
from tqdm import tqdm
from typing import Any
import os, uuid, boto3, mimetypes, ftplib, dropbox, time

class FTP:

    def __init__ ( self ):

        self.ftp = None

    def connect ( self, credentials: dict, options: dict = {} ):

        host = credentials.get('host')
        user = credentials.get('user')
        pwd  = credentials.get('password')
        port = credentials.get('port', 21)

        base_dir = options.get('base_dir', '/')
        timeout  = options.get('timeout', 30)

        self.ftp = ftplib.FTP()
        self.ftp.connect(host, port, timeout=timeout)
        self.ftp.login(user, pwd)
        self.ftp.cwd(base_dir)

        return self

    def _makedirs ( self, remote_path: str ):

        dirs = remote_path.strip('/').split('/')

        for i in range(len(dirs)):
            subdir = '/'.join(dirs[:i + 1])

            try: self.ftp.mkd(subdir)
            except: pass

    def upload_file ( self, local_path: str, remote_path: str = None ):

        remote_path = remote_path or os.path.basename(local_path)
        self._makedirs(os.path.dirname(remote_path))

        total = os.path.getsize(local_path)
        bar   = tqdm(total=total, unit='B', unit_scale=True, desc=f"Uploading {remote_path}")

        with open(local_path, 'rb') as f:

            def callback(data): bar.update(len(data))
            self.ftp.storbinary(f'STOR {remote_path}', f, 8192, callback)

        bar.close()
        return f"ftp://{self.host}/{remote_path}"

    def download_file ( self, remote_path: str, local_path: str = None ):

        local_path = local_path or os.path.basename(remote_path)
        os.makedirs(os.path.dirname(local_path) or '.', exist_ok=True)

        size = self.ftp.size(remote_path)
        bar  = tqdm(total=size, unit='B', unit_scale=True, desc=f"Downloading {remote_path}")

        with open(local_path, 'wb') as f:

            def callback(data):
                f.write(data)
                bar.update(len(data))

            self.ftp.retrbinary(f'RETR {remote_path}', callback)

        bar.close()
        return os.path.abspath(local_path)

    def upload_folder ( self, local_path: str, remote_path: str = None, **kwargs ):

        uploaded = []
        remote_path = remote_path or os.path.basename(local_path)

        files = [os.path.join(root, file) for root, _, files in os.walk(local_path) for file in files]
        bar = tqdm(total=len(files), desc="FTP Upload Folder")

        for file in files:

            rel_path = os.path.relpath(file, local_path).replace("\\", "/")
            dest = f"{remote_path}/{rel_path}"

            uploaded.append(self.upload_file(file, dest))
            bar.update(1)

            if callback := kwargs.get('callback'): callback(uploaded[-1])

        bar.close()
        return uploaded

    def download_folder ( self, remote_path: str, local_path: str = None, **kwargs ):

        local_path = local_path or os.path.basename(remote_path)
        os.makedirs(local_path, exist_ok=True)

        downloaded = []
        listing = self.ftp.nlst(remote_path)
        bar = tqdm(total=len(listing), desc="FTP Download Folder")

        for item in listing:

            local_file = os.path.join(local_path, os.path.basename(item))

            downloaded.append(self.download_file(item, local_file))
            bar.update(1)

            if callback := kwargs.get('callback'): callback(downloaded[-1])

        bar.close()
        return downloaded

class GDrive:

    def __init__ ( self, **kwargs ):

        self.drive     = None
        self.folder_id = None

    def connect ( self, credentials: dict, options: dict = {} ):

        self.folder_id = credentials.get('folder_id', options.get('folder_id'))

        gauth = GoogleAuth()
        gauth.LoadCredentialsFile(credentials)

        if not gauth.credentials or gauth.access_token_expired:
            gauth.LocalWebserverAuth()
            gauth.SaveCredentialsFile(credentials)

        self.drive = GoogleDrive(gauth)
        return self

    def upload_file ( self, local_path: str, remote_path: str = None ):

        remote_name = os.path.basename(remote_path or local_path)

        file = self.drive.CreateFile({
            'title': remote_name,
            'parents': [{'id': self.folder_id}] if self.folder_id else []
        })

        total = os.path.getsize(local_path)
        bar = tqdm(total=total, unit='B', unit_scale=True, desc=f"Uploading {remote_name}")

        def progress(cur, total_bytes): bar.update(cur - bar.n)

        file.SetContentFile(local_path)
        file.Upload(param={'progress_callback': progress})

        bar.close()
        return f"gdrive:{file['id']}"

    def download_file ( self, remote_id: str, local_path: str = None ):

        local_path = local_path or f"{remote_id}.bin"
        os.makedirs(os.path.dirname(local_path) or '.', exist_ok=True)

        file = self.drive.CreateFile({'id': remote_id})
        size = int(file.metadata.get('fileSize', 0)) if hasattr(file, 'metadata') else 0
        bar = tqdm(total=size, unit='B', unit_scale=True, desc=f"Downloading {remote_id}")

        file.GetContentFile(local_path, callback=lambda c, t: bar.update(c - bar.n))

        bar.close()
        return os.path.abspath(local_path)

    def upload_folder ( self, local_path: str, remote_path: str = None, **kwargs ):

        uploaded = []
        remote_path = remote_path or os.path.basename(local_path)

        files = [os.path.join(root, file) for root, _, files in os.walk(local_path) for file in files]
        bar = tqdm(total=len(files), desc="GDrive Upload Folder")

        for file in files:
            uploaded.append(self.upload_file(file))
            bar.update(1)
            if callback := kwargs.get('callback'): callback(uploaded[-1])

        bar.close()
        return uploaded

    def download_folder ( self, remote_folder_id: str, local_path: str = None, **kwargs ):

        query = f"'{remote_folder_id}' in parents and trashed=false"
        file_list = self.drive.ListFile({'q': query}).GetList()

        local_path = local_path or 'downloads'
        os.makedirs(local_path, exist_ok=True)

        downloaded = []
        bar = tqdm(total=len(file_list), desc="GDrive Download Folder")

        for file in file_list:

            dest = os.path.join(local_path, file['title'])

            downloaded.append(self.download_file(file['id'], dest))
            bar.update(1)

            if callback := kwargs.get('callback'): callback(downloaded[-1])

        bar.close()
        return downloaded

class Dropbox:

    def __init__ ( self ):

        self.dbx = None

    def connect ( self, credentials: dict, options: dict = {} ):

        token = credentials.get('token')
        if not token: raise ValueError("Dropbox token missing.")

        self.dbx = dropbox.Dropbox(token)
        return self

    def upload_file ( self, local_path: str, remote_path: str = None ):

        remote_path = remote_path or '/' + os.path.basename(local_path)
        total = os.path.getsize(local_path)
        bar   = tqdm(total=total, unit='B', unit_scale=True, desc=f"Uploading {remote_path}")

        with open(local_path, 'rb') as f:

            CHUNK_SIZE = 4 * 1024 * 1024
            session = self.dbx.files_upload_session_start(f.read(CHUNK_SIZE))

            cursor = dropbox.files.UploadSessionCursor(session_id=session.session_id, offset=f.tell())
            commit = dropbox.files.CommitInfo(path=remote_path, mode=dropbox.files.WriteMode.overwrite)

            while chunk := f.read(CHUNK_SIZE):
                self.dbx.files_upload_session_append_v2(chunk, cursor)
                cursor.offset += len(chunk)
                bar.update(len(chunk))

            self.dbx.files_upload_session_finish(b'', cursor, commit)

        bar.close()
        return f"dropbox:{remote_path}"

    def download_file ( self, remote_path: str, local_path: str = None ):

        local_path = local_path or os.path.basename(remote_path)
        os.makedirs(os.path.dirname(local_path) or '.', exist_ok=True)

        md = self.dbx.files_get_metadata(remote_path)
        total = md.size
        bar = tqdm(total=total, unit='B', unit_scale=True, desc=f"Downloading {remote_path}")

        _, res = self.dbx.files_download(remote_path)

        with open(local_path, 'wb') as f:
            for chunk in res.iter_content(chunk_size=8192):
                if not chunk: break
                f.write(chunk)
                bar.update(len(chunk))

        bar.close()
        return os.path.abspath(local_path)

    def upload_folder ( self, local_path: str, remote_path: str = None, **kwargs ):

        uploaded = []
        remote_path = remote_path or os.path.basename(local_path)
        files = [os.path.join(root, file) for root, _, files in os.walk(local_path) for file in files]
        bar = tqdm(total=len(files), desc="Dropbox Upload Folder")

        for file in files:

            rel_path = os.path.relpath(file, local_path).replace("\\", "/")
            dest = f"{remote_path}/{rel_path}"

            uploaded.append(self.upload_file(file, dest))
            bar.update(1)

            if callback := kwargs.get('callback'): callback(uploaded[-1])

        bar.close()
        return uploaded

    def download_folder ( self, remote_path: str, local_path: str = None, **kwargs ):

        local_path = local_path or os.path.basename(remote_path)
        os.makedirs(local_path, exist_ok=True)

        res = self.dbx.files_list_folder(remote_path, recursive=True)
        entries = [e.path_lower for e in res.entries if isinstance(e, dropbox.files.FileMetadata)]

        bar = tqdm(total=len(entries), desc="Dropbox Download Folder")
        downloaded = []

        for entry in entries:

            rel = entry[len(remote_path):].lstrip('/')
            dest = os.path.join(local_path, rel)

            downloaded.append(self.download_file(entry, dest))
            bar.update(1)

            if callback := kwargs.get('callback'): callback(downloaded[-1])

        bar.close()
        return downloaded

class S3:
  
    def __init__ ( self ):

        self.bucket = None
        self.public = True
        self.unique = False

    def connect ( self, credentials: dict, options: dict = {} ):

        access_key = credentials.get('access_key', '')
        secret_key = credentials.get('secret_key', '')

        self.bucket = credentials.get('bucket_name', '')
        self.public = options.get('public', True)
        self.unique = options.get('unique', False)

        if not all([access_key, secret_key]): raise ValueError("Missing AWS credentials !")

        self.session = boto3.session.Session()
        self.client = self.session.client('s3', aws_access_key_id=access_key, aws_secret_access_key=secret_key)
    
        return self

    def content_type ( self, local_path: str ):

        content_type, _ = mimetypes.guess_type(local_path)

        if not content_type: content_type = "application/octet-stream"
        return content_type

    def create_local_path ( self, local_path: str ):

        path = local_path or ''
        local_dir = os.path.abspath(os.path.dirname(path))

        os.makedirs(local_dir, exist_ok=True)
        return os.path.join(local_dir, os.path.basename(path))

    def check_remote_file ( self, remote_path: str ):

        try: return bool(self.client.head_object(Bucket=self.bucket, Key=remote_path))
        except self.client.exceptions.ClientError as e: return e.response['Error']['Code'] != "404"
        except: return False

    def unique_filename ( self, remote_path: str ):

        name, ext = os.path.splitext(remote_path)
        timestamp = uuid.uuid4().hex[:8]
        return f"{name}_{timestamp}{ext}"

    def upload_file ( self, local_path: str, remote_path: str = None ):

        remote_path = remote_path or os.path.basename(local_path)
        if self.unique: remote_path = self.unique_filename(remote_path)

        args = {'ContentType': self.content_type(local_path)}
        if self.public: args['ACL'] = 'public-read'

        self.client.upload_file(local_path, self.bucket, remote_path, ExtraArgs=args)
        return f"https://{self.bucket}.s3.amazonaws.com/{remote_path}"

    def download_file ( self, remote_path: str, local_path: str = None ):

        local_path = self.create_local_path(local_path or os.path.basename(remote_path))
        self.client.download_file(self.bucket, remote_path, local_path)
        return local_path

    def upload_folder ( self, local_path: str, remote_path: str = None, **kwargs: Any ):

        if not os.path.isdir(local_path): return self.upload_file(local_path, remote_path)

        uploaded     = []
        remote_path  = remote_path or os.path.basename(local_path)
        files        = [os.path.join(root, file) for root, _, files in os.walk(local_path) for file in files]
        progress_bar = tqdm(total=len(files), desc="Uploading")

        for file in files:

            s3_path = f"{remote_path}/{os.path.relpath(file, local_path)}".replace("\\", "/")
            uploaded_path = self.upload_file(file, s3_path)

            uploaded.append(uploaded_path)
            progress_bar.update(1)

            callback = kwargs.get('callback')
            if callback: callback(uploaded_path)

        return uploaded

    def download_folder ( self, remote_path: str, local_path: str = None, **kwargs: Any ):

        path = local_path or os.path.basename(remote_path)
        paginator = self.client.get_paginator('list_objects_v2')
        downloaded = []
     
        files = [
            obj['Key']
            for page in paginator.paginate(Bucket=self.bucket, Prefix=remote_path)
            if 'Contents' in page for obj in page['Contents']
        ]

        progress_bar = tqdm(total=len(files), desc="Downloading")

        for file in files:

            local_path = os.path.join(path, os.path.relpath(file, remote_path))
            downloaded_path = self.download_file(file, local_path)

            downloaded.append(downloaded_path)
            progress_bar.update(1)

            callback = kwargs.get('callback')
            if callback: callback(downloaded_path)

        return downloaded


class Connection:

    @staticmethod
    def retry ( attempts = 3, delay = 2 ):

        def decorator ( func ):

            @functools.wraps(func)
            def wrapper ( *args, **kwargs ):

                for attempt in range(attempts):
                    try: return func(*args, **kwargs)
                    except Exception as e:
                        if attempt == attempts - 1: raise
                        time.sleep(delay * (2 ** attempt))

            return wrapper

        return decorator

class Manager:

    def __init__ ( self ):

        self.s3      = S3
        self.ftp     = FTP
        self.gdrive  = GDrive
        self.dropbox = Dropbox
        self.client  = None

    @Connection.retry
    def connect ( self, provider: str = 's3', credentials: dict = {}, options: dict = {} ):

        obj = getattr(self, provider)
        if not obj: raise ValueError(f"Unsupported provider: {provider}")

        self.client = obj().connect(credentials, options)
        return self

    @Connection.retry
    def upload_file ( self, local_path: str = None, remote_path: str = None, **kwargs: Any ):

        return self.client.upload_file(local_path, remote_path, **kwargs)

    @Connection.retry
    def download_file ( self, remote_path: str = None, local_path: str = None, **kwargs: Any ):

        return self.client.download_file(remote_path, local_path, **kwargs)

    @Connection.retry
    def upload_folder ( self, local_path: str = None, remote_path: str = None, **kwargs: Any ):

        return self.client.upload_folder(local_path, remote_path, **kwargs)

    @Connection.retry
    def download_folder ( self, remote_path: str = None, local_path: str = None, **kwargs: Any ):

        return self.client.download_folder(remote_path, local_path, **kwargs)
