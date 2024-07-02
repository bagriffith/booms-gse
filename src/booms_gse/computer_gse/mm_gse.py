import asyncio
import datetime
import socket
import struct
from copy import deepcopy
from functools import partial

import numpy as np

#import holoviews as hv
#from holoviews import dim, opts
#import holoviews.operation.datashader as hd
#from datashader.colors import Sets1to3
#hv.extension('bokeh')


import crcmod
crc16 = crcmod.predefined.mkPredefinedCrcFun('modbus')

import astropy.units as u
from astropy.coordinates import Angle

from bokeh.events import ButtonClick
from bokeh.io import curdoc
from bokeh.layouts import column, row
from bokeh.models import Button, ColumnDataSource, Div, HoverTool, TextInput, Toggle
from bokeh.palettes import Colorblind8
from bokeh.plotting import figure

"""
==========================================================================================================================
GSE Setup
==========================================================================================================================
"""


#Port setup
DEFAULT_REMOTE_IP = "192.168.2.101"
DEFAULT_SELF_IP = "192.168.2.1"

CMD_PORT = 50501
TM_PORT = 20501

#A function to handle the bitfield
def split(word):
    return [char for char in word]


command_packet = bytearray()
command_sequence_number = -1
acknowledged_command_sequence_number = -1



#Initializing some variables, arrays, etc.
telemetry_info = np.zeros((256, 256))
telemetry_info_lock = asyncio.Lock()

#Create arrays full of junk data to test plotting strain
number = int(0)

'''
=============================================================================================================
!! The bokeh plotting bogs down between 2e4 and 3e4 seconds (because there are 30 data streams being plotted)
=============================================================================================================
'''


zeros = np.zeros(number)
#zeros = zeros + 1
#zeros = zeros.tolist()


faketime = np.arange(number)

#offset = 946728000000. #Milliseconds from January 1970 to January 2000
#offset2 = 43200000. #Make a 12 hour adjustment (I think for UTC time)
#faketimeA = faketime + offset - offset2
#faketime = faketime + offset - offset2
#faketime = faketime * 1000. #Transform into milliseconds?

#faketime = np.zeros(number)
#faketime = faketime.tolist()

#Ability to add junk data to beginning of GSE
#Use 0 if you don't wish to do this
#This is for testing the plotting slow down
junk = 0
faketime =np.zeros(junk)
faketimeA = np.zeros(junk)
zeros = np.zeros(junk)



#Data Rates array
data_rates = ColumnDataSource(data=dict(date=faketimeA, 
                                        dateG=faketime,
                                        total=zeros, 
                                        interface=zeros, 
                                        imager_hk=zeros, 
                                        imager_event=zeros, 
                                        gps=zeros, 
                                        mag=zeros, 
                                        spec=zeros))

#Statistics relating to instrument performance
statistics = ColumnDataSource(data=dict(date=faketimeA, dateG=faketime,
                                        events_0=zeros, remain_0=zeros, bad_0=zeros,
                                        events_1=zeros, remain_1=zeros, bad_1=zeros,
                                        events_2=zeros, remain_2=zeros, bad_2=zeros,
                                        events_3=zeros, remain_3=zeros, bad_3=zeros,
                                        events_4=zeros, remain_4=zeros, bad_4=zeros,
                                        events_5=zeros, remain_5=zeros, bad_5=zeros,
                                        events_6=zeros, remain_6=zeros, bad_6=zeros,
                                        events_7=zeros, remain_7=zeros, bad_7=zeros
                                       ))

#GPS info
gps_info = {'hour': 0,
            'minute': 0,
            'second': 0,
            'latitude': Angle(0*u.deg),
            'longitude': Angle(0*u.deg),
            'altitude': 0*u.m,
            'quality': "",
            'num_sat': 0,
            'hdop': 0,
            'geoidal': 0*u.m,
            'gondola': 0,
           }
gps_info_lock = asyncio.Lock()
quality_strings = ['invalid fix', 'GPS fix', 'SBAS-corrected fix', '', '', '','', 'cached']

#PPS Info
pps_info = {'day_offset': 0,
            'hour': 0,
            'minute': 0,
            'second': 0,
            'clock_difference': 0*u.s,
            'gondola': 0,
            'datetime' : datetime.datetime(2000, 1, 1)
           }
pps_info_lock = asyncio.Lock()

