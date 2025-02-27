# Need this first: python -m pip install jinja2 pywin32 pandas
import jinja2 # code to format a .jinja file into an output document
import argparse # command line argument parser
import os # filename and pathname functions
import ctypes, ctypes.wintypes
import winreg
import time
import win32gui, win32con, win32api
import pandas as pd
from jinja2 import Environment, FileSystemLoader

# Generate AYC Scoring Sheets given SailWave
# Author: Barry Bond
# License: MIT License
#
# To use:
#  Prereqs:
#    Install Python from the Windows app store
#    From the command prompt, "python -m pip install jinja2" to install the Jinja2 extension
#  In SailWave:
#    Import and tidy up the competitor list, paying attention to the HelmName, Fleet, SailNo and Boat fields.  Alt Sail Number is supported too.
#    use File/Save as XML... and save the XML file to your PC
#  From the command prompt:
#    python ScoringSheet.py --xml SailWaveFile.xml --name "AYC Lake Pleasant 2025 B-Day Sat/Sun"
#  Which will produce a bunch of *.html files in the same directory, one for each fleet.  Print them all.

FindWindow = ctypes.windll.user32.FindWindowW
SendMessage = ctypes.windll.user32.SendMessageW

# Definition of a competitor, using SailWave concepts
class Competitor:
    def __init__(self, helmname, boat, sailno, altsailno):
        self.helmname = helmname
        self.boat = boat
        self.sailno = sailno
        self.altsailno = altsailno

class COPYDATASTRUCT(ctypes.Structure):
    _fields_ = [
        ('dwData', ctypes.wintypes.LPARAM),
        ('cbData', ctypes.wintypes.DWORD),
        ('lpData', ctypes.c_char_p) 
]
PCOPYDATASTRUCT = ctypes.POINTER(COPYDATASTRUCT)

