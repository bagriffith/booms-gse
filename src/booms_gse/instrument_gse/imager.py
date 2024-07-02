#!/Library/Frameworks/Python.framework/Versions/3.8/bin/python3.8 #mac Xquartz
#
# to run this code on a computer
#    1. select or modify one of the 3 paths to a python interpreter (below)
#    2. copy that line to first line of this file, remove and trailing comment
#    3. replace the blank following # with a ! and save
#    4. see usage notes to start the gse code
#
# /Library/Frameworks/Python.framework/Versions/3.8/bin/python3.8 #mac Xquartz
# /opt/local/bin/python3.10                                       #mac X11
# /usr/bin/python3                                                #linux
#
# don't know start details under a Win OS
#
#############################################################################
# For BOOMS project: a GSE for displaying imager data
#############################################################################
#
# USAGE: [python] ./bgse.py serialPort
#        [python] ./bgse.py filename rate
#
#
# INPUTS: serialPort is the serial port name
#                    MAC/linux w/USB adapter: /dev/cu.usbserialxxxx
#                    linux w/serport: /dev/ttyS0
#                    Windows: COMx
#         filename is a stored file of data packets
#         rate     is how many seconds of data to process per real time second
#                       (positive real number; limited by the computer)
#
# OUTPUTS: writes serial data into a time-stamped file
#          maintains a GUI display of transmitted data
#          some diagnostics to stdout
#
# NOTES:
#          1. keep class variables localized, unless needed externally
#          2. tested versions:  python v3.10.8, tkinter v8.6.12, matplotlib v3.5.3,
#             pyserial v3.5
#               to find python version:      python --version
#               to find tkinter patch level: import tkinter as tk; r=tk.Tk();
#                           print(r.tk.call("info","patchlevel")); r.destroy()
#               to find matplotlib version:  import matplotlib; matplotlib.__version__
#               to find pyserial version:    import serial; serial.__version__
#          3. incoming serial data are stored to disk as received;
#             regardless of data source, packets are split off from input stream,
#             then queued, then periodically de-queued, digested, and displayed
#   
# REMAINING TASKS:
#          1. add a sum spectrum
#          2. add position mapper
#          3. improve efficiency?
#
# HISTORY: 28Dec2020/v1.0 serial thread/data archiving
#          25Jan2021/v1.1 spectra/time plots & pd counter tables
#          05Feb2021/v1.2 added file playback
#          05Apr2021/v1.3 added housekeeping window
#          13Oct2022/v1.4 modify for flight version of imager
#          22Nov2022/v1.5 added range controls and hkpg limits

from datetime import (datetime, timedelta)
from threading import Thread
from serial import Serial
from os import (mkdir, path)
import sys
import time
import tkinter as tk
from tkinter import font
import queue
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg


packetTypes={0:7, 1:11,  2:11,  3:11,  4:11,  5:8,  6:18,  7:10}
maxLength=18
winBk="palegreen"

class GetData(Thread):
    """ collect imager data

    INPUT: prefix---------string prepended to output filename
    OUTPUT:
    Variables used outside this thread:
       datastreamActive---boolean to externally disable activity (__main__)
       packets------------queue of packets
    Functions used outside this thread:
       __init__()---------instantiate
       showOutfile()------return name of open output file
       newOutfile()-------close old and open new output file
       getStats()---------return a tuple describing good data so far
       run()--------------main loop is called when thread starts

    DESCRIPTION: This is a virtual class for two sub-classes
       One pulls data from a serial port, the other from a recorded
       file. Some functions are common to each subclass
          __init__()      wrapper is needed for each subclass
          showOutfile()
          newOutfile()
          getStats()
          _pktExtract()   identifies packets in data stream
    """

    def __init__(self, prefix=None):
        Thread.__init__(self)
        self._outFile = None
        self._rxbuf = b""
        self._bytesRead = 0
        self._junkBytes = 0
        self._packetCount = 0
        self._newFrameCntr = 0
        self._outfilename = ""
        self._prefix = prefix
        self.datastreamActive = None
        self.packets = queue.Queue()

        if prefix==None:
            self._outfilename = "n/a"
            self._outFile = None
            return

        if not path.isdir("packets"):
            mkdir("packets")
        try:
            self._outfilename = prefix+f"{datetime.utcnow():%Y%b%dT%H%M%S}.dat"
            self._outFile = open(path.join("packets", self._outfilename), "wb")
        except:
            print("failed to open output file")
            sys.exit(1)
            
