#!/Library/Frameworks/Python.framework/Versions/3.8/bin/python3.8
#      /usr/bin/python3 on linux
#
#############################################################################
# For BOOMS project: a GSE for displaying spectrometer data
#############################################################################
#
# USAGE: [python] specgse.py serialPort
#        [python] specgse.py filename rate
#
#
# INPUTS: serialPort is the serial port name
#                    MAC/linux w/USB adapter: /dev/cu.usbserialxxxx
#                    linux w/serport: /dev/ttyS0
#                    Windows: COMx
#         filename is a stored file of data packets
#         rate     is how many frames to process per second (positive real number)
#
# OUTPUTS: writes serial data into a time-stamped file
#          maintains a GUI display of transmitted data
#          a few diagnostics to stdout
#
# NOTES:
#          1. keep class variables localized, unless needed externally
#             single-instance classes use classVariable instead of self
#          2. tested versions:  python v3.8.2, tkinter v8.6.8, matplotlib v3.3.0,
#             pyserial v3.4
#               to find python version:      python --version
#               to find tkinter patch level: import tkinter as tk; r=tk.Tk();
#                           print(r.tk.call("info",patchlevel")); r.destroy()
#               to find matplotlib version:  import matplotlib; matplotlib.__version__
#               to find pyserial version:    import serial; serial.__version__
#          3. incoming serial data are stored to disk as received
#             regardless of data source, packets are split off from
#               input stream and queued, periodically de-queud,
#               digested, and displayed
#
# REMAINING TASKS:
#          1. add housekeeping limit checks
#          2. add a sum spectrum
#          3. more controls on the spectrum plot
#
# HISTORY: 20Jan2022/v1.0 adapted from bgse.py
#          17Feb2022/v1.1 bigger packets and faster baud

from datetime import (datetime, timedelta)
from glob import glob
from threading import Thread
from serial import Serial
from os import (mkdir, path)
import sys
import time
import tkinter as tk
import queue
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import (FigureCanvasTkAgg,
       NavigationToolbar2Tk)
#from matplotlib.backend_bases import key_press_handler
#from struct import Struct
import numpy as np

pktLen=212

class SerialThread(Thread):
    """ pull in serial data and save it

    Variables used outside this thread:
       datastreamActive---boolean to externally disable activity (__main__)
       packets--------a queue of packets
       bytesRead------number of bytes read so far
       junkBytes------number of bytes that could not be used

    DESCRIPTION:
    
    """
    def __init__(self,ser):
        Thread.__init__(self)
        self.serialPort = ser
        self.rxbuf = b""
        self.packets=queue.Queue()
        self.bytesRead = 0
        self.junkBytes = 0
        if not path.isdir("packets"):
            mkdir("packets")
        try:
            self.outFile = open(path.join("packets",
                  f"BSPC{datetime.utcnow():%Y%b%dT%H%M%S}.dat"), "wb")
        except:
            print("failed to open output file")
            sys.exit(1)
            
    def run(self):
        while datastreamActive:
           justread = self.serialPort.read(25000)
           newCount = len(justread)
           if newCount > 0:
               self.bytesRead += newCount
               self.outFile.write(justread)
               self.rxbuf += justread
               self.pktExtract(len(self.rxbuf))
        self.outFile.close()

    def pktExtract(self,buffLen):
        if buffLen < pktLen:
            return
        start = 0
        while start <= (buffLen-pktLen):
            temp = self.rxbuf[start]
            if self.rxbuf[start] != 0xEB:
                self.junkBytes += 1
                start += 1
                continue
            if self.rxbuf[start+1] != 0x90:
                self.junkBytes += 1
                start += 1
                continue
            if self.verifyChksum(start) == False:
                self.junkBytes += 1
                start += 1
                continue
            self.packets.put(self.rxbuf[start:start+pktLen])
            start += pktLen
        self.rxbuf = self.rxbuf[start:]

    def verifyChksum(self,index):
        total = 0
        maxIndex = index + pktLen - 2;
        while index < maxIndex:
            word = int(self.rxbuf[index])<<8
            index += 1
            word |= int(self.rxbuf[index])
            index += 1
            total += word
        total &= 0xFFFF;
        word = int(self.rxbuf[index]) << 8
        index += 1
        word |= int(self.rxbuf[index])
        if total == word:
            return True
        else:
            return False

########################### END OF SERIAL CLASS ##############################

