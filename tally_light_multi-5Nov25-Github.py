
#!/usr/bin/env python
# -*- coding: utf-8 -*-

#Original code written by td0g: https://github.com/td0g/OBS_TallyLight
#Modified in Jul20 by SiliconKnight42 to support multiple lights (Program + Preview) and multiple cameras:  https://github.com/SiliconKnight42/OBS_TallyLight

# 1Nov25 - the old OBS Websock code from 2020 is no longer working reliably (the Tally lights don't realize that OBS shutdown and fail to reconnect to newly restarted OBS session)
#        - Code re-written for latest OBS Websockets version (now included with OBS)

import sys
import time
import RPi.GPIO as GPIO
import logging
from pythonping import ping
import itertools
from multiping import MultiPing
import socket
#logging.basicConfig(level=logging.INFO)        #level can be 'logging.INFO' or 'logging.DEBUG'
sys.path.append('../')
#from obswebsocket import obsws, events, requests  # noqa: E402  # old websockets4 code
import obsws_python as obs  # added 1Nov25 for websockets v5

############## User Configuration ###############
windows_dev = False       #flag for use during Windows development and testing, turn off for Raspberry Pi deployment
debug_level = 1         # Set amount of debug printing (0-4) -> higher is more print statements, 0 is off
#Modified by G Cotton - 18Jun20 to enable multiple tally lights (Preview/Program) and specific Camera # (trigger_char -> cam_num_str) based on GPIO inputs
heartbeat_duration = 90     #Number of seconds between heartbeat checks to ensure OBS is still connected
socket_timeout = 5         #Number of seconds to wait for each attempted port check when trying to locate OBS

## Set the Port # and password to be used with OBS (v5 API usese port 4455, different from v4 API which used 4444)
obs_port = 4455 #Should be 4444 for old version, v5 of OBS websockets uses 4455
obs_password = "12345" #Change to a unique password.  Use the same password in OBS -> Tools -> Websockets Server Settings -> Password

IP_Addr_Base1 = "10.0.0."     #First IP Address base to scan for connection to OBS
IP_Addr_Base2 = "192.168.0."  #Optional Alternate IP Address base to scan

#Input Scene names
#trigger_char = "+" #If this character is found in the scene name then tally light will illuminate
# In final version, use GPIO reads to determine camera number - store as digits in string  - 3bits
cam_num_str_base = "cam " #If this string of chars is found in the scene name then tally light will illuminate - correlate with Cam# to make it easier
#Final format example 'cam 5' - number can be 1 through 8 - UPPER function is used, so this string base is NOT case senstive

#Input/Output pin definitions
GPIO_connected = 16 #-> Drives "Connected" LED (flashes when IP connetion established to OBS)
GPIO_tally_prev = 13 #-> Drives tally light#1 (Preview) -> Orginally 26 in schematic, but 13 in code?
GPIO_tally_prog = 6 #-> Drives tally light#2 (Program) 
GPIO_Cam_Num_Sel1 = 17 # Which GPIO inputs will be used to set the Cam# (3 bits), 1 is LSB
GPIO_Cam_Num_Sel2 = 27  # GPIO 17, 27, 22 should correspond to pin#s 11, 13 and 15 (RPi Zero W) on J8 (40pin header)
GPIO_Cam_Num_Sel3 = 22

if debug_level >= 1: print('GPIOs OUT: Connected-',GPIO_connected, 'Tally Prev-',GPIO_tally_prev, 'Tally Prog-', GPIO_tally_prog)     #Debug print to highlight GPIO Outputs
if debug_level >= 1: print('GPIOs IN: Cam Num Sel1',GPIO_Cam_Num_Sel1, 'Cam Num Sel2',GPIO_Cam_Num_Sel2, 'Cam Num Sel3', GPIO_Cam_Num_Sel3)   #Debug print to highlight GPIO Outputs