#Housekeeping Info
house_info = {'seq': 0,
              'gon_t': 0*u.s,
              'gps': "",
              'pps': "",
              'sbd': "",
              'gnd': "",
              'evtm': "",
              'rate': "",
              'cmd': 0,
              'cpu': 0*u.pct,
              'disk': 0*u.pct,
              'up': 0*u.s,
              'comp_byte': 0,
              'gps_byte': 0,
              'imag_byte': 0,
              'spec_byte': 0,
              'mag_byte': 0,
              'temp_acpitz': 0,
              'temp_soc_dts0': 0,
              'temp_soc_dts1': 0,
              'temp_cpu_max': 0
              }
house_info_lock = asyncio.Lock()
gps_strings = ['NO GPS fix','GPS fix']
pps_strings = ['NO PPS from GPS device','Using PPS from GPS device']
sbd_strings = ['NOT in middle of sending SBD packets','Sending SBD packets']
gnd_strings = ['Telemetry NOT sent to ground port','Telemetry being sent to ground port']
evtm_strings = ['Telemetry NOT sent via LOS EVTM link','Telementry being sent via LOS EVTM link']
rate_strings = ['EVTM NOT rate limited','EVTM being rate limited']
            

#Magnetometer Info
mag_info = {'bx': 0,
            'by': 0,
            'bz': 0,
            'total': 0,
            'temp': 0*u.K,
            'adc': 0
            }
mag_info_lock = asyncio.Lock()

mag_data = ColumnDataSource(data=dict(date=zeros,
                                    dateG=zeros,
                                    bx=zeros,
                                    by=zeros,
                                    bz=zeros,
                                    total=zeros))

#Timing adjustment info
timing = ColumnDataSource(data=dict(date=faketimeA, dateG=faketime, gps_to_pps=zeros, pps_to_sbc=zeros))


#Set the Holoviews output as bokeh
#hv.output(backend="bokeh")


"""
==========================================================================================================================
Telemetry parsing
==========================================================================================================================
"""

#Parse the incoming statistics packet
async def parse_statistics(data):
    async with pps_info_lock:
        global pps_info
        date = deepcopy(pps_info['datetime'])
        dateG = deepcopy(pps_info['gondola'])

#Read in the new statistics from the packet
    new_statistics = dict(date=[date],dateG=[dateG])
    for i in range(8):
        new_statistics[f'events_{i}'] = [struct.unpack('<H', data[6*i + 16: 6*i + 18])[0]]
        new_statistics[f'remain_{i}'] = [struct.unpack('<H', data[6*i + 18: 6*i + 20])[0]]
        bad_bytes = struct.unpack('<H', data[6*i + 20: 6*i + 22])[0]
        new_statistics[f'bad_{i}'] = [bad_bytes]
        if bad_bytes > 0:
            print(f"Gondola time: {data[10:16].hex()}, Imager: {i}, Number of bad bytes: {bad_bytes}")


	#Add new statistics into the initialized structure
    doc.add_next_tick_callback(partial(statistics.stream, new_statistics))
    
    #Create a copy, culled version of the data structure



#Parse the incoming GPS packet
async def parse_gps_position(data):
    async with gps_info_lock:
        global gps_info
        gps_info['hour'] = data[16]
        gps_info['minute'] = data[17]
        gps_info['second'] = data[18]
        gps_info['latitude'] = Angle(struct.unpack('<d', data[20:28])[0]*u.deg)
        gps_info['longitude'] = Angle(struct.unpack('<d', data[28:36])[0]*u.deg)
        gps_info['altitude'] = struct.unpack('<H', data[42:44])[0]*u.m
        gps_info['quality'] = quality_strings[data[36]]
        gps_info['num_sat'] = data[37]
        gps_info['hdop'] = struct.unpack('<f', data[38:42])[0]
        gps_info['geoidal'] = struct.unpack('<h', data[44:46])[0]*u.m
        gps_info['gondola'] = struct.unpack('<q', data[10:16] + b'00')[0] / 1e7

        if data[36] != 1:
            #print(gps_info)
            pass

    doc.add_next_tick_callback(update_gps_info_div)

#Parse the incoming PPS packet
async def parse_pps(data):
    async with pps_info_lock:
        global pps_info
        pps_info['day_offset'] = data[16]
        pps_info['hour'] = data[17]
        pps_info['minute'] = data[18]
        pps_info['second'] = data[19]
        pps_info['clock_difference'] = struct.unpack('<l', data[20:24])[0]*u.us
        pps_info['second_offset'] = struct.unpack('<L', data[24:28])[0]*u.s
        pps_info['gondola'] = struct.unpack('<q', data[10:16] + b'00')[0] / 1e7

        pps_info['datetime'] = datetime.datetime(2000, 1, 1 + pps_info['day_offset'],
                                                 pps_info['hour'], pps_info['minute'], pps_info['second'])


        if pps_info['day_offset'] == 0 and pps_info['hour'] == 0 and pps_info['minute'] == 0 and pps_info['second'] == 0:
            pps_info['datetime'] += datetime.timedelta(0, pps_info['second_offset'].to_value('s'))

