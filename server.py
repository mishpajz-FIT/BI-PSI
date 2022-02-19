#!/usr/bin/env python3

from concurrent.futures import thread
import socket
from sqlite3 import connect
from symtable import SymbolTable
import sys
import threading
from enum import Enum

HOST = '127.0.0.1'
port = None

class ServerThread(threading.Thread):

    class Authentication():
        class AuthenticationPhase(Enum):
            USERNAME = 0
            KEY_ID = 1
            CONFIRMATION = 2
            AUTHENTICATED = 3

        SERVER_KEY = [23019, 32037, 18789, 16443, 18189]
        CLIENT_KEY = [32037, 29295, 13603, 29533, 21952]

        def __init__(self, connection) -> None:
            self.connection = connection
            self.phase = self.AuthenticationPhase.USERNAME

        def length_valid(self, data) -> bool:
            if self.phase == self.AuthenticationPhase.USERNAME:
                if len(data) > 18:
                    return False
            elif self.phase == self.AuthenticationPhase.KEY_ID:
                if len(data) > 3:
                    return False
            elif self.phase == self.AuthenticationPhase.CONFIRMATION:
                if len(data) > 5:
                    return False
            return True

        def calculate_hash(self):
            self.hash = 0
            for c in self.username:
                self.hash += ord(c)
            self.hash *= 1000
            self.hash %= 65536


        def authenticate(self, data) -> bool:
            if not self.length_valid(data):
                self.connection.send("301 SYNTAX ERROR\a\b".encode("ascii"))
                return False

            if self.phase == self.AuthenticationPhase.USERNAME:
                self.username = data

                self.phase = self.AuthenticationPhase.KEY_ID
                self.connection.send("107 KEY REQUEST\a\b".encode("ascii"))
                return True

            elif self.phase == self.AuthenticationPhase.KEY_ID:
                if not data.isdecimal():
                    self.connection.send("301 SYNTAX ERROR\a\b".encode("ascii"))    
                    return False

                self.keyid = int(data)

                if self.keyid < 0 or self.keyid > 4:
                    self.connection.send("303 KEY OUT OF RANGE\a\b".encode("ascii"))
                    return False
                
                self.calculate_hash()

                server_hash = self.hash + self.SERVER_KEY[self.keyid]
                server_hash %= 65536
                confirmation_message = f"{server_hash}\a\b"

                self.phase = self.AuthenticationPhase.CONFIRMATION
                self.connection.send(confirmation_message.encode("ascii"))
                return True

            elif self.phase == self.AuthenticationPhase.CONFIRMATION:
                if not data.isdecimal():
                    self.connection.send("301 SYNTAX ERROR\a\b".encode("ascii"))
                    return False
                
                clientkey = int(data)
                clientkey -= self.CLIENT_KEY[self.keyid]
                if clientkey < 0:
                    clientkey = 65536 + clientkey

                if clientkey != self.hash:
                    self.connection.send("300 LOGIN FAILED\a\b".encode("ascii"))
                    return False

                self.phase = self.AuthenticationPhase.AUTHENTICATED
                self.connection.send("200 OK\a\b".encode("ascii"))
                return True     

    def __init__(self, connection, address) -> None:
        threading.Thread.__init__(self)
        self.connection = connection
        self.address = address
        self.data = ""
        self.authentication = ServerThread.Authentication(connection)
        self.active = True
        print("OK: Connected from ", address)

    def run(self):
        while self.active:
            self.data += self.connection.recv(1024).decode("ascii")
            while '\a\b' in self.data:
                new_partition = self.data.partition("\a\b")
                new_string = new_partition[0]
                self.data = new_partition[2]
                if (self.authentication.phase != self.authentication.AuthenticationPhase.AUTHENTICATED):
                    if not self.authentication.authenticate(new_string):
                        self.connection.close()
                        self.active = False
                        break

            if (self.authentication.phase != self.authentication.AuthenticationPhase.AUTHENTICATED and not self.authentication.length_valid(self.data)):
                self.connection.send("301 SYNTAX ERROR\a\b".encode("ascii"))
                self.active = False
        self.connection.close()


        
def get_port() -> bool:
    if (len(sys.argv) <= 1):
        print("ERR: Add port as an argument")
        return False
    
    try:
        global port 
        port = int(sys.argv[1])
    except:
        print("ERR: Port is not a number")
        return False

    if (port == None or port <= 1023 or port > 65353):
        print("ERR: Invalid port")
        return False

    return True

def main():
    if (not get_port()):
        return None
    
    try:
        serversocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        print("OK: Socket created")
    except:
        print("ERR: Socket creation failed")
        return None

    try:
        global HOST
        global port
        serversocket.bind((HOST, port))
        print("OK: Socket binded")
    except:
        print("ERR: Socket bind failed")
        return None

    serversocket.listen(5)

    try:
        while True:
            (connection, address) = serversocket.accept()
            clientsocket = ServerThread(connection, address)
            clientsocket.start()
    except KeyboardInterrupt:
        serversocket.close()
        print("OK: Exiting")
        exit(0)

    print(port)


if __name__ == "__main__":
    main()