class FileRead(Thread):
    """ pull data in from a file

    Variables used outside this thread:
       datastreamActive-----boolean to externally disable activity (__main__)
       packets--------a queue of packets
       bytesRead------number of bytes read so far
       junkBytes------number of bytes that could not be used

    DESCRIPTION:
    
    """
    def __init__(self, fp, speed, live=False):
        Thread.__init__(self)
        self.fileID = fp
        self.rxbuf = b""
        self.packets=queue.Queue()
        self.bytesRead = 0
        self.junkBytes = 0
        self.sleepTime = 1/speed
        self.live = live
            
    def run(self):
        fileDone = False
        while datastreamActive:
            if not fileDone:
                justread = self.fileID.read(2120)
                newCount = len(justread)
                if newCount == 2120:
                    self.bytesRead += 2120
                    self.rxbuf += justread
                    newFrame = self.pktExtract(len(self.rxbuf))
                    if newFrame:
                         newFrame = False
                         time.sleep(self.sleepTime)
                else:
                    # TODO, option
                    if not self.live:
                        fileDone = True
                        self.fileID.close()
                    self.bytesRead += newCount
                    self.rxbuf += justread
                    newFrame = self.pktExtract(len(self.rxbuf))
                    if not self.live:
                        self.junkBytes += len(self.rxbuf)
            else:
                time.sleep(1)

        if not fileDone:
            self.fileID.close()

    def pktExtract(self,buffLen):
        foundNewFrame = False
        if buffLen < pktLen:
            return False
        start = 0
        while start <= (buffLen-pktLen):
            temp = self.rxbuf[start]
            if self.rxbuf[start] != 0xEB:
                self.junkBytes += 1
                start += 1
                continue
            if self.rxbuf[start+1] != 0x90:
                self.junkBytes += 1
                start += 1
                continue
            if self.verifyChksum(start) == False:
                self.junkBytes += 1
                start += 1
                continue
            self.packets.put(self.rxbuf[start:start+pktLen])
            start += pktLen
            foundNewFrame = True
#            tempstring="".join(f"{c:02X}" for c in self.rxbuf[start:start+pktLen])  #HACK
#            print(tempstring)                             #HACK
        self.rxbuf = self.rxbuf[start:]
        return foundNewFrame


    def verifyChksum(self,index):
        total = 0
        maxIndex = index + pktLen - 2;
        while index < maxIndex:
            word = int(self.rxbuf[index]) << 8
            index += 1
            word += int(self.rxbuf[index])
            index += 1
            total += word
        total &= 0xFFFF;
        word = int(self.rxbuf[index]) << 8
        index += 1
        word |= int(self.rxbuf[index])
        if total == word:
            return True
        else:
            print('Checksum Failed')
            return False

########################### END OF FileRead CLASS ##############################

# widget with a vertical list of (label, value) pairs
def stuffLabelFrame(container, labels, vars, frColor="lightgray", lw=12, vw=8):
    i=0
    handles=[]
    for (lab,var) in zip(labels,vars):
        tk.Label(container, anchor="e", text=lab, bg=frColor, relief="flat",
            width=lw, padx=1).grid(row=i,sticky=tk.E)
        temp = tk.Label(container, textvar=var, padx=3, anchor="e", bg=frColor,
            font="TkFixedFont", width=vw, relief="sunken")
        handles.append(temp)
        temp.grid(row=i, column=1, sticky=tk.E)
        i += 1
    return handles 

class twoCounters:
    def __init__(self, panel, length, *args, **kwargs):
        self.tmp1 = length*[0]
        self.tmp2 = length*[0]
        self.cbuf1 = length*[0]
        self.cbuf2 = length*[0]
        self.addNext = 0
        self.len = length
        x = [i for i in range(1-length,1)]
        self.fig=panel.add_subplot(*args, **kwargs)
        self.fig.set_xlim([-length,1])
        self.fig.plot(x,self.cbuf1,animated=True)
        self.fig.plot(x,self.cbuf2,animated=True)

    def firstDraw(self):
        self.fig.draw_artist(self.fig.lines[0])
        self.fig.draw_artist(self.fig.lines[1])

    def addPMTs(self, twocntrs):
        self.cbuf1[self.addNext] = twocntrs[0]
        self.cbuf2[self.addNext] = twocntrs[1]
        self.addNext = (self.addNext+1)%self.len

    def update(self):
        line1 = self.fig.lines[0]
        line2 = self.fig.lines[1]
        i =  0
        j = self.addNext
        while (i < self.len):
            self.tmp1[i] = self.cbuf1[j]
            self.tmp2[i] = self.cbuf2[j]
            i += 1
            j =(j+1)%self.len
        line1.set_ydata(self.tmp1)
        line2.set_ydata(self.tmp2)
        self.fig.draw_artist(line1)
        self.fig.draw_artist(line2)

