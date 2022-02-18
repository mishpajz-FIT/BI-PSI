#!/usr/bin/env python3

import socket
import sys

HOST = '127.0.0.1'
port = None


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
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        print("OK: Socket created")
    except:
        print("ERR: Socket creation failed")
        return None

    try:
        global HOST
        global port
        s.bind((HOST, port))
    except:
        print("ERR: Socket bind failed")
        return None

    print(port)


if __name__ == "__main__":
    main()