#Choose to assign GPS or Gondola time to the date array
        date = deepcopy(pps_info['datetime'])
        dateG = deepcopy(pps_info['gondola'])
        #print('PPS_Info is runnning')

        async with gps_info_lock:
            global gps_info
            if gps_info['gondola'] > 0:  # if at least one GPS position packet has been received
                #if pps_info['hour'] == 0 and pps_info['minute'] == 0:
                #    print(pps_info)
                #    print(gps_info)
                #if pps_info['second_offset'] != 1*u.s:
                #    print(pps_info)
                #    print(gps_info)
                gps_to_pps = pps_info['gondola'] - gps_info['gondola']
                new_timing = dict(date=[date],
                			    dateG=[dateG],
                                  gps_to_pps=[gps_to_pps],
                                  pps_to_sbc=[pps_info['clock_difference'].to_value('s')])


#Add new timing data to the timing array
                doc.add_next_tick_callback(partial(timing.stream, new_timing))

        async with telemetry_info_lock:
            global telemetry_info

#Read incoming data rate information
            new_data_rates = dict(date=[date],
            				    dateG=[dateG],
                                  total=[np.sum(telemetry_info)],
                                  interface=[np.sum(telemetry_info[0xa0, :])],
                                  imager_hk=[np.sum(telemetry_info[0xc0:0xc8, 0x09:0x10])],
                                  imager_event=[np.sum(telemetry_info[0xc0:0xc8, 0xc0])],
                                  spec = [np.sum(telemetry_info[0xd0:0xd4,0xd0])],
                                  gps=[np.sum(telemetry_info[0x60, 0x60:0x63])],
                                  mag=[np.sum(telemetry_info[0xb0, :])]
                                 )
            telemetry_info = np.zeros((256, 256))
#Add new data rate information to the data rate array
            doc.add_next_tick_callback(partial(data_rates.stream, new_data_rates))

    doc.add_next_tick_callback(update_pps_info_div)

#Parse the incoming housekeeping packet
async def parse_house(data):
    async with house_info_lock:
        global house_info
        seq_bin = data[7:9].zfill(2)
        seq_hex = seq_bin.hex()

        gon_bin = data[9:16]
        gon_hex = hex(int.from_bytes(gon_bin,byteorder='little'))
            
        bit_bin= data[16]
        bitfield = bin(bit_bin)[2:].zfill(8)
        bit_list = split(bitfield)
        bit_list.reverse()
            
        cmd_bin = data[17]
        cmd_hex = hex(cmd_bin)

        cpu_bin = data[18:20].zfill(2)
        cpu_hex = hex(int.from_bytes(cpu_bin,byteorder='little'))
        cpu = int(cpu_hex,16)/100.

        disk_bin = data[20:22]
        disk_hex = hex(int.from_bytes(disk_bin,byteorder='little'))
        disk = int(disk_hex,16)/100.

        up_bin = data[22:26]
        up_hex = hex(int.from_bytes(up_bin,byteorder='little'))
            
        #Read in telemetry info bytes
        comp_tele_bin = data[26]
        gps_tele_bin = data[27]
        imag_tele_bin = data[28:32]
        imag_tele_hex = hex(int.from_bytes(imag_tele_bin,byteorder='little'))
        spec_tele_bin = data[32:34]
        spec_tele_hex = hex(int.from_bytes(spec_tele_bin,byteorder='little'))
        mag_tele_bin = data[34]
        #mag_tele_hex = hex(int.from_bytes(mag_tele_bin,byteorder='little'))

        #Read in the temperature data
        temp_acp_bin = data[35]
        #temp_acp_hex = hex(int,from_bytes(temp_acp_bin,byteorder='little'))
        temp_dts0_bin = data[36]
        #temp_dts0_hex = hex(int,from_bytes(temp_dts0_bin,byteorder='little'))
        temp_dts1_bin = data[37]
        #temp_dts1_hex = hex(int,from_bytes(temp_dts1_bin,byteorder='little'))
        temp_cpu_bin = data[38]
        #temp_cpu_hex = hex(int,from_bytes(temp_cpu_bin,byteorder='little'))

        house_info['seq'] = int(seq_hex,16)
        house_info['gon_t'] = int(gon_hex,16)
        house_info['gps'] = gps_strings[int(bit_list[0])]
        house_info['pps'] = pps_strings[int(bit_list[1])]
        house_info['sbd'] = sbd_strings[int(bit_list[4])]
        house_info['gnd'] = gnd_strings[int(bit_list[5])]
        house_info['evtm'] = evtm_strings[int(bit_list[6])]
        house_info['rate'] = rate_strings[int(bit_list[7])]
        house_info['cmd'] = cmd_hex
        house_info['cpu'] = cpu
        house_info['disk'] = disk
        house_info['up'] = int(up_hex,16)
        house_info['comp_byte'] = comp_tele_bin
        house_info['gps_byte'] = gps_tele_bin
        house_info['imag_byte'] = int(imag_tele_hex,16)
        house_info['spec_byte'] = int(spec_tele_hex,16)
        house_info['mag_byte'] = mag_tele_bin
        house_info['temp_acpitz'] = temp_acp_bin
        house_info['temp_soc_dts0'] = temp_dts0_bin
        house_info['temp_soc_dts1'] = temp_dts1_bin
        house_info['temp_cpu_max'] = temp_cpu_bin
    doc.add_next_tick_callback(update_house_info_div)