# This is the main loop for this thread, in which we sleep most of the
# time. Periodically wake and check for serial data, or quitting time.

    def run(self):
        pass

    def _pktExtract(self,buffLen):
        if buffLen < (maxLength+1):
            return
        start = 0
        while start < (buffLen-maxLength):
            temp = self._rxbuf[start]
            if (temp & 0xFC) != 0xAC:
                self._junkBytes += 1
                start += 1
                continue
            pktType = (temp & 0x3)<<1
            temp = self._rxbuf[start+1]
            pktType |= ((temp & 0x80) >> 7)
            pktLen = packetTypes.get(pktType,"invalid packet code")
            if (self._rxbuf[start+pktLen] & 0xFC) != 0xAC:
                self._junkBytes += 1
                start += 1
                continue
            if pktType == 5:
                self._newFrameCntr += 1
            self.packets.put((pktType, self._rxbuf[start:start+pktLen]))
            self._packetCount += 1
            start += pktLen
        self._rxbuf = self._rxbuf[start:]

    def showOutfile(self):
        return self._outfilename

    def newOutfile(self):
        self._outFile.close()
        try:
            self._outfilename = self._prefix+f"{datetime.utcnow():%Y%b%dT%H%M%S}.dat"
            self._outFile = open(path.join("packets", self._outfilename), "wb")
        except:
            print("failed to open output file")
            sys.exit(1)
        return self._outfilename

    def getStats(self):
        return [self._bytesRead, self._junkBytes, self._packetCount]

########################### END OF BASE GetData CLASS ##############################

class SerialThread(GetData):
    """ pull in serial data and save it

    DESCRIPTION:
    
    """
    def __init__(self, ser, prefix):
        GetData.__init__(self, prefix)
        self._serialPort = ser

    def run(self):
        while self.datastreamActive:
           justread = self._serialPort.read(25000)
           newCount = len(justread)
           if newCount > 0:
               self._bytesRead += newCount
               self._outFile.write(justread)
               self._rxbuf += justread
               self._pktExtract(len(self._rxbuf))
           time.sleep(0.1)
        self._outFile.close()

########################### END OF SERIAL CLASS ##############################

class FileRead(GetData):
    """ pull data in from a file

    INPUTS: fp      is a file pointer to input file
            sps   is #seconds/s to pull from input file

    DESCRIPTION:
    
    """
    def __init__(self, fp, sps, live=False):
        GetData.__init__(self)
        self._fileID = fp
        self._startTime = time.perf_counter()
        self._sps = sps
        self.live = live

    def run(self):
        fileDone = False
        while self.datastreamActive:
            if not fileDone:
                justread = self._fileID.read(512)
                newCount = len(justread)
                if newCount == 512:
                    self._bytesRead += 512
                    self._rxbuf += justread
                    self._pktExtract(len(self._rxbuf))
                    expectTime = self._startTime + self._newFrameCntr/self._sps
                    nowTime = time.perf_counter()
                    if nowTime < expectTime:
                         time.sleep(expectTime - nowTime)
                    else:
                         time.sleep(0.05)      # allow time for other threads
                else:
                    # Skip next_lines for continuous readout
                    if not self.live:
                        fileDone = True
                        self._fileID.close()
                    self._bytesRead += newCount
                    self._rxbuf += justread
                    self._pktExtract(len(self._rxbuf))
                    if not self.live:
                        self._junkBytes += len(self._rxbuf)
            else:
                time.sleep(1)
        if not fileDone:
            self._fileID.close()

    def newOutfile(self):
        pass

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

class FourCounters:
    def __init__(self, panel, length, *args, **kwargs):
        self._x = [i for i in range(1-length,1)]
        self._tmp1 = length*[0]
        self._tmp2 = length*[0]
        self._tmp3 = length*[0]
        self._tmp4 = length*[0]
        self._cbuf1 = length*[0]
        self._cbuf2 = length*[0]
        self._cbuf3 = length*[0]
        self._cbuf4 = length*[0]
        self._addNext = 0
        self._len = length

        self._fig=panel.add_subplot(*args, **kwargs)
        self._ylabel = self._fig.get_ylabel()
        self._yscale = self._fig.get_yscale()
        self._ylim = list(self._fig.get_ylim())
        self._fig.set_xlim([-length,1])

    def getsetYlim(self, limits=None):
        if limits==None:
            return self._ylim
        else:
            self._ylim = limits

    def newPlot(self):
        self._fig.clear()
        self._fig.set_ylabel(self._ylabel)
        self._fig.set_ylim(self._ylim)
        self._fig.set_yscale(self._yscale)
        self._fig.set_xlim([-self._len,1])
        self._fig.plot([],[],'-',label='1',animated=True)
        self._fig.plot([],[],'-',label='2',animated=True)
        self._fig.plot([],[],'-',label='3',animated=True)
        self._fig.plot([],[],'-',label='4',animated=True)
        self._fig.legend(fontsize=6,markerscale=1)

    def addPMTs(self, fourcntrs):
        self._cbuf1[self._addNext] = fourcntrs[0]
        self._cbuf2[self._addNext] = fourcntrs[1]
        self._cbuf3[self._addNext] = fourcntrs[2]
        self._cbuf4[self._addNext] = fourcntrs[3]
        self._addNext = (self._addNext+1)%self._len

    def update(self):
        line1 = self._fig.lines[0]
        line2 = self._fig.lines[1]
        line3 = self._fig.lines[2]
        line4 = self._fig.lines[3]
        i =  0
        j = self._addNext
        while (i < self._len):
            self._tmp1[i] = self._cbuf1[j]
            self._tmp2[i] = self._cbuf2[j]
            self._tmp3[i] = self._cbuf3[j]
            self._tmp4[i] = self._cbuf4[j]
            i += 1
            j =(j+1)%self._len
        line1.set_data(self._x,self._tmp1)
        line2.set_data(self._x,self._tmp2)
        line3.set_data(self._x,self._tmp3)
        line4.set_data(self._x,self._tmp4)
        self._fig.draw_artist(line1)
        self._fig.draw_artist(line2)
        self._fig.draw_artist(line3)
        self._fig.draw_artist(line4)