############## Script ###############
ipAddressHistory = open("obsAddr.log","r")  # "obsAsddr.log" is a text file with one line -> the last IP address to which the program connected
host = ipAddressHistory.readline()
ipAddressHistory.close()

def scan_all_ip():
    ipRange = []
    if windows_dev:
        if debug_level >=2: print ("Starting in local Windows development mode, searching local loopback addresses.")
        for i in range(1,2):
          ipRange.append("127.0.0."+str(i))         #Temp code for testing on same Windows machine (loopback)
    else:
        if debug_level >=2: print ("Building ping list using %s and %s subnets." % (IP_Addr_Base1,IP_Addr_Base2))
        for i in range(1,253):                  #scans range of IP addresses
          ipRange.append(IP_Addr_Base1 + str(i))
          ipRange.append(IP_Addr_Base2 + str(i))
          if debug_level >=3: print ("Adding IP addresses %s and %s to ping list." % (IP_Addr_Base1 + str(i),IP_Addr_Base2 + str(i)))
    mp = MultiPing(ipRange)     #Ping the set of IP addresses defined by the list in IP_Addr_Base1 and IP_Addr_Base2
    if debug_level >=2: print ("Pinging address list...")
    mp.send()
    responses, no_responses = mp.receive(1)
    for addr, rtt in responses.items():
        if debug_level >= 2: print ("%s responded in %f seconds" % (addr, rtt))
    return responses


def find_open_socket():             #Seach for the open port# at any IPs that responded to the ping - any valid response on the specified port# (in obs_port) is assumed to be OBS
        responses = scan_all_ip()
        for addr, rtt in responses.items():
                if addr == host:
                    if debug_level >= 2: print ("Attempting to connect to " + host)
                    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    sock.settimeout(socket_timeout)     #Set timeout to 5sec
                    result = sock.connect_ex((host,obs_port))
                    sock.settimeout(None)   #Reset timeout to default (apparently this is important?)
                    sock.close
                    if result == 0:
                        return host
        for addr, rtt in responses.items():
            if connected == False:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                if debug_level >= 2: print ("Attempting to connect to " + addr)
                sock.settimeout(socket_timeout)
                result = sock.connect_ex((addr,obs_port))
                sock.settimeout(None)   #Reset timeout to default (apparently this is important?)
                sock.close
                if result == 0:
                    return addr
        return ""
        
def set_cam_num():      #Sets the "Cam_num_str" based on the GPIO Input switches -> 3-bit binary -> returns as string
    cam_num=1       #default cam num
    if debug_level >=2: print("GPIO inputs:  %s:%s, %s:%s, %s:%s" % (GPIO_Cam_Num_Sel1,GPIO.input(GPIO_Cam_Num_Sel1),GPIO_Cam_Num_Sel2,GPIO.input(GPIO_Cam_Num_Sel2),GPIO_Cam_Num_Sel3,GPIO.input(GPIO_Cam_Num_Sel3)))
    if debug_level >=2: print("Curr cam num: %s" % (cam_num))
    if GPIO.input(GPIO_Cam_Num_Sel1):
        cam_num=cam_num+1
        if debug_level >=2: print("Curr cam num: %s" % (cam_num))
    if GPIO.input(GPIO_Cam_Num_Sel2):
        cam_num=cam_num+2
        if debug_level >=2: print("Curr cam num: %s" % (cam_num))
    if GPIO.input(GPIO_Cam_Num_Sel3):
        cam_num=cam_num+4
        if debug_level >=2: print("Curr cam num: %s" % (cam_num))
    if windows_dev:         #For debugging, hard code the cam num
        cam_num=2
    return str(cam_num)

def on_event(message):          #This is the old method for detecting loss of connection?? (API v4)
    global connected
    #print(u"Got message: {}".format(message))
    if format(message).find("SourceDestroyed event") > -1:
        connected = False