#Parse the incoming magnetometer packet
async def parse_mag(data):
    async with mag_info_lock:
        global mag_info, pps_info
        date = deepcopy(pps_info['datetime'])
        dateG = deepcopy(pps_info['gondola'])

        #Starter bytes
        #start = 'bfaa'
        #end_ = '55'

        #mag_bin = data[16:18].zfill(2)
        #mag_hex = mag_bin.hex()
        
        #data_hex = data.hex()
        #index = data_hex.index(start)
        #end_index = data_hex.index(end_)
        #index = int(index/2)
        #end_index = int(end_index/2)

        #if (end_index - index) != 18:
        #    print('Packet is not right size')
        #    print(end_index - index)

        #mag_packet = data[index:index+18]

        bx_bin = data[18:21].zfill(3)
        #bx_hex = hex(int.from_bytes(bx_bin,byteorder='little'))
        bx_hex = bx_bin.hex()

        by_bin = data[21:24].zfill(3)
        #by_hex = hex(int.from_bytes(by_bin,byteorder='little'))
        by_hex = by_bin.hex()

        bz_bin = data[24:27].zfill(3)
        #bz_hex = hex(int.from_bytes(bz_bin,byteorder='little'))
        bz_hex = bz_bin.hex()

        temp_bin = data[27:30].zfill(3)
        #temp_hex = hex(int.from_bytes(temp_bin,byteorder='little'))
        temp_hex = temp_bin.hex()

        adc_bin = data[30:33]
        adc_hex = adc_bin.hex()

        #Convert to decimals
        bx_dec = int(bx_hex,16)
        by_dec = int(by_hex,16)
        bz_dec = int(bz_hex,16)
        t_dec = int(temp_hex,16)
        adc_dec = int(adc_hex,16)

        #bx2_dec = int(bx2_hex,16)
        #bx3_dec = int(bx3_hex,16)
        #bx4_dec = int(bx4_hex,16)

        #Convert to physical units
        bx = 100.*(bx_dec-8388608)/8388607
        by = 100.*(by_dec-8388608)/8388607
        bz = 100.*(bz_dec-8388608)/8388607
        t = 2980.*(t_dec-8388608)/8388607
        adc = 100.*(adc_dec-8388608)/8388607

        #Calculate the magnitude
        b_total = ((bx**2)+(by**2)+(bz**2))**0.5
        
        mag_info['bx'] = bx
        mag_info['by'] = by
        mag_info['bz'] = bz
        mag_info['total'] = b_total
        mag_info['temp'] = t
        mag_info['adc'] = adc

        new_mag = dict(date=[date],dateG=[dateG],
                        bx=[bx],
                        by=[by],
                        bz=[bz],
                        total=[b_total])

        doc.add_next_tick_callback(partial(mag_data.stream, new_mag))
    doc.add_next_tick_callback(update_mag_info_div)

