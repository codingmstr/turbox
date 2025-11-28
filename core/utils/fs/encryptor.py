from cryptography.fernet import Fernet
import os

class Encryptor:

    def __init__ ( self ):

        pass

    def generate_key ( self, key_path: str = None ):

        path = key_path or os.path.join(os.path.expanduser("~"), ".keys", "encryption.key")
        os.makedirs(os.path.dirname(path), exist_ok=True)

        if os.path.exists(path):
            with open(path, 'rb') as kfile: return kfile.read()

        key = Fernet.generate_key()
        with open(path, "wb") as kfile: kfile.write(key)

        return key

    def load_key ( self, key_path: str = None ):

        path = key_path or os.path.join(os.path.expanduser("~"), ".keys", "encryption.key")
        if not os.path.exists(path): return

        with open(path, 'rb') as kfile: return kfile.read()

    def key_exists ( self, key_path: str = None ):

        path = key_path or os.path.join(os.path.expanduser("~"), ".keys", "encryption.key")
        return os.path.exists(path)

    def is_encrypted ( self, path: str ):

        try:

            if os.path.isfile(path):
                with open(path, 'rb') as f: head = f.read(10)
                return b'gAAAAA' in head

            elif os.path.isdir(path):

                for root, _, files in os.walk(path):

                    for file in files:

                        file_path = os.path.join(root, file)
                        with open(file_path, 'rb') as f: head = f.read(10)

                        if b'gAAAAA' in head: return True

                return False

            return False

        except: return False

    def encrypt_file ( self, path: str, cipher: Fernet, chunk_size: int ):

        tmp_path = path + '.tmp'

        try:
            with open(path, 'rb') as fin, open(tmp_path, 'wb') as fout:
                while chunk := fin.read(chunk_size):
                    fout.write(cipher.encrypt(chunk))

            os.replace(tmp_path, path)
        finally:
            if os.path.exists(tmp_path): os.remove(tmp_path)

        return True

    def decrypt_file ( self, path: str, cipher: Fernet, chunk_size: int ):

        tmp_path = path + '.tmp'

        try:
            with open(path, 'rb') as fin, open(tmp_path, 'wb') as fout:
                while chunk := fin.read(chunk_size):
                    fout.write(cipher.decrypt(chunk))

            os.replace(tmp_path, path)

        finally:
            if os.path.exists(tmp_path): os.remove(tmp_path)

        return True

    def encrypt ( self, path: str, key_path: str = None, chunk_size: int = 1048576 ):

        key = self.generate_key(key_path)
        if not key: return False

        cipher = Fernet(key)
        if os.path.isfile(path): return self.encrypt_file(path, cipher, chunk_size)

        if os.path.isdir(path):

            for root, _, files in os.walk(path):

                for file in files:
                    file_path = os.path.join(root, file)
                    if file_path != key_path: self.encrypt_file(file_path, cipher, chunk_size)

            return True

        return False

    def decrypt ( self, path: str, key_path: str = None, chunk_size: int = 1048576 ):

        key = self.load_key(key_path)
        if not key: return False

        cipher = Fernet(key)
        if os.path.isfile(path): return self.decrypt_file(path, cipher, chunk_size)

        if os.path.isdir(path):

            for root, _, files in os.walk(path):

                for file in files:
                    file_path = os.path.join(root, file)
                    if file_path != key_path: self.decrypt_file(file_path, cipher, chunk_size)

            return True

        return False
