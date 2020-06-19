#!/usr/bin/env python
# -*- coding: utf-8 -*-

import sys
import time
import RPi.GPIO as GPIO
import logging
from pythonping import ping
import itertools
from multiping import MultiPing
import socket
logging.basicConfig(level=logging.INFO)
sys.path.append('../')
from obswebsocket import obsws, events, requests  # noqa: E402

############## User Configuration ###############
windows_dev = True       #flag for use during Windows development and testing, turn off for Raspberry Pi deployment
debug_level = 1         # Set amount of debug printing (0-4) -> higher is more print statements, 0 is off
#Modified by G Cotton - 18Jun20 to enable multiple tally lights (Preview/Program) and specific Camera # (trigger_char -> cam_num_str) based on GPIO inputs
port = 4444 #Should be 4444
password = "123456" #Change to a unique password.  Use the same password in OBS -> Tools -> Websockets Server Settings -> Password
IP_Addr_Base = "192.168.1."     #IP Address base to scan for connection to OBS

#Input Scene names
#trigger_char = "+" #If this character is found in the scene name then tally light will illuminate
# In final version, use GPIO reads to determine camera number - store as digits in string  - 3bits
cam_num_str_base = "-cam" #If this string of chars is found in the scene name then tally light will illuminate - correlate with Cam# to make it easier
#Final format example '-cam5' - number can be 0 through 7

#Input/Output pin definitions
GPIO_connected = 16 #-> Drives "Connected" LED (flashes when IP connetion established to OBS)
GPIO_tally_prev = 13 #-> Drives tally light#1 (Preview) -> Orginally 26 in schematic, but 13 in code?
GPIO_tally_prog = 6 #-> Drives tally light#2 (Program) 
GPIO_Cam_Num_Sel1 = 0 # Which GPIO inputs will be used to set the Cam# (3 bits), 1 is LSB
GPIO_Cam_Num_Sel2 = 2  # GPIO 0, 2, 3 should correspond to pin#s 11, 13 and 15 (RPi 3B+) on J8 (40pin header)
GPIO_Cam_Num_Sel3 = 3

if debug_level >= 1: print('GPIOs OUT: Connected-',GPIO_connected, 'Tally Prev-',GPIO_tally_prev, 'Tally Prog-', GPIO_tally_prog)     #Debug print to highlight GPIO Outputs
if debug_level >= 1: print('GPIOs IN: Cam Num Sel1',GPIO_Cam_Num_Sel1, 'Cam Num Sel2',GPIO_Cam_Num_Sel2, 'Cam Num Sel3', GPIO_Cam_Num_Sel3)   #Debug print to highlight GPIO Outputs

############## Script ###############
ipAddressHistory = open("obsAddr.log","r")  # "obsAddr.log" is a text file with one line -> the last IP address to which the program connected
host = ipAddressHistory.readline()
ipAddressHistory.close()

def scan_all_ip():
    ipRange = []
    if windows_dev:
        for i in range(1,2):
          ipRange.append("127.0.0."+str(i))         #Temp code for testing on same Windows machine (loopback)
    else:
        for i in range(1,253):                  #scans range of IP addresses
          ipRange.append(IP_Addr_Base + str(i))
#         ipRange.append("192.168.2."+str(i))
    mp = MultiPing(ipRange)
    mp.send()
    responses, no_responses = mp.receive(1)
    for addr, rtt in responses.items():
        if debug_level >= 2: print ("%s responded in %f seconds" % (addr, rtt))
    return responses



def find_open_socket():             #Seach for the open port# at any IPs that responded to the ping
        responses = scan_all_ip()
        for addr, rtt in responses.items():
                if addr == host:
                    if debug_level >= 1: print ("Attempting to connect " + host)
                    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    result = sock.connect_ex((host,port))
                    sock.close
                    if result == 0:
                        return host
        for addr, rtt in responses.items():
            if connected == False:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                if debug_level >= 1: print ("Attempting to connect " + addr)
                result = sock.connect_ex((addr,port))
                sock.close
                if result == 0:
                    return addr
        return ""
        
def set_cam_num():      #Sets the "Cam_num_str" based on the GPIO Input switches -> 3-bit binary -> returns as string
    cam_num=0       #default cam num
    if GPIO.input(GPIO_Cam_Num_Sel1):
        cam_num=cam_num+1
    if GPIO.input(GPIO_Cam_Num_Sel2):
        cam_num=cam_num+2
    if GPIO.input(GPIO_Cam_Num_Sel3):
        cam_num=cam_num+4
    return str(cam_num)

def on_event(message):
    global connected
    #print(u"Got message: {}".format(message))
    if format(message).find("SourceDestroyed event") > -1:
        connected = False

def on_prev_switch(message):		#Event to be used when a Scene is Selected in Preview
    global LED_prev_state
#    print(u"  *****You selected in Preview scene {}".format(message.getSceneName()))
    if format(message.getSceneName()).find(cam_num_str) > -1:       #Set Preview LED status to ON if scene matches this camera
            GPIO.output(GPIO_tally_prev, 1)
            if debug_level >= 2: print(" %s - Preview LED %s ON" % (cam_num_str, "STAYS" if LED_prev_state == 1 else "TURNS"))
            LED_prev_state = 1
    else:       #Set Preview LED status to OFF if scene matches this camera
            GPIO.output(GPIO_tally_prev, 0)
            if debug_level >= 2: print(" %s - Preview LED %s OFF" % (cam_num_str, "STAYS" if LED_prev_state == 0 else "TURNS"))
            LED_prev_state = 0
    if debug_level >= 4: print("Preview Switch Event  - Cam: %s      Preview LED %s   Program LED %s " % (cam_num_str, LED_prev_state, LED_prog_state))