class TelemetryProtocol:
    def connection_made(self, transport):
        self.transport = transport

    def datagram_received(self, data, addr):
        loop = asyncio.get_running_loop()

        tm = bytearray(data)
        tm[2:4] = [0, 0]
        hb, lb = divmod(crc16(tm), 256)
        if data[2:4] != bytearray([lb, hb]):
            print("Bad checksum")
            return

        sysid = tm[4]
        tmtype = tm[5]
        #print(sysid, tmtype)
        if tmtype == 0x01:
            global acknowledged_command_sequence_number
            acknowledged_command_sequence_number = int.from_bytes(tm[8:10], "little")

            doc.add_next_tick_callback(update_command_info_div)
        elif (sysid, tmtype) == (0x60, 0x60):
            loop.create_task(parse_pps(tm))
        elif (sysid, tmtype) == (0x60, 0x61):
            loop.create_task(parse_gps_position(tm))
        elif (sysid, tmtype) == (0x60, 0x62):
            # TODO
            pass
        elif (sysid, tmtype) == (0xa0, 0x0c):
            loop.create_task(parse_statistics(tm))
        elif sysid & 0xf0 == 0xc0:
            # TODO
            pass
        elif (sysid, tmtype) == (0xb0, 0xb0):
            loop.create_task(parse_mag(tm))
        elif (sysid, tmtype) == (0xa0, 0x02):
            loop.create_task(parse_house(tm))
        elif sysid & 0xf0 == 0xd0:
            # TODO
            pass
        else:
            print(f"Unhandled telemetry packet (0x{sysid:02x}/0x{tmtype:02x})")

        loop.create_task(update_telemetry_info(sysid, tmtype, len(tm)))


async def update_telemetry_info(sysid, tmtype, size):
    async with telemetry_info_lock:
        global telemetry_info
        telemetry_info[sysid, tmtype] += size


"""
==========================================================================================================================
Commanding
==========================================================================================================================
"""

def update_command_info_div():
    command_info_div.text = (f"Command #{command_sequence_number}: {command_packet.hex()}<br>"
                             f"Acknowledgement: #{acknowledged_command_sequence_number}")


def send_command(sysid, cmdtype, payload=[]):
    global command_packet, command_sequence_number
    command_sequence_number += 1

    payload = bytearray(payload)
    command_packet = (bytearray.fromhex('90eb0000') +
                      bytearray([sysid, cmdtype, command_sequence_number, len(payload)]) +
                      payload)

    hb, lb = divmod(crc16(command_packet), 256)
    command_packet[2:4] = [lb, hb]

    print(f"Sending {command_packet.hex()} to {remote_ip_text.value}")

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.sendto(command_packet, (remote_ip_text.value, CMD_PORT))

    doc.add_next_tick_callback(update_command_info_div)


def route_telemetry_command():
    send_command(0xa0, 0xa1, map(int, self_ip_text.value.split('.')))


def send_raw_command():
    if len(raw_command_text.value) >= 4:
        raw_command = bytearray.fromhex(raw_command_text.value)
        send_command(raw_command[0], raw_command[1], raw_command[2:])


"""
==========================================================================================================================
GPS
==========================================================================================================================
"""

def update_gps_info_div():
    gps_info_div.text = (f"GPS time: {gps_info['hour']:02}:{gps_info['minute']:02}:{gps_info['second']:02}<br>"
                         f"Lat: {gps_info['latitude'].to_string()}<br>"
                         f"Lon: {gps_info['longitude'].to_string()}<br>"
                         f"Alt: {gps_info['altitude']}<br>"
                         f"# of satellites: {gps_info['num_sat']}<br>"
                         f"Quality: {gps_info['quality']}<br>"
                         f"HDOP: {gps_info['hdop']}<br>"
                         f"Geoidal sep: {gps_info['geoidal']}<br>"
                         f"Gondola: {gps_info['gondola']}<hr>")


"""
==========================================================================================================================
PPS
==========================================================================================================================
"""

def update_pps_info_div():
    pps_info_div.text = (f"GPS time at PPS: {pps_info['hour']:02}:{pps_info['minute']:02}:{pps_info['second']:02} + {pps_info['day_offset']}d<br>"
                         f"Clock diff: {pps_info['clock_difference']}<br>"
                         f"Applied offset: {pps_info['second_offset']}<br>"
                         f"Gondola: {pps_info['gondola']}")



"""
==========================================================================================================================
Magnetometer
==========================================================================================================================
"""

def update_mag_info_div():
    mag_info_div.text = (f"X magnetic field (uT): {mag_info['bx']}<br>"
                        f"Y magnetic field (uT): {mag_info['by']}<br>"
                        f"Z magnetic field (uT): {mag_info['bz']}<br>"
                        f"Total magnetic field (uT): {mag_info['total']}<br>"
                        f"Temperature: {mag_info['temp']}<br>"
                        f"ADC Offset: {mag_info['adc']}")