######################### END OF FourCounters class ############################

class TimeGraphs:
    """ stripchart of rate data

        ll, pd, hl are 3 stripchart subplots of class FourCounters
                   which are also accessed by BMSDisplay, and so are
                   not private
    """

    def __init__(self, base):
        self._panel = Figure(figsize=(9.5,4.5), dpi=100)
        self._panel.set_tight_layout(True)
        self._plotRegion = FigureCanvasTkAgg(self._panel, base)
        self._plotRegion.get_tk_widget().grid(row=0, column=0,
                padx=5, pady=5)
        self.ll=FourCounters(self._panel, 60, 311, yscale="log", 
                ylim=[100, 5000], ylabel="low disc")
        self.pd=FourCounters(self._panel, 60, 312, yscale="log", 
                ylim=[100, 5000], ylabel="peak det")
        self.hl=FourCounters(self._panel, 60, 313, yscale="log", 
                ylim=[1, 50], ylabel="high disc")
        self._refresh = True

    def update(self):
        if (self._refresh):
            self._refresh = False
            self.ll.newPlot()
            self.pd.newPlot()
            self.hl.newPlot()
            self._plotRegion.draw()
            self._bkgd = self._panel.canvas.copy_from_bbox(self._panel.bbox)
        else:
            self._panel.canvas.restore_region(self._bkgd)

        self.ll.update()
        self.pd.update()
        self.hl.update()
        self._plotRegion.blit(self._panel.bbox)
        
########################## END OF TimeGraphs class #############################

class PDWindow(tk.LabelFrame):
    """ create and update the PD counter windows

        __init__(container,title)
        update((lowlevel, peak detect, highlevel))
                   changes display
    """
    def __init__(self, base, title, bgColor):
        tk.LabelFrame.__init__(self, base, text=title, pady=5,
          padx=5, bg=bgColor)
        self._ll = tk.IntVar(base,0)
        self._pd = tk.IntVar(base,0)
        self._hl = tk.IntVar(base,0)
        stuffLabelFrame(self, ["loLev", "peakDet", "hiLev"],
                [self._ll, self._pd, self._hl], vw=5, lw=7)
            
    def update(self, boardCounters):
        for (var,val) in zip([self._ll, self._pd, self._hl], boardCounters):
            var.set(val)
        return

########################### END OF PDWindow CLASS ##############################


class HKPWindow(tk.LabelFrame):
    """ create and update an analog housekeeping window

        __init__(container)
        update((hk1, hk2, hk3, hk4, hk5, hk6, hk7, hk8))
                   changes display
    """
    limitsDictionary={}
    valuesDictionary={}
    labels = [ "Txtl (C)", "Tdpu (C)", "im +5.0V", "im -5.0V", "im +I (mA)",
               "im -I (mA)",  "+5.0V", "+curr(mA)"]
    limits = [(-40, 60), (-40, 60), (4.5, 6.0), (-6.0, -4.5), (77, 87),
              (-11, -7), (4.8, 5.2), (105, 121)]

    def __init__(self, base):
        tk.LabelFrame.__init__(self, base, text="analog hkpg", 
                               bg='lightgray', pady=5, padx=5)
        self._hk1 = tk.StringVar(base,"no data")
        self._hk2 = tk.StringVar(base,"no data")
        self._hk3 = tk.StringVar(base,"no data")
        self._hk4 = tk.StringVar(base,"no data")
        self._hk5 = tk.StringVar(base,"no data")
        self._hk6 = tk.StringVar(base,"no data")
        self._hk7 = tk.StringVar(base,"no data")
        self._hk8 = tk.StringVar(base,"no data")
        handles = stuffLabelFrame(self, HKPWindow.labels,
                 [self._hk1, self._hk2, self._hk3, self._hk4, self._hk5, self._hk6,
                  self._hk8, self._hk7], vw=5, lw=9)
        for lab, han, lim in zip(HKPWindow.labels, handles, HKPWindow.limits):
            if lim != None:
                HKPWindow.limitsDictionary[lab] = (han,)+lim
            
    def update(self, vals):
        t1 = vals[0]/10. - 273.2
        t2 = vals[1]/10. - 273.2
        vp = vals[2]*0.00132
        vm = -vals[3]*0.00127
        ip = vals[4]/10.
        im = -vals[5]/100.
        i5 = vals[6]/10.
        v5 = vals[7]*0.00132
        self._hk1.set(f"{t1:5.1f}")
        self._hk2.set(f"{t2:5.1f}")
        self._hk3.set(f"{vp:4.2f}")
        self._hk4.set(f"{vm:5.2f}")
        self._hk5.set(f"{ip:5.1f}")
        self._hk6.set(f"{im:5.1f}")
        self._hk7.set(f"{i5:5.1f}")
        self._hk8.set(f"{v5:4.2f}")
        for name, var in zip(HKPWindow.labels,[t1,t2,vp,vm,ip,im,v5,i5]):
            HKPWindow.valuesDictionary[name] = var
        self.checkLimits()
        return

    def checkLimits(self):
        for label, (handle, lo, hi) in HKPWindow.limitsDictionary.items():
            measurement = HKPWindow.valuesDictionary[label]
            if lo <= measurement <= hi:
                handle.config(bg='lightgray')
            else:
                handle.config(bg='yellow')

