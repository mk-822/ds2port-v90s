"""SSH transfers use tar streams: PlumOS can run without an SFTP subsystem."""
import base64
import hashlib
import io
import os
from pathlib import Path
import shlex
import tarfile
import time
import paramiko


class UnknownHostKey(Exception):
    def __init__(self, hostname, key):
        self.hostname, self.key = hostname, key
        self.fingerprint = "SHA256:" + base64.b64encode(hashlib.sha256(key.asbytes()).digest()).decode().rstrip("=")
        super().__init__(f"{hostname}: {key.get_name()} {self.fingerprint}")


class AskHostKey(paramiko.MissingHostKeyPolicy):
    def missing_host_key(self, client, hostname, key):
        raise UnknownHostKey(hostname, key)


def known_hosts_path():
    base = Path(os.environ.get("LOCALAPPDATA", Path.home() / ".local/share"))
    return base / "ds2port-v90s" / "known_hosts"


def trust_host(error: UnknownHostKey):
    path = known_hosts_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    keys = paramiko.HostKeys(str(path)) if path.exists() else paramiko.HostKeys()
    keys.add(error.hostname, error.key.get_name(), error.key)
    keys.save(str(path))


class Connection:
    def __init__(self, host, username, password="", port=22, key_filename=None):
        self.client = paramiko.SSHClient()
        path = known_hosts_path()
        if path.exists():
            self.client.load_host_keys(str(path))
        self.client.set_missing_host_key_policy(AskHostKey())
        try:
            self.client.connect(hostname=host, port=port, username=username, password=password or None,
                                key_filename=key_filename, look_for_keys=not password and not key_filename,
                                allow_agent=not password, timeout=15, auth_timeout=20, banner_timeout=20)
            self.client.get_transport().set_keepalive(15)
        except BaseException:
            self.client.close()
            raise

    def close(self):
        self.client.close()

    def run(self, command, timeout=300):
        channel = self.client.get_transport().open_session(timeout=15)
        channel.exec_command(command)
        stdout, stderr = bytearray(), bytearray()
        deadline = time.monotonic() + timeout
        try:
            while True:
                while channel.recv_ready():
                    stdout.extend(channel.recv(65536))
                while channel.recv_stderr_ready():
                    stderr.extend(channel.recv_stderr(65536))
                if channel.exit_status_ready() and not channel.recv_ready() and not channel.recv_stderr_ready():
                    break
                if time.monotonic() > deadline:
                    raise TimeoutError("本体上の処理がタイムアウトしました。")
                time.sleep(0.02)
            status = channel.recv_exit_status()
        finally:
            channel.close()
        out, err = stdout.decode("utf-8", "replace"), stderr.decode("utf-8", "replace")
        if status:
            raise RuntimeError(f"本体上の処理が失敗しました ({status})\n{out}\n{err}")
        return out

    def upload(self, path: Path, remote: str, progress=lambda done, total: None):
        # A single safely quoted file path is sent to cat; no shell interpolation.
        channel = self.client.get_transport().open_session(timeout=15)
        channel.settimeout(180)
        channel.exec_command("umask 077; cat > " + shlex.quote(remote))
        total, done = path.stat().st_size, 0
        try:
            with path.open("rb") as source:
                while chunk := source.read(256 * 1024):
                    channel.sendall(chunk)
                    done += len(chunk)
                    progress(done, total)
            channel.shutdown_write()
            error = channel.makefile_stderr("rb").read().decode("utf-8", "replace")
            if channel.recv_exit_status():
                raise RuntimeError("転送に失敗しました: " + error)
        finally:
            channel.close()

    def upload_bytes(self, data: bytes, remote: str):
        channel = self.client.get_transport().open_session(timeout=15)
        channel.settimeout(60)
        channel.exec_command("umask 077; cat > " + shlex.quote(remote))
        try:
            channel.sendall(data)
            channel.shutdown_write()
            error = channel.makefile_stderr("rb").read().decode("utf-8", "replace")
            if channel.recv_exit_status():
                raise RuntimeError(error)
        finally:
            channel.close()