"""
==========================================================================================================================
Housekeeping
==========================================================================================================================
"""
def update_house_info_div():
    house_info_div.text = (f"Sequence number: {house_info['seq']}<br>"
                           f"Gondola time: {house_info['gon_t']}<br>"
                           f"{house_info['gps']}<br>"
                           f"{house_info['pps']}<br>"
                           f"{house_info['sbd']}<br>"
                           f"{house_info['gnd']}<br>"
                           f"{house_info['evtm']}<br>"
                           f"{house_info['rate']}<br>"
                           f"Latest command: {house_info['cmd']}<br>"
                           f"CPU Usage: {house_info['cpu']}<br>"
                           f"Disk Usage: {house_info['disk']}<br>"
                           f"Uptime: {house_info['up']}<br>"
                           f"Bytes from computer: {house_info['comp_byte']}<br>"
                           f"Bytes from GPS: {house_info['gps_byte']}<br>"
                           f"Bytes from imagers: {house_info['imag_byte']}<br>"
                           f"Bytes from spectrometers: {house_info['spec_byte']}<br>"
                           f"Bytes from magnetometer: {house_info['mag_byte']}<br>"
                           f"Temperature (C) (acpitz): {house_info['temp_acpitz']}<br>"
                           f"Temperature (C) (dts0): {house_info['temp_soc_dts0']}<br>"
                           f"Temperature (C) (dts1): {house_info['temp_soc_dts1']}<br>"
                           f"Temperature (C) (Max CPU): {house_info['temp_cpu_max']}")


"""
==========================================================================================================================
Interface Layout and Plotting
==========================================================================================================================
"""

#Creates plot info hover tool
def create_hover_tool(list_of_keys):
    tooltips = [('date', '@date{%F %T}')] + [(s, '@'+s) for s in list_of_keys]
    return HoverTool(tooltips=tooltips, formatters={'@date': 'datetime'}, mode='mouse')

#Create a plot Toggle button
toggle = Toggle(label = 'Change between GPS/Gondola Time',active=False)


#Displays IP information
remote_ip_text = TextInput(title="Remote IP", value=DEFAULT_REMOTE_IP)
self_ip_text = TextInput(title="Self IP", value=DEFAULT_SELF_IP)

#Creates "Route telemetry" button that triggers route_telemetry_command
route_button = Button(label="Route telemetry")
route_button.on_event(ButtonClick, route_telemetry_command)

#Creates "Raw Command (hex)" text field
raw_command_text = TextInput(title="Raw command (hex)")

#Inputs command from text field into send_raw_command function
send_raw_command_button = Button(label="Send raw command")
send_raw_command_button.on_event(ButtonClick, send_raw_command)

command_info_div = Div(text="")

command_block = column(remote_ip_text,
                       self_ip_text,
                       route_button,
                       raw_command_text,
                       send_raw_command_button,
                       command_info_div)

gps_info_div = Div(text="")
pps_info_div = Div(text="")

gps_block = column(gps_info_div, pps_info_div)

house_info_div = Div(text="")
mag_info_div = Div(text="")

house_block = column(house_info_div, mag_info_div)

#**************************************************************************************************************************
# PLOTTING [Gondola time plots are appended with a 'G'
#__________________________________________________________________________________________________________________________

#Sets which plotting tools to be included
tools = "box_zoom,crosshair,pan,reset,save,wheel_zoom"


#LOD_THRESHOLD LIMIT
limit = 10000


#Sets up data rates plot
#Date Time
data_rates_plot = figure(plot_width=400, plot_height=300, x_axis_type='datetime', tools=tools,
                         y_axis_label='bytes/s', title='Telemetry data rates')
data_rates_plotG = figure(plot_width=400, plot_height=300, x_axis_type='linear', tools=tools,
                         y_axis_label='bytes/s', title='Telemetry data rates (Gondola Time)',
                         x_axis_label='Elapsed Time (s)')

#Adds tools to data rates plot
data_rates_plot.add_tools(create_hover_tool(['total', 'interface', 'gps', 'imager_hk', 'imager_event', 'mag']))
data_rates_plotG.add_tools(create_hover_tool(['total', 'interface', 'gps', 'imager_hk', 'imager_event', 'mag']))


#Plots the various data sets
data_rates_plot.line('date', 'total', source=data_rates, line_color=Colorblind8[7], legend_label='Total')
data_rates_plot.line('date', 'interface', source=data_rates, line_color=Colorblind8[0], legend_label='Interface')
data_rates_plot.line('date', 'gps', source=data_rates, line_color=Colorblind8[1], legend_label='GPS & PPS')
data_rates_plot.line('date', 'imager_hk', source=data_rates, line_color=Colorblind8[2], legend_label='Imager H/K')
data_rates_plot.line('date', 'imager_event', source=data_rates, line_color=Colorblind8[3], legend_label='Imager Events')
data_rates_plot.line('date', 'spec', source=data_rates, line_color=Colorblind8[5], legend_label='Spec')
data_rates_plot.line('date', 'mag', source=data_rates, line_color=Colorblind8[4], legend_label='Magnetometer')