# Wrapper to help launch and access a Sailwave running app and communicate with it.
class Sailwave:
    def __init__(self):
        self.needs_to_close = False
        self.SW_hwnd = 0
        self.pCDS = None
        self.SW_data_return=None
        self.message_return=""
        self.buffer_return=""

        message_map = {
            win32con.WM_COPYDATA: self.__OnCopyData
        }

        # Create an HWND_MESSAGE window so we can listen for Swailwave calls
        wc = win32gui.WNDCLASS()
        wc.lpfnWndProc = message_map
        wc.lpszClassName = 'ScoringSheetLive_WC'
        hinst = wc.hInstance = win32api.GetModuleHandle(None)

        win32gui.RegisterClass(wc)
        
        hwnd_message = 0xFFFFFFFFFFFFFFFD
        self.mywnd= win32gui.CreateWindowEx (
            0, # dwExStyle
            wc.lpszClassName, # classname
            None, # Window name
            0, # window style
            0, # X
            0, # Y
            0, # Width
            0, # Height
            hwnd_message, # hwndParent
            None, # hMenu
            hinst, # hInstance
            None # lpParam
        )
        if self.mywnd == 0:
            print("Failed to create window")
            exit(3)

    # WndProc callback for WM_COPYDATA messages.
    def __OnCopyData(self, SW_hwnd, msg, wparam, lparam):
        self.pCDS = ctypes.cast(lparam, PCOPYDATASTRUCT)      
        self.message_return=self.pCDS.contents.dwData
        self.buffer_return=self.pCDS.contents.lpData
        self.SW_data_return=str(self.pCDS.contents.lpData[:self.pCDS.contents.cbData].replace(b"\r",b"\n").decode('latin-1'))
        return 1

    # Check the Sailwave version installed on the PC.
    # Returns True if it is OK, False otherwise.
    def CheckVersion() -> bool:
        registry = winreg.ConnectRegistry(None, winreg.HKEY_CURRENT_USER)
        validversion='0002.0028.0011'
        try:
            with winreg.OpenKey(registry, r"Software\Sailwave\Version") as Sailwave_key:
                name, version, type = winreg.EnumValue(Sailwave_key, 0)
                version_list=version.split('.')
                if version_list[0].zfill(4)+'.'+version_list[1].zfill(4)+'.'+version_list[2].zfill(4) < validversion :
                    print('Incorrect Sailwave version found. Version 2.28.11 or greater is needed')
                    return False
        except WindowsError:
            print('Sailwave not found. Version 2.28.11 or greater is needed')
            return False
        return True

    # Start the Sailwave app with the given path.
    # 'running' allows attach to an existing running Sailwave instance if it is present,
    #           otherwise it starts a fresh one.
    def Start(self, pathname, running) -> bool:
        # Go see if Sailwave is running and has the file open already
        fullpathname = os.path.abspath(pathname)
        SW_hwnd = win32gui.FindWindowEx(None, None, None, "Sailwave - "+ fullpathname)  # get the handle
        if SW_hwnd != 0:
            # Sailwave is running and has the file open
            if running:
                # Attach-to-running is allowed - proceed.
                print("Attaching to running Sailwave")
            else:
                # Attach-to-running is not allowed.  Bail out.
                print(f'The file "{pathname}" is open already. Close it and try again.')
                return False
        else:
            # Sailwave isn't running, so launch it now.
            os.startfile(pathname, 'open')
            # Sleep before getting the sailwave handle
            max_sleep_time = 15
            sleep_time=0.1
            while SW_hwnd == 0:
                time.sleep(sleep_time)
                SW_hwnd = win32gui.FindWindowEx(None, None, None, "Sailwave - "+ fullpathname)  # get the handle
                sleep_time=sleep_time+1 
                if sleep_time > max_sleep_time:
                    print('Timed out waiting for Sailwave to launch')
                    return 0

            # Remember that we opened it, so we need to close it when done.            
            self.needs_to_close = True

        # Minimize the Sailwave window           
        win32gui.ShowWindow(SW_hwnd, win32con.SW_MINIMIZE)

        # Tell Sailwave where to send the data
        string = str(self.mywnd).encode('ASCII')
        cds = COPYDATASTRUCT()
        cds.dwData = 1   #notify Sailwave
        cds.cbData = ctypes.sizeof(ctypes.create_string_buffer(string))    
        cds.lpData = ctypes.c_char_p(string)

        # initiate Sailwave
        SendMessage(SW_hwnd, win32con.WM_COPYDATA, self.mywnd, ctypes.byref(cds))
        time.sleep(0.1)
        win32gui.PumpWaitingMessages()

        self.SW_hwnd = SW_hwnd
        return True

    # Close the Sailwave instance.  This will leave it running if it was already running
    # and '--running' was passed on the command line.    
    def Close(self):
        # Restore window
        win32gui.ShowWindow(self.SW_hwnd, win32con.SW_RESTORE)
        time.sleep(0.1)
        
        # Close Sailwave  Message 32 this will Close Sailwave without saving any data
        if self.needs_to_close:
            cds = COPYDATASTRUCT()
            cds.dwData = 32   #close it
            SendMessage(self.SW_hwnd, win32con.WM_COPYDATA, self.mywnd, ctypes.byref(cds))
            time.sleep(0.1)
        win32gui.PumpWaitingMessages()
        self.SW_hwnd = 0

    # Helper to wait for a fresh WM_COPYDATA message back from Sailwave with a reply in it.
    def __wait_for_message_data(self,string,message):
        cds = COPYDATASTRUCT()
        iloop=0
        while self.SW_data_return is None:
            iloop = iloop +1
            if iloop == 90 :
                # Close Sailwave file and abort
                self.Close()
                print(f'Unable to process this file. Message: {message}')
                exit(4)
            time.sleep(0.1)
            win32gui.PumpWaitingMessages() 
    
        return

    # Convert Sailwave data into a Pandas table
    # SW_Data_in is a long string with '\n' separators, of rows of CSV data, each with 4 columns.  fieldname,value1,value2,value3.
    def __SW_to_DF(SW_Data_in):
        SW_Data_out = pd.DataFrame([x[1:-1].split('","') for x in SW_Data_in.splitlines()],columns=["one", "two", "three","four"])
        SW_Data_out = SW_Data_out.where(pd.notnull(SW_Data_out), '').copy()
        return(SW_Data_out)

    # Call Sailwave to retrieve the competitor list and reformat it into
    # dictionary mapping fleet to list of Competitor objects.
    def GetCompetitors(self):
        self.SW_data_return = None
        cds = COPYDATASTRUCT()
        cds.dwData = 7    # Request competitor info
        SendMessage(self.SW_hwnd, win32con.WM_COPYDATA, self.mywnd, ctypes.byref(cds))
        self.__wait_for_message_data('comptotal', cds.dwData)  # this waits until the current datastring is found or exits and closes Sailwave file

        #
        #convert Sailwave buffer to dataframe structure
        comp_info = Sailwave.__SW_to_DF(self.SW_data_return)
        competitors = (comp_info.pivot(index='three', columns='one', values='two')
            .fillna('')
            .reset_index()
            .rename(columns = {'three':'ID'}))

        # Convert into our dictionary mapping fleets to list of Competitor objects
        fleets = {}
        for competitor in competitors.index:
            # competitors[][] is a 2-day array indexed by named column from Sailwave 
            # and an integer competitor ID number.
            compfleet = competitors['compfleet'][competitor]
            comphelmname = competitors['comphelmname'][competitor]
            compboat = competitors['compboat'][competitor]
            compsailno = competitors['compsailno'][competitor]
            compaltsailno = competitors['compaltsailno'][competitor]
            c = Competitor(comphelmname, compboat, compsailno, compaltsailno)

            # If this is the first competitor in the fleet, then create an empty
            # competitor list
            if not compfleet in fleets:
                fleets[compfleet] = []

            # Add the new competitor to the per-fleet list
            fleets[compfleet].append(c)
        return fleets                