def on_exit_started(message):   #This is the new method for detecting loss of connection (API v5)
     global connected
     if debug_level >= 1: print("OBS Exit event received!  Resuming IP Addr search...")
     connected = False      #If OBS Exit event received set connected state to false

def on_current_preview_scene_changed(message):		#Event to be used when a Scene is Selected in Preview - ##Updated name of function to match new OBS Websockets v5 API
    global LED_prev_state
#    print(u"  *****You selected in Preview scene {}".format(message.getSceneName()))
    msg = message.scene_name
    if format(msg.upper()).find(cam_num_str) > -1:       #Set Preview LED status to ON if scene matches this camera, Set to upper case so that it's case insensitive
            GPIO.output(GPIO_tally_prev, 1)
            if debug_level >= 2: print(" %s - Preview LED %s ON" % (cam_num_str, "STAYS" if LED_prev_state == 1 else "TURNS"))
            LED_prev_state = 1
    else:       #Set Preview LED status to OFF if scene matches this camera
            GPIO.output(GPIO_tally_prev, 0)
            if debug_level >= 2: print(" %s - Preview LED %s OFF" % (cam_num_str, "STAYS" if LED_prev_state == 0 else "TURNS"))
            LED_prev_state = 0
    if debug_level >= 4: print("Preview Switch Event  - Cam: %s      Preview LED %s   Program LED %s " % (cam_num_str, LED_prev_state, LED_prog_state))
    if debug_level >= 1: print("LED status for Cam# %s    Preview LED %s ---  Program LED %s" % (cam_num_str, LED_prev_state,LED_prog_state), end='\r')

def on_current_program_scene_changed(message):		#Event to be used when a Scene is Transitioned into Program
    global LED_prog_state
#    print(u"  *****You Transitioned into Program scene to {}".format(message.getSceneName()))
    msg = message.scene_name
    if format(msg.upper()).find(cam_num_str) > -1:       #Set Program LED status to ON if scene matches this cameram, Set to upper case so that it's case insensitive
            GPIO.output(GPIO_tally_prog, 1)
            if debug_level >= 2: print(" %s - Program LED %s ON" % (cam_num_str, "STAYS" if LED_prog_state == 1 else "TURNS"))
            LED_prog_state = 1
    else:
            GPIO.output(GPIO_tally_prog, 0)
            if debug_level >= 2: print(" %s - Program LED %s OFF" % (cam_num_str, "STAYS" if LED_prog_state == 0 else "TURNS"))
            LED_prog_state = 0
    if debug_level >= 4: print("Program Switch Event  - Cam: %s      Preview LED %s   Program LED %s " % (cam_num_str, LED_prev_state, LED_prog_state))
    if debug_level >= 1: print("LED status for Cam# %s    Preview LED %s ---  Program LED %s" % (cam_num_str, LED_prev_state,LED_prog_state), end='\r')