data_rates_plotG.line('dateG', 'total', source=data_rates, line_color=Colorblind8[7], legend_label='Total')
data_rates_plotG.line('dateG', 'interface', source=data_rates, line_color=Colorblind8[0], legend_label='Interface')
data_rates_plotG.line('dateG', 'gps', source=data_rates, line_color=Colorblind8[1], legend_label='GPS & PPS')
data_rates_plotG.line('dateG', 'imager_hk', source=data_rates, line_color=Colorblind8[2], legend_label='Imager H/K')
data_rates_plotG.line('dateG', 'imager_event', source=data_rates, line_color=Colorblind8[3], legend_label='Imager Events')
data_rates_plotG.line('dateG', 'spec', source=data_rates, line_color=Colorblind8[5], legend_label='Spec')
data_rates_plotG.line('dateG', 'mag', source=data_rates, line_color=Colorblind8[4], legend_label='Magnetometer')


#Creates the interactive legend
data_rates_plot.legend.location = "top_left"
data_rates_plot.legend.click_policy = "hide"

data_rates_plotG.legend.location = "top_left"
data_rates_plotG.legend.click_policy = "hide"

#--------------------------------------------------------------------------------------------------------------------------

#Sets ups event rates plot
event_rates_plot = figure(plot_width=900, plot_height=300, x_axis_type='datetime', tools=tools,
                         y_axis_label='events/s', title='Imager event rates')
event_rates_plotG = figure(plot_width=900, plot_height=300, x_axis_type='linear', tools=tools,
                         y_axis_label='events/s', title='Imager event rates (Gondola Time)',
                         x_axis_label='Elapsed Time (s)')


#Adds tools to the event rates plot
event_rates_plot.add_tools(create_hover_tool([f'events_{i}' for i in range(8)]))
event_rates_plotG.add_tools(create_hover_tool([f'events_{i}' for i in range(8)]))


#Plots the event rates for all the instruments
for i in range(8):
    event_rates_plot.line('date', f'events_{i}', source=statistics, line_color=Colorblind8[i], legend_label=f'Imager {i}')

for i in range(8):
    event_rates_plotG.line('dateG', f'events_{i}', source=statistics, line_color=Colorblind8[i], legend_label=f'Imager {i}')

#Creates the interactive legend
event_rates_plot.legend.location = "top_left"
event_rates_plot.legend.click_policy = "hide"

event_rates_plotG.legend.location = "top_left"
event_rates_plotG.legend.click_policy = "hide"

#--------------------------------------------------------------------------------------------------------------------------


#Sets up the GPS/PPS plot
gps_to_pps_plot = figure(plot_width=900, plot_height=200, x_axis_type='datetime', tools=tools,
                         y_axis_label='seconds', title='Gondola time of PPS signal minus preceding GPS position packet')
gps_to_pps_plotG = figure(plot_width=900, plot_height=200, x_axis_type='linear', tools=tools,
                         y_axis_label='milliseconds', title='Gondola time of PPS signal minus preceding GPS position packet (Gondola Time)',
                         x_axis_label='Elapsed Time (s)')


#Adds tools to the plot
gps_to_pps_plot.add_tools(create_hover_tool(['gps_to_pps']))
gps_to_pps_plotG.add_tools(create_hover_tool(['gps_to_pps']))

#Plots the GPS to PPS offset
gps_to_pps_plot.line('date', 'gps_to_pps', source=timing, line_color=Colorblind8[0])
gps_to_pps_plotG.line('dateG', 'gps_to_pps', source=timing, line_color=Colorblind8[0])

#--------------------------------------------------------------------------------------------------------------------------

#Sets up the PPS to SBC plot
pps_to_sbc_plot = figure(plot_width=900, plot_height=200, x_axis_type='datetime', tools=tools,
                         y_axis_label='seconds', title='System clock minus GPS clock')
pps_to_sbc_plotG = figure(plot_width=900, plot_height=200, x_axis_type='linear', tools=tools,
                         y_axis_label='milliseconds', title='System clock minus GPS clock (Gondola Time)',
                         x_axis_label='Elapsed Time (s)')

#Adds tools to the plot
pps_to_sbc_plot.add_tools(create_hover_tool(['pps_to_sbc']))
pps_to_sbc_plotG.add_tools(create_hover_tool(['pps_to_sbc']))