########################### END OF LOGWindow CLASS ##############################

class HDRWindow():
    """ create and maintain the header at top of window

        __init__() needs name of window's container
        update(vals)
             vals: a tuple of values to display

        These variables are accessed externally
            nowString, pps, numSecs, message, window

    """
    def __init__(self, base, sheets):
        self._pktCount  = tk.IntVar(base,0)
        self._ID        = tk.IntVar(base,-1)
        self._swver     = tk.IntVar(base,-1)
        self._FC        = tk.IntVar(base,0)
        self._rcvCount  = tk.IntVar(base,0)
        self._junk      = tk.IntVar(base,0)
        self._sheets     = sheets
        self._page       = tk.StringVar(base,"page1")
        self.nowString  = tk.StringVar(base,"2020xxxxxTxx:xx:xx")
        self.pps        = tk.IntVar(base,0)
        self.numSecs    = tk.IntVar(base,0)
        self.message    = tk.StringVar(base,"no messages yet")

        hd = tk.Frame(base, bg="lightgray")
        tk.Label(hd, textvar=self.nowString,anchor=tk.E).grid(row=0,
              column=0, columnspan=2, sticky=tk.E)
        tk.Label(hd, text="packet counter").grid(row=0, column=2, sticky=tk.E)
        tk.Label(hd, textvar=self._pktCount,width=7,anchor=tk.E,
                 relief="sunken").grid( row=0, column=3, sticky=tk.E)
        tk.Label(hd, text="camera ID").grid(row=1, column=0, sticky=tk.E)
        tk.Label(hd, textvar=self._ID).grid(row=1, column=1, sticky=tk.E)

        tk.Label(hd, text="frame counter").grid(row=1, column=2, sticky=tk.E)
        tk.Label(hd, textvar=self._FC,width=7,anchor=tk.E,
                 relief="sunken").grid(row=1, column=3, sticky=tk.E)
        tk.Label(hd, text="seconds").grid(row=0, column=4, sticky=tk.E)
        tk.Label(hd, textvar=self.numSecs,width=8,anchor=tk.E,
                 relief="sunken").grid( row=0, column=5, sticky=tk.E)
        tk.Label(hd, text="pps delay").grid(row=1, column=4, sticky=tk.E)
        tk.Label(hd, textvar=self.pps,width=8,anchor=tk.E,
                 relief="sunken").grid( row=1, column=5, sticky=tk.E)
        tk.Label(hd, text="read bytes").grid(row=0, column=6, sticky=tk.E)
        tk.Label(hd, textvar=self._rcvCount,width=8,anchor=tk.E,
                 relief="sunken").grid( row=0, column=7, sticky=tk.E)
        tk.Label(hd, text="junk bytes").grid(row=1, column=6, sticky=tk.E)
        tk.Label(hd, textvar=self._junk,width=8,anchor=tk.E,
                 relief="sunken").grid( row=1, column=7, sticky=tk.E)
        tk.Label(hd,textvar=self.message, width=33, anchor="w", 
                 bg="white").grid(row=0, column=8, sticky=tk.EW, padx=10)
        tk.Button(hd, text="Quit", bg="red", command=base.destroy).grid(
              row=1, column=8)
        tk.Radiobutton(hd, text="frontpage", variable=self._page, value="page1",
                       bg="lightgray", command=self.showMain).grid(row=0,
                                       column=9, sticky=tk.W)
        tk.Radiobutton(hd, text="stripchart", variable=self._page, value="page2",
                       bg="lightgray", command=self.showStripChart).grid(
                                       row=1, column=9, sticky=tk.W)
        self.window = hd

    def showMain(self):
        self._sheets["page1"].tkraise()

    def showStripChart(self):
        self._sheets["page2"].tkraise()