def on_prog_switch(message):		#Event to be used when a Scene is Transitioned into Program
    global LED_prog_state
#    print(u"  *****You Transitioned into Program scene to {}".format(message.getSceneName()))
    if format(message.getSceneName()).find(cam_num_str) > -1:       #Set Program LED status to ON if scene matches this camera
            GPIO.output(GPIO_tally_prog, 1)
            if debug_level >= 2: print(" %s - Program LED %s ON" % (cam_num_str, "STAYS" if LED_prog_state == 1 else "TURNS"))
            LED_prog_state = 1
    else:
            GPIO.output(GPIO_tally_prog, 0)
            if debug_level >= 2: print(" %s - Program LED %s OFF" % (cam_num_str, "STAYS" if LED_prog_state == 0 else "TURNS"))
            LED_prog_state = 0
    if debug_level >= 4: print("Program Switch Event  - Cam: %s      Preview LED %s   Program LED %s " % (cam_num_str, LED_prev_state, LED_prog_state))

#Initialize GPIO input/output pins
if debug_level >= 0: print("**** DEBUG PRINTING ENABLED: Level ",debug_level)
GPIO.setmode(GPIO.BCM)
GPIO.setup(GPIO_connected, GPIO.OUT)
GPIO.output(GPIO_connected, GPIO.HIGH) #Sets output to active High 3.3V
connected = False
LED_prev_state = 0
LED_prog_state = 0
GPIO.setup(GPIO_tally_prev, GPIO.OUT)  #setup output pin for Preview LED
GPIO.setup(GPIO_tally_prog, GPIO.OUT)  #setup ouptut pin for Program LED
GPIO.setup(GPIO_Cam_Num_Sel1, GPIO.IN, pull_up_down=GPIO.PUD_UP) #setup input pins for camera number selection, Sel1 is LSB
GPIO.setup(GPIO_Cam_Num_Sel2, GPIO.IN, pull_up_down=GPIO.PUD_UP)
GPIO.setup(GPIO_Cam_Num_Sel3, GPIO.IN, pull_up_down=GPIO.PUD_UP)
cam_num_str = cam_num_str_base + set_cam_num()     #Read the GPIO inputs to set the cam num - 3 bits, Sel1 is LSB
if debug_level >= 1: print ("Cam Num: ", cam_num_str)
try:
    while 1:
            addr = find_open_socket()
            if addr != "":
                    ws = obsws(addr, port, password)
                    ws.register(on_event)
                    ws.register(on_prog_switch, events.SwitchScenes)	#Event for Scene going to Program
                    ws.register(on_prev_switch, events.PreviewSceneChanged)  #Event for Scene selected in Preview
                    ws.connect()
                    message = ws.call(requests.GetCurrentScene())
                    sn = str(message)[str(message).find("name"):]
                    sn = sn[:sn.find(",")]
                    connected = True
                    if debug_level >= 1: print("Connected!  Current Scene in Program: ",sn)
                    ipAddressHistory = open("obsAddr.log","w")      #Store the connected IP address in the log file
                    ipAddressHistory.write(addr)
                    ipAddressHistory.close()
					#if sn.find(trigger_char) > -1:
                    if sn.find(cam_num_str) > -1:           #Set initial Program LED states  (since changes are based on events) - No way to determine current Preview scene?
#                      GPIO.output(GPIO_tally_prev, 1)
#                      if debug_level >= 1: print("   Preview LED ON")
#                      LED_prev_state = 1
                      GPIO.output(GPIO_tally_prog, 1)
                      if debug_level >= 1: print("   Program LED ON")
                      LED_prog_state = 1
					  
            while connected:        #Flash the Connected LED, 20ms on, 980ms off to indicate connected state=TRUE
                GPIO.output(GPIO_connected, GPIO.LOW)
                time.sleep(0.98)
                GPIO.output(GPIO_connected, GPIO.HIGH)
                time.sleep(0.02)
                if debug_level >= 3: print("Flash connected LED SLOW")
#Insert code to include Prev and Prog
#                if LED_prev_state == 1:
                if LED_prev_state == 1 or LED_prog_state == 1:  #Flash the Connected LED, 20ms on, 200ms off to indicate connected state=TRUE and one of the Tally LEDs on
                    GPIO.output(GPIO_connected, GPIO.LOW)
                    time.sleep(0.2)
                    GPIO.output(GPIO_connected, GPIO.HIGH)
                    time.sleep(0.02)
                    if debug_level >= 3: print("Flash connected LED FAST")
                if debug_level >= 1: print(cam_num_str,"       Preview LED ", LED_prev_state,"Program LED", LED_prog_state)
            try:
                GPIO.output(GPIO_tally_prev, 0)     #Turn off LEDs when shutting down
                GPIO.output(GPIO_tally_prog, 0)     #Turn off LEDs when shutting down
                GPIO.output(GPIO_connected, 0)      #Turn off LEDs when shutting down
                ws.disconnect()
            except:
                pass
            time.sleep(2)

except KeyboardInterrupt:
    GPIO.output(GPIO_tally_prev, 0)     #Turn off LEDs when shutting down
    GPIO.output(GPIO_tally_prog, 0)     #Turn off LEDs when shutting down
    GPIO.output(GPIO_connected, 0)      #Turn off LEDs when shutting down
    try:
      ws.disconnect()
    except:
      pass

GPIO.output(GPIO_tally_prev, 0)     #Turn off LEDs when shutting down
GPIO.output(GPIO_tally_prog, 0)     #Turn off LEDs when shutting down
GPIO.output(GPIO_connected, 0)      #Turn off LEDs when shutting down
GPIO.cleanup()