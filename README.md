# BI-PSI

Computer networks course at FIT CTU.

The repository contains code for homework task.

## Task assignment

The task was to create a TCP/IP server in any programming language. I chose Python for this task.

The server should be able to guide the client (robot) to zero coordinates. 

At the beginning of the communication, the client is authorized by sending a key and through a simple hash calculation. 
The client then sends the coordinate information about where it is, and the goal of the server is to send motion and rotation commands so that the client arrives at the null coordinates. 
The task is complicated by the limited number of moves, and the presence of obstacles along the way, which must be bypassed and which can only be found by the fact that the client does not move after the move command. Further, at any time, the client can send a command ("recharging") notifying that it will not respond to commands for some fixed period of time, and the server must adapt to this.
Furthermore, there are fixed message lengths, and the server optimizes communication when it is indicated that the maximum message length has been exceeded.

## Evaluation

The final score for my homework was 23/20 points.

<sub><sup>Note: Maximum points are quoted without bonus for early submission</sup></sub>