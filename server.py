#!/usr/bin/env python3

import socket
import sys
import threading
import enum

HOST = '127.0.0.1'
port = None

class ServerThread(threading.Thread):

    class Authentication():

        class AuthenticationPhase(enum.Enum):
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
                self.connection.send("103 TURN LEFT\a\b".encode("ascii"))
                return True     

    class Movement():

        class Direction(enum.Enum):
            POSITIVE_X = 0
            POSITIVE_Y = 1
            NEGATIVE_X = 2
            NEGATIVE_Y = 3

        def __init__(self, connection) -> None:
            self.connection = connection
            self.x = None
            self.y = None
            self.direction = None
            self.picking_up_message = False
            self.recharging = False
            self.last_moved = False
            self.first_move = True
            self.unstuck_moves_left = 0

        def move(self):
            self.connection.send("102 MOVE\a\b".encode("ascii"))
            self.last_moved = True

        def rotate(self, left):
            rotation_value = None
            if left:
                rotation_value = (self.direction.value + 1) % 4
                self.connection.send("103 TURN LEFT\a\b".encode("ascii"))
            else:
                rotation_value = (self.direction.value - 1) % 4
                self.connection.send("104 TURN RIGHT\a\b".encode("ascii"))
            self.direction = self.Direction(rotation_value)
            self.last_moved = False

        def calculate_direction(self, direction):
            if self.direction == direction:
                self.move()
            else:
                if (direction.value - self.direction.value) == -1 or (direction.value - self.direction.value) == 3:
                    self.rotate(False)
                else:
                    self.rotate(True)

        def unstuck(self):
            #TODO
            return

        def get_message(self):
            self.picking_up_message = True
            self.connection.send("105 GET MESSAGE\a\b".encode("ascii"))

        def calculate_move(self):
            if self.x != 0:
                if self.x > 0:
                    self.calculate_direction(self.Direction.NEGATIVE_X)
                elif self.x < 0:
                    self.calculate_direction(self.Direction.POSITIVE_X)
            elif self.y != 0:
                if self.y > 0:
                    self.calculate_direction(self.Direction.NEGATIVE_Y)
                elif self.y < 0:
                    self.calculate_direction(self.Direction.POSITIVE_Y)
            else:
                self.last_moved = False
                self.get_message()

        def verify_length(self, data):
            if self.picking_up_message:
                if len(data) <= 98:
                    return True
            else:
                if len(data) <= 10:
                    return True
            return False

        def process_message(self, data) -> bool:
            
            if not self.verify_length(data):
                self.connection.send("301 SYNTAX ERROR\a\b".encode("ascii"))
                return False

            if "OK" in data and not self.picking_up_message:
                if self.recharging:
                    self.connection.send("302 LOGIC ERROR\a\b".encode("ascii"))
                    return False

                data_split = data.split(" ")
                new_x = int(data_split[1])
                new_y = int(data_split[2])

                if self.last_moved and new_x == self.x and new_y == self.y and self.unstuck_moves_left <= 0:
                    self.unstuck()
                elif not self.first_move:
                    if (new_x > self.x):
                        self.direction = self.Direction.POSITIVE_X
                    elif (new_x < self.x):
                        self.direction = self.Direction.NEGATIVE_X
                    elif (new_y > self.y):
                        self.direction = self.Direction.POSITIVE_Y
                    elif (new_y < self.y):
                        self.direction = self.Direction.NEGATIVE_Y

                self.x = new_x
                self.y = new_y

                if self.first_move:
                    self.first_move = False
                    self.move()
                else:
                    if self.unstuck_moves_left <= 0:
                        self.calculate_move()
                    else:
                        self.unstuck_moves_left -= 1

            elif data == "RECHARGING":
                if self.recharging:
                    self.connection.send("302 LOGIC ERROR\a\b".encode("ascii"))
                    return False
                    
                self.connection.settimeout(5)
                self.unstuck_moves_left = 0
                self.recharging = True
            elif data == "FULL POWER":
                if not self.recharging:
                    self.connection.send("302 LOGIC ERROR\a\b".encode("ascii"))
                    return False

                self.connection.settimeout(1)
                self.recharging = False
                self.calculate_move()
            else:
                if self.picking_up_message:
                    if self.recharging:
                        self.connection.send("302 LOGIC ERROR\a\b".encode("ascii"))
                        return False
                    else:
                        self.connection.send("106 LOGOUT\a\b".encode("ascii"))
                        return True

                self.connection.send("301 SYNTAX ERROR\a\b".encode("ascii"))
                return False
            return True

    def __init__(self, connection, address) -> None:
        threading.Thread.__init__(self)
        self.connection = connection
        self.address = address
        self.data = ""
        self.authentication = ServerThread.Authentication(connection)
        self.movement = ServerThread.Movement(connection)
        self.active = True
        
        self.connection.settimeout(1)

        print("OK: Connected from ", address)

    def syntax_error(self):
        self.connection.send("301 SYNTAX ERROR\a\b".encode("ascii"))
        self.active = False

    def handle_data(self) -> bool:
        while '\a\b' in self.data:
            new_partition = self.data.partition("\a\b")
            new_string = new_partition[0]
            self.data = new_partition[2]
            if (self.authentication.phase != self.authentication.AuthenticationPhase.AUTHENTICATED):
                if not self.authentication.authenticate(new_string):
                    self.active = False
                    return False
            else:
                if not self.movement.process_message(new_string):
                    self.active = False
                    return False
        return True

    def run(self):
        while self.active:
            self.data += self.connection.recv(1024).decode("ascii")

            if not self.handle_data():
                break

            if (self.authentication.phase != self.authentication.AuthenticationPhase.AUTHENTICATED):
                if not self.authentication.length_valid(self.data):
                    self.syntax_error()
            else:
                if not self.movement.picking_up_message and len(self.data) > 10:
                    self.syntax_error()
                elif len(self.data) > 98:
                    self.syntax_error()

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


if __name__ == "__main__":
    main()