######################### END OF twoCounters class ############################

class TimeGraphs:
    def __init__(self, base):
        self.panel = Figure(figsize=(7,5),dpi=100)
        self.plotRegion = FigureCanvasTkAgg(self.panel,base)
        self.plotRegion.get_tk_widget().grid(row=0,column=0,padx=5,pady=5)
        self.ll=twoCounters(self.panel,60,221,yscale="log",
              ylim=[50,2000],title="low disc")
        self.pd=twoCounters(self.panel,60,222,yscale="log",
              ylim=[50,2000],title="peak det")
        self.hl=twoCounters(self.panel,60,223,yscale="log",
              ylim=[1,50],title="high disc")
        self.iq=twoCounters(self.panel,60,224,yscale="log",
              ylim=[50,2000],title="interrupts")
        self.panel.set_tight_layout(True)
        self.plotWait = True

    def update(self):
        if (self.plotWait):
            if (BMSDisplay.hdr.numSecs.get()>1):
                self.bkgd = self.panel.canvas.copy_from_bbox(self.panel.bbox)
                self.ll.firstDraw()
                self.pd.firstDraw()
                self.iq.firstDraw()
                self.hl.firstDraw()
                self.plotRegion.blit(self.panel.bbox)
                self.plotWait = False
            return
        else: 
            self.panel.canvas.restore_region(self.bkgd)
            self.iq.update()
            self.ll.update()
            self.pd.update()
            self.hl.update()
            self.plotRegion.blit(self.panel.bbox)
        
########################## END OF TimeGraphs class #############################

class PDWindow(tk.LabelFrame):
    """ create and update the PD counter windows

        __init__(container,title)
        update((energy, lowlevel, peak detect, highlevel, saturationlevel, pileup))
                   changes display
    """
    def __init__(self, base, title):
        tk.LabelFrame.__init__(self, base, text=title, pady=5, padx=5)
        self.iq = tk.IntVar(base,0)
        self.ll = tk.IntVar(base,0)
        self.pd = tk.IntVar(base,0)
        self.hl = tk.IntVar(base,0)
        stuffLabelFrame(self, ["IRQs", "loDisc", "peakDet", "hiDisc"],
                [self.iq, self.ll, self.pd, self.hl], vw=5, lw=7)
            
    def update(self, boardCounters):
        for (var,val) in zip([self.iq, self.ll, self.pd, self.hl], boardCounters):
            var.set(val)
        return

########################### END OF PDWindow CLASS ##############################

class HKPWindow(tk.LabelFrame):
    """ create and update an analog housekeeping window

        __init__(container)
        update((hk1, hk2, hk3, hk4, hk5, hk6))
                   changes display
    """
    def __init__(self, base):
        tk.LabelFrame.__init__(self, base, text="analog hkpg", 
                               bg='lightgray', pady=5, padx=5)
        HKPWindow.hk1 = tk.StringVar(base,"no data")
        HKPWindow.hk2 = tk.StringVar(base,"no data")
        HKPWindow.hk3 = tk.StringVar(base,"no data")
        HKPWindow.hk4 = tk.StringVar(base,"no data")
        HKPWindow.hk5 = tk.StringVar(base,"no data")
        HKPWindow.hk6 = tk.StringVar(base,"no data")
        HKPWindow.hk7 = tk.StringVar(base,"no data")
        stuffLabelFrame(self, ["+5 (V)", "+I (mA)", "-5 (V)",  "-I (mA)",
                               "Tx1 (C)", "Tx2 (C)", "Tbox (C)"],
                        [HKPWindow.hk1, HKPWindow.hk2, HKPWindow.hk3,
                         HKPWindow.hk4, HKPWindow.hk5, HKPWindow.hk6,
                         HKPWindow.hk7], vw=5, lw=7)
            
    def update(self, vals):
        vp = vals[0]/758.
        ip = vals[1]/20.
        vm = -vals[2]/788.
        im = -vals[3]/102.
        t1 = vals[4]/10. - 273.2
        t2 = vals[5]/10. - 273.2
        tb = vals[6]/10. - 273.2
        HKPWindow.hk1.set(f"{vp:4.2f}")
        HKPWindow.hk2.set(f"{ip:5.1f}")
        HKPWindow.hk3.set(f"{vm:5.2f}")
        HKPWindow.hk4.set(f"{im:5.1f}")
        HKPWindow.hk5.set(f"{t1:5.1f}")
        HKPWindow.hk6.set(f"{t2:5.1f}")
        HKPWindow.hk7.set(f"{tb:5.1f}")
        return