#   update header information
    def update(self, vals):               # vals is [fc, id, _swver]
        temp = thread1.getStats()         # returns [byteCount, junkCount packetCount]
        self._rcvCount.set(temp[0])
        self._junk.set(temp[1])
        self._pktCount.set(temp[2])
        self._FC.set(vals[0])
        self._ID.set(vals[1])
        self._swver.set(vals[2])

########################### END OF HDRWindow CLASS ##############################

class SpecControlBox(tk.LabelFrame):
    """ control appearance of spectrum figure
    """
    def __init__(self, base, sG):
        tk.LabelFrame.__init__(self,base,text='figure control',bg='lightgray')
        buttons=tk.Frame(self,bg='lightgray')
        buttons.grid(row=0,column=0,padx=5,pady=0,sticky=tk.W)
        tk.Button(buttons,text="clear",command=sG.clear).grid(row=0,
                  column=0, padx=5, pady=5, sticky=tk.W)
        tk.Label(buttons, anchor="e", text="events", bg="lightgray", relief="flat",
            width=6, padx=1).grid(row=0, column=1)
        tk.Label(buttons, textvar=sG.xrayCntr, padx=3, anchor="e",
                 bg="lightgray", font="TkFixedFont", width=7, relief="sunken").grid(
                 row=0, column=2)
        # Display max channels
        tk.Label(buttons, anchor="e", text="max ch", bg="lightgray", relief="flat",
            width=6, pady=5, padx=5).grid(row=1, column=0)
        tk.Label(buttons, textvar=sG.maxch, padx=3, anchor="e",
                 bg="lightgray", font="TkFixedFont", width=16, relief="sunken").grid(
                 row=1, column=1, columnspan=2)
        limitsGroup=tk.Frame(self, bg="lightgray")
        limitsGroup.grid(row=2,column=0)
        self._xControl = MinMaxControl(limitsGroup, sG.getsetXlim,
                                      [-5,1050], "X")
        self._xControl.grid(row=0, column=0)
        self._yControl = MinMaxControl(limitsGroup, sG.getsetYlim,
                                      [0.00001,1000000], "Y")
        self._yControl.grid(row=0, column=1)
        tk.Button(self, activeforeground="green",text="update",
                  command=self.update).grid(row=3,column=0,pady=5)
        self._redraw = sG.redraw

    def update(self):
        state1 = self._xControl.update()
        state2 = self._yControl.update()
        if (state1 or state2):
            self._redraw()
            

########################### END OF SpecControlBox CLASS ##############################

class MinMaxControl(tk.Frame):
    """ a Frame to control min/max parameters of spectrum plot
    """
    def __init__(self, base, limitsFunc, limits, label):
        tk.Frame.__init__(self,base,bg='lightgray')
        self._lolim = limits[0]
        self._hilim = limits[1]
        currentLimits = limitsFunc()
        self._minVal = tk.StringVar(self,str(currentLimits[0]))
        self._maxVal = tk.StringVar(self,str(currentLimits[1]))
        tk.Label(self,bg='lightgray',text=label+"min").grid(
                 row=0, column=0)
        tk.Entry(self, width=5, justify="right", bd=3,
                 highlightbackground="lightgray",
                 font="TkFixedFont", textvariable=self._minVal).grid(
                 row=0, column=1)
        tk.Label(self,bg='lightgray',text=label+"max").grid(
                 row=1, column=0)
        tk.Entry(self,width=5, justify="right", bd=3,
                 highlightbackground="lightgray",
                 font="TkFixedFont", textvariable=self._maxVal).grid(
                 row=1, column=1)
        self._limitsFunc = limitsFunc

    def update(self):
        redraw = False
        currentLimits = self._limitsFunc()

        data = self._minVal.get()
        try:
            value = float(data)
        except:
            print("min formatting error: "+data)
            self._minVal.set(str(currentLimits[0]))
            return
        if (value != currentLimits[0]):
            if (value < self._lolim or value > self._hilim):
                print("min value out of range "+data)
                self._minVal.set(str(currentLimits[0]))
                return
            redraw = True
            currentLimits[0] = value

        data = self._maxVal.get()
        try:
            value = float(data)
        except:
            print("max formatting error: "+data)
            self._maxVal.set(str(currentLimits[1]))
            return
        if (value != currentLimits[1]):
            if (value < self._lolim or value > self._hilim):
                print("max value out of range "+data)
                self._maxVal.set(str(currentLimits[1]))
                return
            redraw = True
            currentLimits[1] = value

        if redraw:
            self._limitsFunc(currentLimits)

        return redraw

########################### END OF MinMaxControl CLASS ##############################

