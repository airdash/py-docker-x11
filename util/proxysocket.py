import struct
from socket import socket, AF_UNIX, SOCK_STREAM
import threading
import os
from util import user

# This proxies socket requests from Docker and uses the credentials
# of the user running the application, not the namespaced user.
# This is obviously dangerous if your application decides to make
# malicious calls via dbus, Docker or whatever you're proxying!

class ProxySocket(threading.Thread):
    def __init__(self, src, dst, container_uid, container_gid):
        threading.Thread.__init__(self)
        self.src = src
        print("self src is %s" % self.src)
        self.dst = dst
        self.container_uid = container_uid
        self.container_gid = container_gid

    def _proxy(self, src_socket, dst_socket):
        while True:
            try:
                data = src_socket.recv(4096)
                if not data:
                    break
                else:
                    dst_socket.sendall(data)
            except:
                break
    
    def listen(self):

        print("Creating proxy socket at %s to %s" % (self.src, self.dst))

        print("Checking for socket path at %s" % self.src)
        if os.path.exists(self.src):
            print("Unlinking %s" % self.src)
            user.chown(self.src, self.container_uid, self.container_gid)
            os.unlink(self.src)

        src_socket = socket(AF_UNIX, SOCK_STREAM)
        src_socket.bind(self.src)

        os.chmod(self.src, 0o620)
        user.chown(self.src, self.container_uid, self.container_gid)

        while True:

            src_socket.listen(1)

            # This blocks until we receive a connection
            src_connection, src_addr = src_socket.accept()
            src_connection.settimeout(5.0)

            dst_socket = socket(AF_UNIX, SOCK_STREAM)
            dst_socket.connect(self.dst)
            dst_socket.settimeout(5.0)

            src_thread = threading.Thread(target = self._proxy, args=[src_connection, dst_socket])
            src_thread.start()
            dst_thread = threading.Thread(target = self._proxy, args=[dst_socket, src_connection])
            dst_thread.start()