########################### END OF HKPWindow CLASS ##############################

class HDRWindow():
    """ create and maintain the header at top of window

        __init__() needs name of window's container
        update(vals)
             vals: a tuple of values to display

    """
    def __init__(self, base, sheets):
        self.packetCount = 0
        HDRWindow.sheets = sheets
#        HDRWindow.command   = tk.StringVar(base,"")
        self.nowString      = tk.StringVar(base,"2020xxxxxTxx:xx:xx")
        HDRWindow.pktCount  = tk.IntVar(base,0)
        HDRWindow.ID        = tk.IntVar(base,-1)
        HDRWindow.swver     = tk.IntVar(base,-1)
        self.FC             = tk.IntVar(base,0)
        HDRWindow.pps       = tk.IntVar(base,0)
        HDRWindow.numSecs   = tk.IntVar(base,0)
        HDRWindow.rcvCount  = tk.IntVar(base,0)
        HDRWindow.junk      = tk.IntVar(base,0)
        self.message        = tk.StringVar(base,"no messages yet")
        HDRWindow.page      = tk.StringVar(base,"page1")
        hd = tk.Frame(base, bg="lightgray")

        tk.Label(hd, textvar=self.nowString,anchor=tk.E).grid(row=0,
              column=0, columnspan=2, sticky=tk.E)
        tk.Label(hd, text="received frames").grid(row=0, column=2, sticky=tk.E)
        tk.Label(hd, textvar=HDRWindow.pktCount,width=7,anchor=tk.E,
                 relief="sunken").grid( row=0, column=3, sticky=tk.E)
        tk.Label(hd, text="spectrometer ID").grid(row=1, column=0, sticky=tk.E)
        tk.Label(hd, textvar=HDRWindow.ID).grid(row=1, column=1, sticky=tk.E)

        tk.Label(hd, text="frame counter").grid(row=1, column=2, sticky=tk.E)
        tk.Label(hd, textvar=self.FC,width=7,anchor=tk.E,
                 relief="sunken").grid(row=1, column=3, sticky=tk.E)
        tk.Label(hd, text="runtime (s)").grid(row=0, column=4, sticky=tk.E)
        tk.Label(hd, textvar=HDRWindow.numSecs,width=8,anchor=tk.E,
                 relief="sunken").grid( row=0, column=5, sticky=tk.E)
        tk.Label(hd, text="pps delay").grid(row=1, column=4, sticky=tk.E)
        tk.Label(hd, textvar=HDRWindow.pps,width=8,anchor=tk.E,
                 relief="sunken").grid( row=1, column=5, sticky=tk.E)
        tk.Label(hd, text="Kbytes in").grid(row=0, column=6, sticky=tk.E)
        tk.Label(hd, textvar=HDRWindow.rcvCount,width=8,anchor=tk.E,
                 relief="sunken").grid( row=0, column=7, sticky=tk.E)
        tk.Label(hd, text="junk bytes").grid(row=1, column=6, sticky=tk.E)
        tk.Label(hd, textvar=HDRWindow.junk,width=8,anchor=tk.E,
                 relief="sunken").grid( row=1, column=7, sticky=tk.E)
        tk.Label(hd,textvar=self.message, width=30, anchor="w", 
                 bg="white").grid(row=0, column=8, sticky=tk.EW, padx=10)
        def kill():
            base.quit()
            base.destroy()
        tk.Button(hd, text="Quit", bg="red", command=kill).grid(
              row=1, column=8)
        radioFrame = tk.Frame(hd, bg="lightgray")
        tk.Radiobutton(radioFrame, text="page1", variable=HDRWindow.page,
                       value="page1", bg="lightgray",
                       command=self.showMain).grid(row=0, column=0,
                                                   sticky=tk.W)
        tk.Radiobutton(radioFrame, text="page2", variable=HDRWindow.page,
                       value="page2", bg="lightgray",
                       command=self.showTimeSeries).grid(row=0, column=1,
                                                   sticky=tk.W)
        radioFrame.grid(row=0, column=9, rowspan=2, sticky=tk.E, padx=10)

        HDRWindow.window = hd

    def showMain(self):
        HDRWindow.sheets["page1"].tkraise()

    def showTimeSeries(self):
        HDRWindow.sheets["page2"].tkraise()