class SpecGrapher:
    """ display event spectra
            
        __init__(parent) interfaces between matplotlib and Tk sets up the
                         panel---draws axes, labels, title
        clear()          clears the 4 pmt spectra
        update() refresh the spectrum plot
        Some variables are accessed externally:
            secCntr, xrayCntr, cnt1, cnt2, cnt3, cnt4
    """
    def __init__(self, base):
        self.secCntr = tk.IntVar(base,0)
        self.xrayCntr = tk.IntVar(base,0)
        self.maxch = tk.StringVar(base, ' '.join([str(0)]*4))
        self._xlim = [-5, 1050]
        self._ylim = [0.01, 100]
        self._newDraw=True
        self.cnt1=1024*[0]
        self.cnt2=1024*[0]
        self.cnt3=1024*[0]
        self.cnt4=1024*[0]
        self._sumSpec=1500*[0]
        self._x = [i for i in range(1024)]

        self._panel = Figure(figsize=(6,4),dpi=100)
        self._plotRegion = FigureCanvasTkAgg(self._panel, base)
        self._plotRegion.get_tk_widget().grid(row=0, column=0)
        self._fig = self._panel.add_subplot()

    def clear(self):
        self.secCntr.set(0)
        self.xrayCntr.set(0)
        self.maxch.set(0)
        self.cnt1 = 1024*[0]
        self.cnt2 = 1024*[0]
        self.cnt3 = 1024*[0]
        self.cnt4 = 1024*[0]

    def getsetXlim(self, limits=None):
        if limits==None:
            return self._xlim
        else:
            self._xlim = limits

    def getsetYlim(self, limits=None):
        if limits==None:
            return self._ylim
        else:
            self._ylim = limits

    def redraw(self):
        self._newDraw = True

    def update(self):
        if self._newDraw:
            self._newDraw = False
            self._fig.clear()
            self._fig.set_ylabel("counts/(bin-s)")
            self._fig.set_xlabel("bin")
            self._fig.set_xlim(self._xlim)
            self._fig.set_ylim(self._ylim)
            self._fig.set_yscale("log")
            self._fig.set_title("4 PMT spectra")
            self._fig.plot([],[],'.',markersize=2,label='pmt1',animated=True)
            self._fig.plot([],[],'.',markersize=2,label='pmt2',animated=True)
            self._fig.plot([],[],'.',markersize=2,label='pmt3',animated=True)
            self._fig.plot([],[],'.',markersize=2,label='pmt4',animated=True)
            self._fig.legend(markerscale=5)
            self._plotRegion.draw()
            self._bkgd=self._panel.canvas.copy_from_bbox(self._panel.bbox)
        else:
            self._panel.canvas.restore_region(self._bkgd)

        line1=self._fig.lines[0]
        line2=self._fig.lines[1]
        line3=self._fig.lines[2]
        line4=self._fig.lines[3]
        counts=self.secCntr.get()
        if counts>0:
            temp=[a/counts for a in self.cnt1]
            line1.set_data(self._x,temp)
            temp=[a/counts for a in self.cnt2]
            line2.set_data(self._x,temp)
            temp=[a/counts for a in self.cnt3]
            line3.set_data(self._x,temp)
            temp=[a/counts for a in self.cnt4]
            line4.set_data(self._x,temp)
        self._fig.draw_artist(line1)
        self._fig.draw_artist(line2)
        self._fig.draw_artist(line3)
        self._fig.draw_artist(line4)
        self._plotRegion.blit(self._panel.bbox)

########################### END OF SpecGrapher CLASS ##############################

class BMSDisplay(tk.Tk):
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
        tk.Tk.__init__(self, *args, **kwargs)
