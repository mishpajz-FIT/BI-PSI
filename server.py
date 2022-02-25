#!/usr/bin/env python3

import socket
import sys
import threading
import enum

HOST = '127.0.0.1'
port = None

SERVER_KEY = [23019, 32037, 18789, 16443, 18189]
CLIENT_KEY = [32037, 29295, 13603, 29533, 21952]

MESSAGES = {
    "SERVER_SYNTAX_ERROR": "301 SYNTAX ERROR\a\b".encode("ascii"),
    "SERVER_LOGIC_ERROR": "302 LOGIC ERROR\a\b".encode("ascii"),
    "SERVER_LOGOUT": "106 LOGOUT\a\b".encode("ascii"),
    "SERVER_KEY_REQUEST": "107 KEY REQUEST\a\b".encode("ascii"),
    "SERVER_LOGIN_FAILED": "300 LOGIN FAILED\a\b".encode("ascii"),
    "SERVER_KEY_OUT_OF_RANGE_ERROR": "303 KEY OUT OF RANGE\a\b".encode("ascii"),
    "SERVER_OK": "200 OK\a\b".encode("ascii"),
    "SERVER_MOVE": "102 MOVE\a\b".encode("ascii"),
    "SERVER_TURN_LEFT": "103 TURN LEFT\a\b".encode("ascii"),
    "SERVER_TURN_RIGHT": "104 TURN RIGHT\a\b".encode("ascii"),
    "SERVER_PICK_UP": "105 GET MESSAGE\a\b".encode("ascii")
};