#Plots the PPS to SBC data
pps_to_sbc_plot.line('date', 'pps_to_sbc', source=timing, line_color=Colorblind8[1])
pps_to_sbc_plotG.line('dateG', 'pps_to_sbc', source=timing, line_color=Colorblind8[1])

#--------------------------------------------------------------------------------------------------------------------------

#Sets up the magnetometer data plot
mag_plot = figure(plot_width=900, plot_height=200, x_axis_type='datetime', tools=tools,
                    y_axis_label='B Field (uT)', title='Magnetometer Data')
mag_plotG = figure(plot_width=900, plot_height=200, x_axis_type='datetime', tools=tools,
                    y_axis_label='B Field (uT)', title='Magnetometer Data (Gondola Time)',
                    x_axis_label='Elapsed Time (s)')

#Add tools to the plot
mag_plot.add_tools(create_hover_tool(['bx', 'by', 'bz', 'total']))
mag_plotG.add_tools(create_hover_tool(['bx', 'by', 'bz', 'total']))

#Plot the data to the figures
mag_plot.line('date', 'bx', source=mag_data, line_color=Colorblind8[1], legend_label='Bx')
mag_plot.line('date', 'by', source=mag_data, line_color=Colorblind8[2], legend_label='By')
mag_plot.line('date', 'bz', source=mag_data, line_color=Colorblind8[3], legend_label='Bz')
mag_plot.line('date', 'total', source=mag_data, line_color=Colorblind8[4], legend_label='Btot')

mag_plotG.line('dateG', 'bx', source=mag_data, line_color=Colorblind8[1], legend_label='Bx')
mag_plotG.line('dateG', 'by', source=mag_data, line_color=Colorblind8[2], legend_label='By')
mag_plotG.line('dateG', 'bz', source=mag_data, line_color=Colorblind8[3], legend_label='Bz')
mag_plotG.line('dateG', 'total', source=mag_data, line_color=Colorblind8[4], legend_label='Btot')

mag_plot.legend.location = 'top_left'
mag_plotG.legend.location = 'top_left'

#--------------------------------------------------------------------------------------------------------------------------
#Wraps up GSE interface creation
doc = curdoc()
doc.add_root(column(row(command_block, data_rates_plot, data_rates_plotG, gps_block), 
                toggle, 
                event_rates_plot, 
                gps_to_pps_plot, 
                pps_to_sbc_plot,
                mag_plot, 
                event_rates_plotG, 
                gps_to_pps_plotG, 
                pps_to_sbc_plotG, 
                mag_plotG,
                house_block))

doc.title = "Middleman GSE"

#Start with the Gondola Time plots invisible
data_rates_plotG.visible = True
event_rates_plotG.visible = True
gps_to_pps_plotG.visible = True
pps_to_sbc_plotG.visible = True
mag_plotG.visible = True
  	  


#Define what the toggle button actually does
def toggleCallback(attr):
    # Either add or remove the second graph
    if  toggle.active == False:
        data_rates_plotG.visible = False
        event_rates_plotG.visible = False
        gps_to_pps_plotG.visible = False
        pps_to_sbc_plotG.visible = False
        mag_plotG.visible = False
  	   
        data_rates_plot.visible = True
        event_rates_plot.visible = True
        gps_to_pps_plot.visible = True
        pps_to_sbc_plot.visible = True
        mag_plot.visible = True
  	   
  
    if toggle.active == True:
        data_rates_plotG.visible = True
        event_rates_plotG.visible = True
        gps_to_pps_plotG.visible = True
        pps_to_sbc_plotG.visible = True
        mag_plotG.visible= True
  	   
        data_rates_plot.visible = False
        event_rates_plot.visible = False
        gps_to_pps_plot.visible = False
        pps_to_sbc_plot.visible = False
        mag_plot.visible = False


# Set the callback for the toggle button
toggle.on_click(toggleCallback)


#Print the statistics info
print(type(statistics))
print(statistics)

#Print the telemetry and magnetometer information

"""
==========================================================================================================================
Execution
==========================================================================================================================
"""

doc.add_next_tick_callback(update_command_info_div)
doc.add_next_tick_callback(update_gps_info_div)
doc.add_next_tick_callback(update_mag_info_div)
doc.add_next_tick_callback(update_house_info_div)

async def setup_udp_listening():
    loop = asyncio.get_running_loop()
    transport, protocol = await loop.create_datagram_endpoint(lambda: TelemetryProtocol(),
                                                              local_addr=("0.0.0.0", TM_PORT))


loop = asyncio.get_running_loop()
loop.create_task(setup_udp_listening())