#Initialize GPIO input/output pins
print ("Tally Light Python script starting.")
if debug_level >= 1: print("**** DEBUG PRINTING ENABLED: Level ",debug_level)
GPIO.setmode(GPIO.BCM)
GPIO.setup(GPIO_connected, GPIO.OUT)
GPIO.output(GPIO_connected, GPIO.HIGH) #Sets output to active High 3.3V
connected = False
LED_prev_state = 0
LED_prog_state = 0
GPIO.setup(GPIO_tally_prev, GPIO.OUT)  #setup output pin for Preview LED
GPIO.setup(GPIO_tally_prog, GPIO.OUT)  #setup ouptut pin for Program LED
GPIO.setup(GPIO_Cam_Num_Sel1, GPIO.IN, pull_up_down=GPIO.PUD_DOWN) #setup input pins for camera number selection, Sel1 is LSB
GPIO.setup(GPIO_Cam_Num_Sel2, GPIO.IN, pull_up_down=GPIO.PUD_DOWN) #DOWN means open is 0
GPIO.setup(GPIO_Cam_Num_Sel3, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
cam_num_str = cam_num_str_base.upper() + set_cam_num()     #Read the GPIO inputs to set the cam num - 3 bits, Num_Sel1 is LSB,   Set to upper case so that it's case insensitive
print ("Tally Light Python script running - Cam Num: ", cam_num_str)
try:
    while 1:
            addr = find_open_socket()
            if addr != "":
                    #old websockets v4 code
                    #ws = obsws(addr, port, password)
                    #ws.register(on_event)
                    #ws.register(on_prog_switch, events.SwitchScenes)	#Event for Scene going to Program
                    #ws.register(on_prev_switch, events.PreviewSceneChanged)  #Event for Scene selected in Preview
                    #ws.connect()
                    #message = ws.call(requests.GetCurrentScene())  #Get the Name of the Scene currently in Program (chk connection and set initial Prog LED state)
                    #sn = str(message)[str(message).find("name"):]
                    #sn = sn[:sn.find(",")]
                    #usn = sn.upper()
                    connected = False
                    LED_prev_state = 0          #If assumption is that we are not connected, then both LEDs should be off
                    LED_prog_state = 0
                    
                    while connected is False:
                        try:
                            #new websockets v5 code
                            if debug_level >= 3: print("Found OBS - trying to connect and setup Reqeust and Event clients...")
                            reqcl = obs.ReqClient(host=addr, port=obs_port, password=obs_password)      #Setup 2 clients - 1 for sending requests and 1 for monitoring events - this required to be separate
                            evtcl = obs.EventClient(host=addr, port=obs_port, password=obs_password)
                        
                            evtcl.callback.register(on_current_preview_scene_changed)
                            evtcl.callback.register(on_current_program_scene_changed)        
                            evtcl.callback.register(on_exit_started)
                            message = reqcl.get_current_program_scene()
                            sn = message.scene_name
                            usn = sn.upper()                 
                            connected = True
                        except:
                            time.sleep(1)     #wait 1 second if connection error
                            if debug_level >= 1: print("Found OBS and tried to connect, but couldn't.  Waiting for OBS to be ready...")
                            pass
                    
                    if debug_level >= 1: print("Connected to OBS and Request/Event clients established!  Current Scene in Program: ",sn, " ", usn)
                    ipAddressHistory = open("obsAddr.log","w")      #Store the connected IP address in the log file
                    ipAddressHistory.write(addr)
                    ipAddressHistory.close()

                    message = reqcl.get_current_preview_scene()
                    sn = message.scene_name
                    usn = sn.upper()                 
                    if usn.find(cam_num_str) > -1:           #Set initial Preivew LED states  (since changes are based on events)
                      GPIO.output(GPIO_tally_prev, 1)
                      if debug_level >= 1: print("   Preview LED ON")
                      LED_prev_state = 1

                    message = reqcl.get_current_program_scene()
                    sn = message.scene_name
                    usn = sn.upper()                 
                    if usn.find(cam_num_str) > -1:           #Set initial Program LED state
                      GPIO.output(GPIO_tally_prog, 1)
                      if debug_level >= 1: print("   Program LED ON")
                      LED_prog_state = 1

                    # old code
#                    message = ws.call(requests.GetPreviewScene())   #Get the Name of the Scene currently in Preview (chk connection and set initial Prog LED state)
#                    sn = str(message)[str(message).find("name"):]
#                    sn = sn[:sn.find(",")]
#                    usn = sn.upper()
#                    if usn.find(cam_num_str) > -1:           #Set initial Program LED states  (since changes are based on events) - No way to determine current Preview scene?
#                      GPIO.output(GPIO_tally_prev, 1)
#                      if debug_level >= 1: print("   Preview LED ON")
#                      LED_prev_state = 1
            watchdog = 0           #Setup watchdog counter for Heartbeat check
            while connected:        #Flash the Connected LED, 20ms on, 980ms off to indicate connected state=TRUE
                watchdog = watchdog + 1           #Increment watchdog counter every loop - essentially once per second
                GPIO.output(GPIO_connected, GPIO.LOW)
                time.sleep(0.98)
                GPIO.output(GPIO_connected, GPIO.HIGH)
                time.sleep(0.02)
                if debug_level >= 3: print("Flash connected LED SLOW")
                if LED_prev_state == 1 or LED_prog_state == 1:  #Flash the Connected LED, 20ms on, 200ms off to indicate connected state=TRUE and one of the Tally LEDs on
                    GPIO.output(GPIO_connected, GPIO.LOW)
                    time.sleep(0.2)
                    GPIO.output(GPIO_connected, GPIO.HIGH)
                    time.sleep(0.02)
                    if debug_level >= 3: print("Flash connected LED FAST")
                if debug_level >= 1: print("LED status for Cam# %s    Preview LED %s ---  Program LED %s" % (cam_num_str, LED_prev_state,LED_prog_state), end='\r')
                if debug_level >= 2: print("")	#add a Linefeed if other debug data
                if debug_level >= 3: print("Watchdog counter: ", watchdog)
                if watchdog > heartbeat_duration:       #check heartbeat every 30 secs (or whatever heartbeat_duration is set to)
                    while False:         #Skip this check -> always run heartbeat check in try block to catch potential errors
                         pass
                    try:
                        watchdog = 0                        #Reset watchdog counter everytime we conduct a heartbeat check
                        message1 = reqcl.get_version()       #This simple 'version request' is used as a watchdog to ensure connection is still alive (there is no way to monitor the event client?)                                               
                        if len(message1.obs_version)>1:          #check that at least one character is in returned as part version number (really we're looking for an error or lack of response here)
                            if debug_level >= 3: print("Heartbeat check response received: ", message1.obs_version)
                        else:
                            raise Exception("Received Heartbeat message too short.")
                    except Exception as e:      #Heartbeat fails for any received message that isn't at least 2 characters long or any API error returned
                            if debug_level >= 3: print("Heartbeat check failed. Exception message: ",e)
                            connected = False       #if heartbeat check fails, change connection flag to allow Python script to resume searching for OBS
            try:
                if debug_level >= 1: print("")	#add a Linefeed if other debug data
                if debug_level >= 1: print("OBS disconnected, reconnectng...")
                GPIO.output(GPIO_tally_prev, 0)     #Turn off LEDs when shutting down
                GPIO.output(GPIO_tally_prog, 0)     #Turn off LEDs when shutting down
                GPIO.output(GPIO_connected, 0)      #Turn off LEDs when shutting down
                #ws.disconnect()        #this is old code from the v4 API
                reqcl.disconnect()      #Ensure both client objects are disconnected for the new v5 API
                evtcl.disconnect()
            except:
                pass
            time.sleep(2)

except KeyboardInterrupt:
    if debug_level >= 1: print("")	#add a Linefeed if other debug data
    if debug_level >= 1: print("Keyboard Interrupt received, shutting down Python script...")
    GPIO.output(GPIO_tally_prev, 0)     #Turn off LEDs when shutting down
    GPIO.output(GPIO_tally_prog, 0)     #Turn off LEDs when shutting down
    GPIO.output(GPIO_connected, 0)      #Turn off LEDs when shutting down
    try:
      #ws.disconnect()      #this is old code from the v4 API
      obs.ReqClient.disconnect()      #this is the new v5 API
      obs.EvtClient.disconnect()      #this is the new v5 API
    except:
      pass
    
if debug_level >= 1: print("")	#add a Linefeed if other debug data
print ("Tally Light Python script exiting...")
GPIO.output(GPIO_tally_prev, 0)     #Turn off LEDs when shutting down
GPIO.output(GPIO_tally_prog, 0)     #Turn off LEDs when shutting down
GPIO.output(GPIO_connected, 0)      #Turn off LEDs when shutting down
GPIO.cleanup()