#   update gets a tuple of fc, id, swver
    def update(self, var):
        HDRWindow.rcvCount.set(thread1.bytesRead//1024)
        self.FC.set(var[0])
        HDRWindow.junk.set(thread1.junkBytes)
        HDRWindow.pktCount.set(gui.pktCount)
        HDRWindow.ID.set(var[1])
        HDRWindow.swver.set(var[2])

########################### END OF HDRWindow CLASS ##############################

class SpecGrapher:
    """ display event spectra
            
        __init__(parent) interfaces between matplotlib and Tk sets up the
                         panel---draws axes, labels, title
        INPUT: base is the tk parent widget
               binCount is number of bins in the spectrum
               plotLabel is a label for the plot
               duration is seconds per measurement
               yrange is (ymin, ymax) tuple
               widths is a list of relative bin widths for normalizing
                  the counts
               In addition there are two sets of measurements to plot
                  in self.cnt1 and self.cnt2, and a count
                  for the number of samples for each bin, self.sampleCount
        clear()  clears the spectra so accumulations can start fresh
        update((seq, upper, lower, condTime)) scales raw values and
                             adds points to the figure for each probe;
    """
    def __init__(self, base, binCount, plotLabel, duration, yrange,
    widths):
        self.plotWait = True
        self.accCount = tk.IntVar(base,0)
        self.binCount = binCount
        self.sampleCount=binCount*[0]
        self.cnt1=binCount*[0]
        self.cnt2=binCount*[0]
        self.widths = widths
        x = [i for i in range(binCount)]
        margin = max(1, binCount // 25)

        buttons=tk.Frame(base)
        buttons.grid(row=0,column=0,padx=5,pady=0,sticky=tk.W)
        tk.Button(buttons,text="clear",command=self.clear).grid(row=0,
                  column=0, padx=5, pady=5, sticky=tk.E)
        tk.Label(buttons, anchor="e", text="#spectra",
                  bg="lightgray", relief="flat", width=6,
                  padx=1).grid(row=0, column=1, sticky=tk.E)
        tk.Label(buttons, textvar=self.accCount, padx=3, anchor="e", relief="sunken",
                  width=5, bg="lightgray", font="TkFixedFont").grid(row=0, column=2,
                  sticky=tk.E)

        self.panel = Figure(figsize=(6,4),dpi=100)
        self.fig = self.panel.add_subplot()
        self.fig.set_ylabel("counts/(bin-s)")
        self.fig.set_xlabel("bin")
        self.fig.set_xlim([-margin,binCount+margin])
        self.fig.set_ylim(list(yrange))
        self.fig.set_yscale("log")
        self.fig.set_title(plotLabel)
        self.plotRegion = FigureCanvasTkAgg(self.panel, base)
        self.plotRegion.get_tk_widget().grid(row=1, column=0)
        self.fig.plot(x,self.cnt1,'.',label='pd1',
                             markersize=2,animated=True)
        self.fig.plot(x,self.cnt2,'.',label='pd2',
                             markersize=2,animated=True)
        self.fig.legend(markerscale=5)
        self.duration = duration

    def clear(self):
        self.accCount.set(0)
        self.sampleCount = self.binCount*[0]
        self.cnt1 = self.binCount*[0]
        self.cnt2 = self.binCount*[0]

    def update(self):
        if (self.plotWait):
            if (BMSDisplay.hdr.numSecs.get()>2):
                self.plotWait = False
                self.bkgd=self.panel.canvas.copy_from_bbox(self.panel.bbox)
                self.fig.draw_artist(self.fig.lines[0])
                self.fig.draw_artist(self.fig.lines[1])
                self.plotRegion.blit(self.panel.bbox)
            return
        line1=self.fig.lines[0]
        line2=self.fig.lines[1]

        temp=[c/b/a/self.duration if a>0 else 0 for (a,b,c) in
                    zip(self.sampleCount, self.widths, self.cnt1)]
        line1.set_ydata(temp)
        temp=[c/b/a/self.duration if a>0 else 0 for (a,b,c) in
                    zip(self.sampleCount, self.widths, self.cnt2)]
        line2.set_ydata(temp)
        self.accCount.set(self.accCount.get() + 1)

        self.panel.canvas.restore_region(self.bkgd)
        self.fig.draw_artist(line1)
        self.fig.draw_artist(line2)
        self.plotRegion.blit(self.panel.bbox)

########################### END OF SpecGrapher CLASS ##############################

class BMSDisplay(tk.Toplevel):
    """ show data that is processed through the BOOMS GSE

    INPUT: none
    OUTPUT: none (manages/updates windows); this is a derived
            class from the tkinter.Tk class
    DESCRIPTION: set up variables which, when changed, appear
                   as updated quantities in the display windows
                 build sub-windows for different data products
                 whatsNew() calls itself every 250ms to
                   look for changes such as new messages,
                   ground commands, or a new packet to process;
                   it also updates a real-time clock display
                 implement different pages of gui by stacking
                   multiple plots in the same location, then
                   raise the one we want to see to the top
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        winBk="palegreen"
#        self.minsize(1140,660)
        self.title("BOOMS: spectrometer GSE v1.1/17Feb2022")
        self.config(bg=winBk)
        self.option_add("*Label*background","lightgray")
        self.option_add("*Labelframe*background","lightgray")
        self.option_add("*Frame.background",winBk)
        BMSDisplay.pd1 = 4*[0]
        BMSDisplay.pd2 = 4*[0]
        BMSDisplay.swver = -1
        BMSDisplay.id = -1
        BMSDisplay.pktCount = 0
        BMSDisplay.fc = -1           # frame counter
        BMSDisplay.lastSecond = 0
        BMSDisplay.hk = 7*[0.]
        BMSDisplay.hresReady = False
        BMSDisplay.hkpgReady = False
        BMSDisplay.fastReady = False
        BMSDisplay.rateReady = False

        widgetDict={}
        BMSDisplay.bodySpace = tk.Frame(self)
        BMSDisplay.pdSpace = tk.Frame(self)
        widgetDict["page1"] = BMSDisplay.bodySpace
        widgetDict["page2"] = BMSDisplay.pdSpace
        BMSDisplay.bodySpace.grid(row=1, column=0, sticky=tk.NSEW)
        BMSDisplay.pdSpace.grid(row=1, column=0, sticky=tk.NSEW)
        BMSDisplay.bodySpace.tkraise()

        BMSDisplay.hdr = HDRWindow(self, widgetDict)
        BMSDisplay.hdr.window.grid(row=0, column=0, sticky=tk.NSEW)
        leftBox = tk.Frame(BMSDisplay.bodySpace, bg=winBk)
        BMSDisplay.pdTabl = tk.LabelFrame(leftBox, text="PD boards", 
                            bg="lightgray", padx=5, pady=5)
        BMSDisplay.pdTabl.grid(row=0, column=0, sticky=tk.NE)
        BMSDisplay.pdWin1=PDWindow(BMSDisplay.pdTabl,"PD 1")
        BMSDisplay.pdWin1.config(bg='#1F77B4')
        BMSDisplay.pdWin1.grid(row=0,column=0,sticky=tk.E,padx=5,pady=5)
        BMSDisplay.pdWin2=PDWindow(BMSDisplay.pdTabl,"PD 2")
        BMSDisplay.pdWin2.config(bg='#FF7F0E')
        BMSDisplay.pdWin2.grid(row=1,column=0,sticky=tk.E,padx=5,pady=5)
        comhkp = tk.Frame(leftBox, bg=winBk)
        comhkp.grid(row=0, column=1, padx=5, pady=5)
        BMSDisplay.hkpg = HKPWindow(comhkp)
        BMSDisplay.hkpg.grid(row=0, column=0, padx=5, pady=5)

        BMSDisplay.hresFrame=tk.Frame(leftBox, bg=winBk, padx=5, pady=5)
        BMSDisplay.hresFrame.grid(row=0,column=2)
        widths = 64*[1]+32*[2]+16*[4]+16*[8]+12*[16]
        BMSDisplay.hres = SpecGrapher(BMSDisplay.hresFrame, 140,
            "high resolution spectra", 19.2, (0.01,100),widths)
        leftBox.grid(row=0, column=0, sticky=tk.NW, padx=4, pady=4)
        BMSDisplay.tsPlots=TimeGraphs(BMSDisplay.pdSpace)

        BMSDisplay.fastFrame=tk.Frame(BMSDisplay.pdSpace, bg=winBk, padx=5, pady=5)
        BMSDisplay.fastFrame.grid(row=0,rowspan=2,column=1)
        widths = [27, 34, 43, 55, 69, 86, 110, 139, 175, 221, 279, 353,
        446, 563, 711, 900]
        BMSDisplay.fast = SpecGrapher(BMSDisplay.fastFrame, 16,
            "100ms spectra", 0.1, (0.005, 50),widths)

    def whatsNew(self):
        """ loop monitors new data from serial thread

            DESCRIPTION: calls itself every 250ms
                         update live clock
                         if diagnostic is queued, print it
                         if packet arrived, update display
        """
        self.after(250,self.whatsNew)
        timenow = datetime.utcnow()
        BMSDisplay.hdr.nowString.set(format(timenow, "%Y%b%dT%H:%M:%S"))
        runtime = timenow - starting
        seconds = int(runtime.total_seconds()+0.5)
        # if seconds == 3: # Temporary hack
        #     BMSDisplay.hresReady = True
        if seconds != BMSDisplay.lastSecond:
            BMSDisplay.lastSecond = seconds
            BMSDisplay.hdr.numSecs.set(seconds)
        if not thread1.packets.empty():
            BMSDisplay.parsePackets(thread1.packets)
        if (BMSDisplay.hkpgReady):
            BMSDisplay.hkpgReady = False
            BMSDisplay.hkpg.update(BMSDisplay.hk);
        if (BMSDisplay.rateReady):
            BMSDisplay.rateReady = False
            BMSDisplay.pdWin1.update(BMSDisplay.pd1)
            BMSDisplay.pdWin2.update(BMSDisplay.pd2)
            temp=list(zip(*[list(BMSDisplay.pd1), list(BMSDisplay.pd2)]))
            BMSDisplay.tsPlots.iq.addPMTs(temp[0])
            BMSDisplay.tsPlots.ll.addPMTs(temp[1])
            BMSDisplay.tsPlots.pd.addPMTs(temp[2])
            BMSDisplay.tsPlots.hl.addPMTs(temp[3])
            BMSDisplay.tsPlots.update()
        if (BMSDisplay.hresReady):
            BMSDisplay.hresReady = False
            BMSDisplay.hres.update()
        if BMSDisplay.fastReady:
            BMSDisplay.fast.update()
            BMSDisplay.fastReady = False
        BMSDisplay.hdr.update((BMSDisplay.fc, BMSDisplay.id, BMSDisplay.swver))
#        try:
#            msg=thread1.status.get(False)
#            BMSDisplay.hdr.message.set(msg)
#        except queue.Empty:
#            pass

    def Unpack(packed):
        chan00 =  (int(packed[ 0])         << 2) | (int(packed[ 1]) >> 6)
        chan01 = ((int(packed[ 1]) & 0x3F) << 4) | (int(packed[ 2]) >> 4)
        chan02 = ((int(packed[ 2]) & 0x0F) << 6) | (int(packed[ 3]) >> 2)
        chan03 = ((int(packed[ 3]) & 0x03) << 8) |  int(packed[ 4])
        chan04 =  (int(packed[ 5])         << 2) | (int(packed[ 6]) >> 6)
        chan05 = ((int(packed[ 6]) & 0x3F) << 4) | (int(packed[ 7]) >> 4)
        chan06 = ((int(packed[ 7]) & 0x0F) << 6) | (int(packed[ 8]) >> 2)
        chan07 = ((int(packed[ 8]) & 0x03) << 8) |  int(packed[ 9])
        chan08 =  (int(packed[10])         << 2) | (int(packed[11]) >> 6)
        chan09 = ((int(packed[11]) & 0x3F) << 4) | (int(packed[12]) >> 4)
        chan10 = ((int(packed[12]) & 0x0F) << 6) | (int(packed[13]) >> 2)
        chan11 = ((int(packed[13]) & 0x03) << 8) |  int(packed[14])
        chan12 =  (int(packed[15])         << 2) | (int(packed[16]) >> 6)
        chan13 = ((int(packed[16]) & 0x3F) << 4) | (int(packed[17]) >> 4)
        chan14 = ((int(packed[17]) & 0x0F) << 6) | (int(packed[18]) >> 2)
        chan15 = ((int(packed[18]) & 0x03) << 8) |  int(packed[19])
        return [chan00, chan01, chan02, chan03, chan04, chan05, chan06, chan07,
                     chan08, chan09, chan10, chan11, chan12, chan13, chan14, chan15]

    def parsePackets(q):
        """ pull packets from queue and collect their contents
            DESCRIPTION: 
        """
        while q.qsize() > 0:
            pkt = q.get_nowait()
            BMSDisplay.pktCount += 1
            BMSDisplay.swver = (int(pkt[2]) & 0xF0)>>4
            BMSDisplay.id = int(pkt[2]) & 0x0F
            fcTop =  int(pkt[3])<<16
            fcMid =  int(pkt[4])<<8
            fcLow =  int(pkt[5])
            BMSDisplay.fc = fcLow | fcMid | fcTop

            BMSDisplay.fast.sampleCount = [
                  BMSDisplay.fast.sampleCount[i]+1 for i in range(16)]

            temp = [BMSDisplay.Unpack(pkt[ 6:26]),  BMSDisplay.Unpack(pkt[46:66]),
                    BMSDisplay.Unpack(pkt[86:106]), BMSDisplay.Unpack(pkt[126:146]),
                    BMSDisplay.Unpack(pkt[166:186])]
            sums = list(map(sum,list(zip(*temp))))
            BMSDisplay.fast.cnt1 = [
                  sums[i] + BMSDisplay.fast.cnt1[i] for i in range(16)]

            temp = [BMSDisplay.Unpack(pkt[26:46]),  BMSDisplay.Unpack(pkt[66:86]),
                    BMSDisplay.Unpack(pkt[106:126]), BMSDisplay.Unpack(pkt[146:166]),
                    BMSDisplay.Unpack(pkt[186:206])]
            sums = list(map(sum,list(zip(*temp))))
            BMSDisplay.fast.cnt2 = [
                  sums[i] + BMSDisplay.fast.cnt2[i] for i in range(16)]

            hkpA = (int(pkt[pktLen-6]) << 8) | int(pkt[pktLen-5])
            hkpB = (int(pkt[pktLen-4]) << 8) | int(pkt[pktLen-3])
            index = fcLow & 0x1F
            if index < 3:
                if index == 0:
                    BMSDisplay.fastReady = True
                BMSDisplay.hk[2*index] = hkpA
                BMSDisplay.hk[2*index+1] = hkpB 
            elif index == 3:
                BMSDisplay.hk[6] = hkpA
                BMSDisplay.hdr.pps.set(hkpB)
                BMSDisplay.hkpgReady = True
            elif index < 8:
                BMSDisplay.pd1[index - 4] = hkpA
                BMSDisplay.pd2[index - 4] = hkpB
                if index == 7:
                    BMSDisplay.rateReady = True
            else:
                binIndex = 24*((BMSDisplay.fc % 192)//32) + index - 8
                if binIndex < 140:
                    BMSDisplay.hres.sampleCount[binIndex] += 1
                    BMSDisplay.hres.cnt1[binIndex] += hkpA
                    BMSDisplay.hres.cnt2[binIndex] += hkpB
                elif binIndex == 140:
                    BMSDisplay.hresReady = True
            continue

########################### END OF BMSDisplay CLASS ##############################

def run_gse(serial_port, frames_per_s=None, parent=None,
            save=False, live=False):
    if parent is None:
        parent = tk.Tk()
        parent.withdraw()

    global starting, datastreamActive, thread1, gui

    if frames_per_s is None:
        try:
            ser = Serial(serial_port, 38400, timeout=0.2)
        except:
            print("ERROR: Cannot open serial port", serial_port)
            sys.exit(-1)
        print("starting serial thread")
        thread1 = SerialThread(ser)
        datastreamActive = True
        thread1.start()
        starting = datetime.utcnow()
        print("starting display")
        gui = BMSDisplay(parent)
        gui.whatsNew()
        gui.mainloop()

        print("shutting down in 1s") # clean up after gui quits
        datastreamActive = False
        time.sleep(1)
        ser.close()
        if save:
            np.savetxt('pd1.txt', gui.hres.fig.lines[0].get_ydata())
            np.savetxt('pd2.txt', gui.hres.fig.lines[1].get_ydata())
    else:
        try:
            filePtr = open(sys.argv[1], "rb")
            if live:
                filePtr.seek(-1, 2)
        except:
            print("failed to open input file", serial_port)
            sys.exit(1)
        try:
            framesPerSecond = float(frames_per_s)
        except:
            print("invalid frames per second argument:"+frames_per_s)
            sys.exit(1)
        if (framesPerSecond <= 0):
            print("invalid frames per second argument:"+frames_per_s)
            sys.exit(1)

        print("starting file thread", serial_port, framesPerSecond)
        thread1 = FileRead(filePtr, framesPerSecond, live)
        datastreamActive = True
        thread1.start()
        print("starting display")
        starting = datetime.utcnow()
        gui = BMSDisplay()
        gui.hdr.message.set(serial_port)
        gui.whatsNew()
        gui.mainloop()

        print("shutting down in 1s")  # clean up after gui quits
        datastreamActive = False
        time.sleep(1)
        if save:
            np.savetxt('pd1.txt', gui.hres.fig.lines[0].get_ydata())
            np.savetxt('pd2.txt', gui.hres.fig.lines[1].get_ydata())
    print("All done")
