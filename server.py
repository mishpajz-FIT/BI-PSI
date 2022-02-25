#!/usr/bin/env python3



## TCP/IP multithreaded server for BI-PSI homework.
#
# Main objective is to reach zero coordinates with client (robot). Sends requests for turning and moving the robot.
# At the beginning of communication the server authenticates the client.
# The server can deal with client halting (robot recharging) and very simple algorithm to avoid obstacles on robots path.

from platform import python_branch
import socket
import sys
import threading
import enum

# Global variables defined by server specification
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


## Class implementing all of server logic after communication has been initialized
#
class ServerThread(threading.Thread):

    ## Class for processing client authentication
    #
    class Authentication():

        ## Defines phases of authentication protocol as enum
        #
        class AuthenticationPhase(enum.Enum):
            USERNAME = 0
            KEY_ID = 1
            CONFIRMATION = 2
            AUTHENTICATED = 3

        ## Constructor
        #
        #  @param self
        #  @param connection Connection to client
        #
        def __init__(self, connection) -> None:
            self.connection = connection
            self.phase = self.AuthenticationPhase.USERNAME

        ## Check if message length is valid before processing it
        #
        #  Calculates whether the message fits the expected length.
        #
        #  @param self
        #  @param data Received message
        #  
        #  @returns bool Valid length
        #
        def verify_length(self, data) -> bool:
            # Check if contains part of message separation characters
            prefix_size = 0
            if len(data) != 0 and data[-1] == "\a":
                prefix_size += 1

            # Check for halt message
            recharging_check_string = "RECHARGING\a\b"
            recharging_check_string_trucated = recharging_check_string[0:len(data)]

            if data.startswith(recharging_check_string_trucated):
                if len(data) > 10 + prefix_size:
                    return False
                else:
                    return True

            # Check if message length is expected in authentication phase
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

        ## Calculate hash as expected by server specification
        #
        #  @param self
        #
        def calculate_hash(self):
            self.hash = 0
            for c in self.username:
                self.hash += ord(c)
            self.hash *= 1000
            self.hash %= 65536

        ## Process received authentication message
        #
        #  @param self
        #  @param data Received message
        #
        #  @returns bool If true authentication is valid, else should terminate connection
        #
        def authenticate(self, data) -> bool:

            global SERVER_KEY
            global CLIENT_KEY
            global MESSAGES

            # Check for correct length
            if not self.verify_length(data):
                self.connection.send(MESSAGES["SERVER_SYNTAX_ERROR"])
                return False

            # Perform required action based on authetication phase defined by server specification
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

    ## Class for processing client movement
    #
    class Movement():

        ## Defines direction of robot movement
        #
        class Direction(enum.Enum):
            POSITIVE_X = 0
            POSITIVE_Y = 1
            NEGATIVE_X = 2
            NEGATIVE_Y = 3

        ## Constructor
        #
        #  @param self
        #  @param connection Connection to client
        #
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

        ## Sends message requesting client to move
        #
        #  @param self
        #
        def move(self):
            global MESSAGES
            self.connection.send(MESSAGES["SERVER_MOVE"])
            self.last_moved = True

        ## Sends message requesting client to rotate
        #
        #  Calculates new direction the robot will be facing and sends request
        #
        #  @param self
        #  @param left If true, rotate anticlockwise, else rotate clockwise
        #
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

        ## Calculates if next request should be rotation or movement
        #
        #  @param self
        #  @param direction Requested direction of movement
        #  
        #  If facing requested direction of movement, move, else rotate whichever way is closer.
        #
        def calculate_direction(self, direction):
            if not self.direction or self.direction == direction:
                self.move()
            else:
                if (direction.value - self.direction.value) == -1 or (direction.value - self.direction.value) == 3:
                    self.rotate(False)
                else:
                    self.rotate(True)

        ## If facing obstacle, moves to the said of given obstacle
        #
        #  @param self
        #
        #  Calculates more advantageous side of obstacle to move to.
        #
        def unstuck(self):
            left = True

            # Calculate which side of obstacle to move to
            if self.direction:
                if self.x > 0:
                    if self.y < 0:
                        left = False
                else:
                    if self.y > 0:
                        left = False

            # Move
            self.rotate(left)
            self.move()
            self.rotate(not left)
            self.move()

            # @var unstuck_moves_left Sets amount of calls to ignore (because of unstuck mechanism)
            self.unstuck_moves_left = 4

        ## Shortcut to request picking up message at zero coords (goal of client)
        #
        #  @param self
        #
        def get_message(self):
            global MESSAGES
            self.picking_up_message = True
            self.connection.send(MESSAGES["SERVER_PICK_UP"])

        ## Calculates next move to zero coords based on current coords
        #
        #  @param self
        #
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

        ## Check if message length is valid before processing it
        #
        #  Calculates whether the message fits the expected length.
        #
        #  @param self
        #  @param data Received message
        #  
        #  @returns bool Valid length
        #
        def verify_length(self, data):
            # Check if contains part of message separation characters
            prefix_size = 0
            if len(data) != 0 and data[-1] == "\a":
                prefix_size += 1

            # Check if message length is expected
            if self.picking_up_message:
                if len(data) <= 98 + prefix_size:
                    return True
            else:
                if len(data) <= 10 + prefix_size:
                    return True
            return False

        ## Check if string contains positive or negative integer
        #
        #  @param self
        #  @param digit String containing digit
        #
        #  @returns bool Does string contain valid integer
        #
        def verify_digit(self, digit) -> bool:
            if digit.startswith("-"):
                return digit[1:].isdigit()
            else:
                return digit.isdigit()

        ## Process received movement message
        #
        #  @param self
        #  @param data Received message
        #
        #  @returns bool If true movement is valid, else should terminate connection (or goal has been achieved and should terminate)
        def process_message(self, data) -> bool:
            global MESSAGES

            # Check for correct length
            if not self.verify_length(data):
                self.connection.send(MESSAGES["SERVER_SYNTAX_ERROR"])
                return False

            # Perform action based on received message
            if "OK" in data and not self.picking_up_message:

                data_split = data.split(" ")

                # Check for correct syntax
                if data_split[0] != "OK" or not self.verify_digit(data_split[1]) or not self.verify_digit(data_split[2]) or len(data_split) != 3:
                    self.connection.send(MESSAGES["SERVER_SYNTAX_ERROR"])
                    return False
                new_x = int(data_split[1])
                new_y = int(data_split[2])

                # Based on current and last position verify if stuck and calculate direction  
                if not self.first_move:
                    if (self.last_moved and (new_x == self.x and new_y == self.y)) and self.unstuck_moves_left <= 0:
                        self.unstuck()

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

                # Check if first move or processing stuck mechanism messages or if client robot is in final destination and move accordingly
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

    ## Constructor
    #
    #  @param self
    #  @param connection Connection to client
    #  @param address Tuple of IPv4 address and port of connected client
    #
    def __init__(self, connection, address) -> None:
        threading.Thread.__init__(self)
        self.connection = connection
        self.address = address
        self.data = ""
        self.authentication = ServerThread.Authentication(connection)
        self.movement = ServerThread.Movement(connection)
        self.active = True
        self.recharging = False

        self.connection.settimeout(1) #Sets default timeout

        print("OK: Connected from " + address[0] + ":" + str(address[1]))

    ## Shortcut for sending sytax error message
    #
    def syntax_error(self):
        global MESSAGES
        self.connection.send(MESSAGES["SERVER_SYNTAX_ERROR"])
        self.active = False

    ## Shortcut for sending sytax logic message
    #
    def logical_error(self):
        global MESSAGES
        self.connection.send(MESSAGES["SERVER_LOGIC_ERROR"])
        self.active = False

    ## Process recharge message
    # 
    #  Handle recharging (client halting).
    #  If already recharging set timeout to default, else set timeout to specified value.
    # 
    #  @param self
    #
    def recharge(self):
        if not self.recharging:
            self.connection.settimeout(5)
            self.recharging = True
        else:
            self.connection.settimeout(1)
            self.recharging = False

    ## Extract and process messages in recieved data
    #
    #  Looks for separation characters in data and extracts message before these characters.
    #  First tries to process recharging (halting) message, if not halted sends recieved message to authentication or movement handler in corresponding class based on current status of authentication.
    #  
    #  @param self
    #
    #  @returns bool If failed and needs to terminate connection false, else true.
    def handle_data(self) -> bool:
        while '\a\b' in self.data:
            new_partition = self.data.partition("\a\b")
            new_string = new_partition[0]
            self.data = new_partition[2]

            # Recharging handling
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

            # Authentication and movement handling
            if (self.authentication.phase != self.authentication.AuthenticationPhase.AUTHENTICATED):
                if not self.authentication.authenticate(new_string):
                    self.active = False
                    return False
            else:
                if not self.movement.process_message(new_string):
                    self.active = False
                    return False
        return True

    ## Primary function of thread
    #
    #  Receives data from connection and calls handler to process it.
    #
    #  If data is longer than specified limit and still not processed, optimizes by cutting connection.
    def run(self):
        while self.active:
            # Receive data
            try:
                self.data += self.connection.recv(1024).decode("ascii")
            except:
                self.active = False
                self.connection.close()

            # Handle data
            if not self.handle_data():
                self.connection.close()

            ## Message length checking optimalization
            if (self.authentication.phase != self.authentication.AuthenticationPhase.AUTHENTICATED) and not self.recharging:
                if not self.authentication.verify_length(self.data):
                    self.syntax_error()
                    self.connection.close()
            else:
                if not self.movement.verify_length(self.data):
                    self.syntax_error()
                    self.connection.close()

## Get port value from stdio.
#
#  Port needs to be between 1024 and 65353 inclusive.
#
#  @returns bool Sucess or failiure
#
#  Saves port value into global variable PORT.
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

## Creates server socket, starts listening for connections, when connected creates new thread for serving client.
#
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
        sys.exit(0)


if __name__ == "__main__":
    main()