# Python sort helper, to make sailno make sense within a Competitor object.
def competitorSailNumber(val):
    # Try to convert to an integer, so that "841" sorts before "1841".  But also support "B302"
    try:
        i = int(val.sailno) # convert to integer, or thow ValueError
        return str(i).zfill(10)  # return as a zero-padded 10-digit number
    except ValueError:
        return val.sailno

# Generate a scoring sheet HTML into a string
def generateScoringSheet(racetitle, fleet, competitors):
    # sort the competitors by sailno
    competitors.sort(key=competitorSailNumber)

    # determine the directory where the .py file was found
    template_directory = os.path.dirname(os.path.abspath(__file__))

    env = Environment(loader = FileSystemLoader(template_directory))  # tell Jinja to load template from that directory
    template = env.get_template('ScoringSheet.jinja')  # load the .jinja document template

    # fill in the template using the specified variables
    output = template.render(fleet=fleet, competitors=competitors, racetitle=racetitle)

    # output is a full HTML document in string form
    return output

def main():
    # build and run the command line parser
    parser = argparse.ArgumentParser(prog="ScoringSheet",
                                     description="Generate AYC Scoring Sheets from SailWave XML data")
    parser.add_argument('--file', help="SailWave .blw file", required=True)
    parser.add_argument('--name', help="Regatta name", required=True)
    parser.add_argument('--running', help="Connect to a running Sailwave", action=argparse.BooleanOptionalAction)
    args = parser.parse_args()

    sw = Sailwave()
    if not Sailwave.CheckVersion():
        exit(1)

    if not sw.Start(args.file, args.running):
        print('Failed to launch Sailwave')
        exit(2)

    fleets = sw.GetCompetitors()
    sw.Close()

    for fleet, competitors in fleets.items():   # for each fleet...
        html = generateScoringSheet(args.name, fleet, competitors)  # generate a scoring sheet
        with open(f"{fleet}.html", 'w') as file:# and save the sheet to a .html file with the fleet name
            file.write(html)
            print(f"Wrote {fleet}.html")

if __name__ == "__main__": 
    # calling main function 
    main() 
    