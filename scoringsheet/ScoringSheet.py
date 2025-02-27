# Need this first: python -m pip install jinja2
import jinja2 # code to format a .jinja file into an output document
import xml.etree.ElementTree as ET  # XML parser
import argparse # command line argument parser
import os # filename and pathname functions
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

# Definition of a competitor, using SailWave concepts
class Competitor:
    def __init__(self, helmname, boat, sailno, altsailno):
        self.helmname = helmname
        self.boat = boat
        self.sailno = sailno
        self.altsailno = altsailno

# Parse the SailWave XML file to extract out the <competitors> list
def parseXML(xmlfile): 
    tree = ET.parse(xmlfile)   
    root = tree.getroot() 
    competitors = root.find('competitors')
    return competitors

# Parse the <competitors> list into a dictionary of {fleetname, competitors}
def parseSailwave(competitors):
    fleets = {}
    for competitor in competitors:
        # Each <competitor> in the XML has a bunch of elements under it.
        # Gather the ones we are interested in.
        compboat = competitor.find('compboat').text.strip()
        compsailno = competitor.find('compsailno').text.strip()
        compaltsailno = competitor.find('compaltsailno').text.strip()
        compfleet = competitor.find('compfleet').text.strip()
        comphelmname = competitor.find('comphelmname').text.strip()
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
    parser.add_argument('--xml', help="SailWave XML file", required=True)
    parser.add_argument('--name', help="Regatta name", required=True)
    args = parser.parse_args()

    all_competitors = parseXML(args.xml)        # read the Sailwave XML
    fleets = parseSailwave(all_competitors)     # parse out the competitor list into {fleet, competitors} dictionary
    for fleet, competitors in fleets.items():   # for each fleet...
        html = generateScoringSheet(args.name, fleet, competitors)  # generate a scoring sheet
        with open(f"{fleet}.html", 'w') as file:# and save the sheet to a .html file with the fleet name
            file.write(html)
            print(f"Wrote {fleet}.html")

if __name__ == "__main__": 
    # calling main function 
    main() 
    