#        self.minsize(1140,660)
        self.title("BOOMS: imager GSE v1.4/23Nov2022")
        self.config(bg=winBk)
        self.option_add("*Label*background","lightgray")
        self.option_add("*Labelframe*background","lightgray")
        self.option_add("*Frame.background",winBk)
        self.pd1 = (0,0,0)
        self.pd2 = (0,0,0)
        self.pd3 = (0,0,0)
        self.pd4 = (0,0,0)
        self.secs = 0
        self.swver = -1
        self.ID = -1
        self.pktCount = 0
        self.fc = -1
        self.oldfc = -1
        tempfont=font.nametofont("TkFixedFont")
        tempfont.configure(family="Monaco", size=11)
        tempfont=font.nametofont("TkDefaultFont")
        tempfont.configure(size=11)

        widgetDict={}
        self.bodySpace = tk.Frame(self)
        self.pdSpace = tk.Frame(self)
        widgetDict["page1"] = self.bodySpace
        widgetDict["page2"] = self.pdSpace
        self.bodySpace.grid(row=1, column=0, sticky=tk.NSEW)
        self.pdSpace.grid(row=1, column=0, sticky=tk.NSEW)
        self.bodySpace.tkraise()

        self.hdr = HDRWindow(self, widgetDict)
        self.hdr.window.grid(row=0, column=0, sticky=tk.NSEW)
        leftBox = tk.Frame(self.bodySpace, bg=winBk)
        self.pdTabl = tk.LabelFrame(leftBox, text="PD boards", 
                            bg="lightgray", padx=5, pady=5)
        self.pdTabl.grid(row=0, column=0, sticky=tk.EW+tk.N)
        self.pdWin1=PDWindow(self.pdTabl, "PD board 1", '#1F77B4')
        self.pdWin1.grid(row=0, column=1, sticky=tk.E, padx=5, pady=5)
        self.pdWin2=PDWindow(self.pdTabl, "PD board 2", '#FF7F0E')
        self.pdWin2.grid(row=0, column=0, sticky=tk.E, padx=5, pady=5)
        self.pdWin3=PDWindow(self.pdTabl, "PD board 3", '#2CA02C')
        self.pdWin3.grid(row=1, column=0, sticky=tk.E, padx=5, pady=5)
        self.pdWin4=PDWindow(self.pdTabl, "PD board 4", '#D62728')
        self.pdWin4.grid(row=1, column=1, sticky=tk.E, padx=5, pady=5)
        self.hkpg = HKPWindow(leftBox)
        self.hkpg.grid(row=0, column=1, padx=5, pady=5,
                       sticky=tk.N+tk.EW)

        specFrame=tk.Frame(self.bodySpace, bg=winBk, padx=5, pady=5)
        specFrame.grid(row=0,column=1)
        self.spec = SpecGrapher(specFrame)
        specControl = SpecControlBox(leftBox, self.spec)
        specControl.grid(row=2,column=0,columnspan=2, pady=5, sticky=tk.E)
        leftBox.grid(row=0, column=0, sticky=tk.NW, padx=4, pady=4)
        leftts=tk.Frame(self.pdSpace, bg=winBk, padx=5)
        leftts.grid(row=0, column=0)
        rightts=tk.Frame(self.pdSpace)
        rightts.grid(row=0, column=1)
        self.tsPlots=TimeGraphs(rightts)
        self.llControl = MinMaxControl(leftts, self.tsPlots.ll.getsetYlim,
            [0.1,100000], "Y")
        self.llControl.grid(row=0, column=0, pady=40)
        self.pdControl = MinMaxControl(leftts, self.tsPlots.pd.getsetYlim,
            [0.1,100000], "Y")
        self.pdControl.grid(row=2, column=0, pady=40)
        self.hlControl = MinMaxControl(leftts, self.tsPlots.hl.getsetYlim,
            [0.1,100], "Y")
        self.hlControl.grid(row=3, column=0, pady=40)
        tk.Button(leftts, activeforeground="green", text="update",
                  command=self.tsupdate).grid(row=1, column=0, pady=5)

    def tsupdate(self):
        state1 = self.llControl.update()
        state2 = self.pdControl.update()
        state3 = self.hlControl.update()
        if (state1 or state2 or state3):
            self.tsPlots._refresh = True

    def whatsNew(self):
        """ loop monitors new data from serial thread

            DESCRIPTION: calls itself every 250ms
                         update live clock
                         if diagnostic is queued, print it
                         if packet arrived, update display
        """
        self.after(250,self.whatsNew)
        self.hdr.nowString.set(format(datetime.utcnow(),
                                  "%Y%b%dT%H:%M:%S"))
        if not thread1.packets.empty():
            self._parsePackets(thread1.packets)
        if self.oldfc != self.fc:
            self.oldfc = self.fc
            self.pdWin1.update(self.pd1)
            self.pdWin2.update(self.pd2)
            self.pdWin3.update(self.pd3)
            self.pdWin4.update(self.pd4)
            self.spec.update()
            temp=list(zip(*[list(self.pd1), list(self.pd2),
                           list(self.pd3), list(self.pd4)]))
            self.tsPlots.ll.addPMTs(temp[0])
            self.tsPlots.pd.addPMTs(temp[1])
            self.tsPlots.hl.addPMTs(temp[2])
            self.tsPlots.update()
        self.hdr.update((self.fc, self.ID, self.swver))

    def _getHkpg(pkt):
        hkp1 = (int(pkt[2])<<8) | int(pkt[3])
        hkp2 = (int(pkt[4])<<8) | int(pkt[5])
        hkp3 = (int(pkt[6])<<8) | int(pkt[7])
        hkp4 = (int(pkt[8])<<8) | int(pkt[9])
        hkp5 = (int(pkt[10])<<8) | int(pkt[11])
        hkp6 = (int(pkt[12])<<8) | int(pkt[13])
        hkp7 = (int(pkt[14])<<8) | int(pkt[15])
        hkp8 = (int(pkt[16])<<8) | int(pkt[17])
        return (hkp1, hkp2, hkp3, hkp4, hkp5, hkp6, hkp7, hkp8)

    def _getTubes(pkt):
        pmt1 = (int(pkt[2]))<<2 | (int(pkt[3])>>6)
        pmt2 = (int(pkt[3]) & 0x3F)<<4 | (int(pkt[4])>>4)
        pmt3 = (int(pkt[4]) & 0xF)<<6 | int(pkt[5])>>2
        pmt4 = (int(pkt[5]) & 0x3)<<8 | int(pkt[6])