class ServerThread(threading.Thread):

    class Authentication():

        class AuthenticationPhase(enum.Enum):
            USERNAME = 0
            KEY_ID = 1
            CONFIRMATION = 2
            AUTHENTICATED = 3

        def __init__(self, connection) -> None:
            self.connection = connection
            self.phase = self.AuthenticationPhase.USERNAME

        def length_valid(self, data) -> bool:
            prefix_size = 0
            if len(data) != 0 and data[-1] == "\a":
                prefix_size += 1

            if self.phase == self.AuthenticationPhase.USERNAME:
                if len(data) > 18 + prefix_size:
                    return False
            elif self.phase == self.AuthenticationPhase.KEY_ID:
                if len(data) > 3 + prefix_size:
                    return False
            elif self.phase == self.AuthenticationPhase.CONFIRMATION:
                if len(data) > 5 + prefix_size:
                    return False
            return True

        def calculate_hash(self):
            self.hash = 0
            for c in self.username:
                self.hash += ord(c)
            self.hash *= 1000
            self.hash %= 65536

        def authenticate(self, data) -> bool:

            global SERVER_KEY
            global CLIENT_KEY
            global MESSAGES

            if not self.length_valid(data):
                self.connection.send(MESSAGES["SERVER_SYNTAX_ERROR"])
                return False

            if self.phase == self.AuthenticationPhase.USERNAME:
                self.username = data

                self.phase = self.AuthenticationPhase.KEY_ID
                self.connection.send(MESSAGES["SERVER_KEY_REQUEST"])
                return True

            elif self.phase == self.AuthenticationPhase.KEY_ID:
                if not data.isdecimal():
                    self.connection.send(MESSAGES["SERVER_SYNTAX_ERROR"])  
                    return False

                self.keyid = int(data)

                if self.keyid < 0 or self.keyid > 4:
                    self.connection.send(MESSAGES["SERVER_KEY_OUT_OF_RANGE_ERROR"])
                    return False
                
                self.calculate_hash()

                server_hash = self.hash + SERVER_KEY[self.keyid]
                server_hash %= 65536
                confirmation_message = f"{server_hash}\a\b"

                self.phase = self.AuthenticationPhase.CONFIRMATION
                self.connection.send(confirmation_message.encode("ascii"))
                return True

            elif self.phase == self.AuthenticationPhase.CONFIRMATION:
                if not data.isdecimal():
                    self.connection.send(MESSAGES["SERVER_SYNTAX_ERROR"])
                    return False
                
                clientkey = int(data)
                clientkey -= CLIENT_KEY[self.keyid]
                if clientkey < 0:
                    clientkey = 65536 + clientkey

                if clientkey != self.hash:
                    self.connection.send(MESSAGES["SERVER_LOGIN_FAILED"])
                    return False

                self.phase = self.AuthenticationPhase.AUTHENTICATED
                self.connection.send(MESSAGES["SERVER_OK"])
                self.connection.send(MESSAGES["SERVER_TURN_LEFT"])
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
            global MESSAGES
            self.connection.send(MESSAGES["SERVER_MOVE"])
            self.last_moved = True

        def rotate(self, left):
            global MESSAGES
            rotation_value = None
            if left:
                if self.direction:
                    rotation_value = (self.direction.value + 1) % 4
                self.connection.send(MESSAGES["SERVER_TURN_LEFT"])
            else:
                if self.direction:
                    rotation_value = (self.direction.value - 1) % 4
                self.connection.send(MESSAGES["SERVER_TURN_RIGHT"])
            if self.direction:
                self.direction = self.Direction(rotation_value)
            self.last_moved = False

        def calculate_direction(self, direction):
            if not self.direction or self.direction == direction:
                self.move()
            else:
                if (direction.value - self.direction.value) == -1 or (direction.value - self.direction.value) == 3:
                    self.rotate(False)
                else:
                    self.rotate(True)

        def unstuck(self):
            left = True
            if self.direction:
                if self.x > 0:
                    if self.y < 0:
                        left = False
                else:
                    if self.y > 0:
                        left = False

            self.rotate(left)
            self.move()
            self.rotate(not left)
            self.move()
            self.unstuck_moves_left = 4

        def get_message(self):
            global MESSAGES
            self.picking_up_message = True
            self.connection.send(MESSAGES["SERVER_PICK_UP"])

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

        def verify_digit(self, digit) -> bool:
            if digit.startswith("-"):
                return digit[1:].isdigit()
            else:
                return digit.isdigit()

        def process_message(self, data) -> bool:
            global MESSAGES

            if not self.verify_length(data):
                self.connection.send(MESSAGES["SERVER_SYNTAX_ERROR"])
                return False

            if "OK" in data and not self.picking_up_message:

                data_split = data.split(" ")

                if data_split[0] != "OK" or not self.verify_digit(data_split[1]) or not self.verify_digit(data_split[2]) or len(data_split) != 3:
                    self.connection.send(MESSAGES["SERVER_SYNTAX_ERROR"])
                    return False
                new_x = int(data_split[1])
                new_y = int(data_split[2])

                if (self.last_moved and (new_x == self.x and new_y == self.y)) and self.unstuck_moves_left <= 0:
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
                    if self.x == 0 and self.y == 0:
                        self.get_message()
                    else:
                        self.move()
                else:
                    if self.unstuck_moves_left <= 0:
                        self.calculate_move()
                    else:
                        self.unstuck_moves_left -= 1
            else:
                if self.picking_up_message:
                    self.connection.send(MESSAGES["SERVER_LOGOUT"])
                    return False

                self.connection.send(MESSAGES["SERVER_SYNTAX_ERROR"])
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
        self.recharging = False

        self.connection.settimeout(1)

        print("OK: Connected from " + address[0] + ":" + str(address[1]))

    def syntax_error(self):
        global MESSAGES
        self.connection.send(MESSAGES["SERVER_SYNTAX_ERROR"])
        self.active = False

    def logical_error(self):
        global MESSAGES
        self.connection.send(MESSAGES["SERVER_LOGIC_ERROR"])
        self.active = False

    def recharge(self):
        if not self.recharging:
            self.connection.settimeout(5)
            self.recharging = True
        else:
            self.connection.settimeout(1)
            self.recharging = False

    def handle_data(self) -> bool:
        while '\a\b' in self.data:
            new_partition = self.data.partition("\a\b")
            new_string = new_partition[0]
            self.data = new_partition[2]

            if new_string == "RECHARGING":
                if self.recharging:
                    self.logical_error()
                    return False
                self.recharge()
                continue
            else:
                if self.recharging:
                    if new_string == "FULL POWER":
                        self.recharge()
                        continue
                    else:
                        self.logical_error()
                        return False

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
            try:
                self.data += self.connection.recv(1024).decode("ascii")
            except:
                self.active = False
                self.connection.close()

            if not self.handle_data():
                self.connection.close()

            if (self.authentication.phase != self.authentication.AuthenticationPhase.AUTHENTICATED):
                if not self.authentication.length_valid(self.data):
                    self.syntax_error()
                    self.connection.close()
            else:
                prefix_size = 0
                if len(self.data) != 0 and self.data[-1] == "\a":
                    prefix_size += 1

                if (not self.movement.picking_up_message and len(self.data) > 10 + prefix_size) or len(self.data) > 98 + prefix_size:
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

    server_threads = []

    try:
        while True:
            (connection, address) = serversocket.accept()
            clientsocket = ServerThread(connection, address)
            server_threads.append(clientsocket)
            clientsocket.start()
    except:
        serversocket.close()
        print("OK: Exiting")


if __name__ == "__main__":
    main()