#        if (pmt1>1023 or pmt2>1023 or pmt3>1023 or pmt4>1023):
#            tempstring="".join(f"{c:02X}" for c in pkt)
#            print(tempstring,pmt1,pmt2,pmt3,pmt4)
#            return((0,0,0,0,0))
        total = (pmt1 + pmt2 + pmt3 + pmt4 + 2) >> 2
        return (pmt1, pmt2, pmt3, pmt4, total)

    def _getCounters(pkt):
        c1 = int(pkt[2])<<8 | int(pkt[3])
        c2 = int(pkt[4])<<8 | int(pkt[5])
        c3 = int(pkt[6])<<8 | int(pkt[7])
        return (c1, c2, c3)

    def _parsePackets(self, q):
        """ pull packets from queue and collect their contents
            DESCRIPTION: 
        """
        while q.qsize() > 20:
            (id,pkt) = q.get_nowait()
            self.pktCount += 1
            temp = int(pkt[1]) & 0x7F
            if id==0:
                tubes = BMSDisplay._getTubes(pkt)
                self.spec.cnt1[tubes[0]] += 1
                self.spec.cnt2[tubes[1]] += 1
                self.spec.cnt3[tubes[2]] += 1
                self.spec.cnt4[tubes[3]] += 1
                temp = self.spec.xrayCntr.get()
                self.spec.xrayCntr.set(temp+1)

                tube_totals = [self.spec.cnt1, self.spec.cnt2, self.spec.cnt3, self.spec.cnt4]
                max_chs = [str(max(range(len(t)), key=lambda x: t[x])) for t in tube_totals]
                max_ch_str = ' '.join(max_chs)
                self.spec.maxch.set(max_ch_str)
            elif id==1:
                self.pd1 = BMSDisplay._getCounters(pkt)
            elif id==2:
                self.pd2 = BMSDisplay._getCounters(pkt)
            elif id==3:
                self.pd3 = BMSDisplay._getCounters(pkt)
            elif id==4:
                self.pd4 = BMSDisplay._getCounters(pkt)
            elif id==5:
                self.ID = (int(pkt[1]) & 0x70)>>4
                self.swver = int(pkt[1]) & 0x0F
                self.hdr.pps.set(int(pkt[2])<<8 | int(pkt[3]))
                temp = self.spec.secCntr.get()
                temp += 1
                self.spec.secCntr.set(temp)
                self.secs += 1
                self.hdr.numSecs.set(self.secs)
                self.fc = ((int(pkt[4])<<24) | (int(pkt[5])<<16) |
                                (int(pkt[6])<<8) | int(pkt[7]))
            elif id==6:
                hk = BMSDisplay._getHkpg(pkt)
                self.hkpg.update(hk);
            elif id==7:
                pass

########################### END OF BMSDisplay CLASS ##############################

def run_gse(serial_port, baud_rate=None, live=False):
    if baud_rate is not None:
        try:
            ser = Serial(serial_port, 230400, timeout=0.1)
        except:
            print("ERROR: Cannot open serial port", serial_port)
            sys.exit(-1)
        print("starting serial thread")
        thread1 = SerialThread(ser, "IMGR")
        thread1.datastreamActive = True
        thread1.start()
        starting = datetime.utcnow()
        print("starting display")
        gui = BMSDisplay()
        gui.whatsNew()
        gui.mainloop()

        print("shutting down in 1s") # clean up after gui quits
        thread1.datastreamActive = False
        time.sleep(1)
        ser.close()
    else:
        try:
            filePtr = open(serial_port, "rb")
            if live:
                filePtr.seek(-1, 2)
        except:
            print("failed to open input file", serial_port)
            sys.exit(1)
        try:
            secsPerSecond = float(baud_rate)
        except:
            print("invalid seconds per second argument:"+baud_rate)
            sys.exit(1)
        if (secsPerSecond <= 0):
            print("invalid seconds per second argument:"+baud_rate)
            sys.exit(1)

        print("starting file thread", sys.argv[1], secsPerSecond)
        thread1 = FileRead(filePtr, secsPerSecond)
        thread1.datastreamActive = True
        thread1.start()
        print("starting display")
        starting = datetime.utcnow()
        gui = BMSDisplay()
        gui.hdr.message.set(serial_port)
        gui.whatsNew()
        gui.mainloop()

        print("shutting down in 1s") # clean up after gui quits
        thread1.datastreamActive = False
        time.sleep(1)
    print("All done")

