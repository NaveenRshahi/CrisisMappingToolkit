# Libraries built in to Google Apps Engine
import sys
import os
import cgi
import webapp2
import urllib2
import ee
import config
import json

# Libraries that we need to provide ourselves in the libs folder

rootdir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.join(rootdir, 'libs'))

from bs4 import BeautifulSoup




# TODO: Move this!
STORAGE_URL = 'http://byss.arc.nasa.gov/smcmich1/cmt_detections/'    

feed_url = STORAGE_URL + 'daily_flood_detect_feed.kml'

# Go ahead and load the HTML files for later use.

with open('index.html', 'r') as f:
    PAGE_HTML = f.read()
with open('map.html', 'r') as f:
    MAP_HTML = f.read()



def renderHtml(html, pairList):
    '''Simple alternative to html template rendering software'''

    for pair in pairList:
        html = html.replace(pair[0], pair[1])
    return html



def fetchDateList(datesOnly=False):
    '''Fetches the list of available dates'''
    
    dateList = []
    parsedIndexPage = BeautifulSoup(urllib2.urlopen((STORAGE_URL)).read(), 'html.parser')
    
    for line in parsedIndexPage.findAll('a'):
        dateString = line.string
        
        if datesOnly:
            dateList.append(dateString)
            continue

        # Else look through each page so we can make date__location pairs.
        subUrl = STORAGE_URL + dateString
        
        try:
            parsedSubPage = BeautifulSoup(urllib2.urlopen((subUrl)).read(), 'html.parser')
            
            for line in parsedSubPage.findAll('a'):
                kmlName = line.string
                info = extractInfoFromKmlUrl(kmlName)
                
                # Store combined date/location string.
                displayString = dateString +'__'+ info['location']
                dateList.append(displayString)
        except:
            pass # Ignore pages that we fail to parse

    return dateList

def getKmlUrlsForKey(key):
    '''Fetches all the kml files from a given date.
       If the dateString includes a location, only fetch the matching URL.
       Otherwise return all URLs for that date.'''

    # The key contains the date and optionally the location
    if '__' in key:
        parts = key.split('__')
        dateString = parts[0]
        location   = parts[1]
    else:
        dateString = key
        location   = None

    kmlList = []
    subUrl = STORAGE_URL + dateString
    parsedSubPage = BeautifulSoup(urllib2.urlopen((subUrl)).read(), 'html.parser')
      
    for line in parsedSubPage.findAll('a'):
        kmlName = line.string
        fullUrl = os.path.join(subUrl, kmlName)
        
        # If this location matches a provided location, just return this URL.
        if location and (location in kmlName):
            return [fullUrl]
        else:
            kmlList.append(fullUrl)

    return kmlList


def extractInfoFromKmlUrl(url):
    '''Extract the information encoded in the KML filename into a dictionary.'''
    
    # Format is: 'STUFF/results_location_SENSORS_%05f_%05f.kml'

    # Get just the kml name    
    rslash = url.rfind('/')
    if rslash:
        filename = url[rslash+1:]
    else:
        filename = url

    # Split up the kml name
    parts     = filename.split('_')
    parts[-1] = parts[-1].replace('.kml','')

    location = parts[1]
    if len(parts) == 5:
        sensors = parts[2]
    else:
        sensors = ''
    lon = float(parts[-2])
    lat = float(parts[-1])
    
    # Pack the results into a dictionary
    return {'location':location, 'sensors':sensors, 'lon':lon, 'lat':lat}


def expandSensorsList(sensors):
    '''Expand the abbreviated sensor list to full sensor names'''
    
    string = ''
    pairs = [('Modis', 'M'), ('Landsat', 'L'), ('Sentinel-1', 'S')]
    for pair in pairs:
        if pair[1] in sensors:
            string += (' ' + pair[0])
    if not string:
        string = 'Error: Sensor list "'+sensors+'" not parsed!'
    return string



class GetMapData(webapp2.RequestHandler):
    """Retrieves EE data on request."""

    def get(self):

        ee.Initialize(config.EE_CREDENTIALS)
        
        layers = [] # We will fill this up with EE layer information

        # Use the MCD12 land-cover as training data.
        modis_landcover = ee.Image('MCD12Q1/MCD12Q1_005_2001_01_01').select('Land_Cover_Type_1')

        # A pallete to use for visualizing landcover images.
        modis_landcover_palette = ','.join([
            'aec3d4',  # water
            '152106', '225129', '369b47', '30eb5b', '387242',  # forest
            '6a2325', 'c3aa69', 'b76031', 'd9903d', '91af40',  # shrub, grass and
                                                               # savanah
            '111149',  # wetlands
            '8dc33b',  # croplands
            'cc0013',  # urban
            '6ca80d',  # crop mosaic
            'd7cdcc',  # snow and ice
            'f7e084',  # barren
            '6f6f6f'   # tundra
        ])

        # A set of visualization parameters using the landcover palette.
        modis_landcover_visualization_options = {
            'palette': modis_landcover_palette,
            'min': 0,
            'max': 17,
            'format': 'png'
        }

        # Add the MODIS landcover image.
        modis_landcover_visualization = modis_landcover.getMapId(modis_landcover_visualization_options)
        layers.append({
            'mapid': modis_landcover_visualization['mapid'],
            'label': 'MODIS landcover',
            'token': modis_landcover_visualization['token']
        })

        # Add the Landsat composite, visualizing just the [30, 20, 10] bands.
        landsat_composite = ee.Image('L7_TOA_1YEAR_2000')
        landsat_composite_visualization = landsat_composite.getMapId({
            'min': 0,
            'max': 100,
            'bands': ','.join(['30', '20', '10'])
        })
        layers.append({
            'mapid': landsat_composite_visualization['mapid'],
            'label': 'Landsat composite',
            'token': landsat_composite_visualization['token']
        })

        text = json.dumps(layers)
        print text
        self.response.out.write(text)



class MainPage(webapp2.RequestHandler):
    '''The splash page that the user sees when they access the site'''

    def get(self):

        # Grab all dates where data is available
        self._dateList = fetchDateList()

        # Build the list of date options
        optionText = ''
        for dateString in self._dateList:
            optionText += '<option>'+dateString.replace('_',' ')+'</option>'
        
        # Insert the option section, leave the output section empty.
        self._htmlText = renderHtml(PAGE_HTML, [('[OPTION_SECTION]', optionText), 
                                                ('[OUTPUT_SECTION]', ''),
                                                ('[FEED_URL]', feed_url)])
        
        # Write the output    
        self.response.write(self._htmlText)


class MapPage(webapp2.RequestHandler):
    '''Similar to the main page, but with a map displayed.'''

    def post(self):

        # Init demo ee image
        ee.Initialize(config.EE_CREDENTIALS)
        mapid = ee.Image('srtm90_v4').getMapId({'min': 0, 'max': 1000})

        # Grab all dates where data is available
        self._dateList = fetchDateList()
        
        # Build the list of date options
        optionText = ''
        for dateString in self._dateList:
            optionText += '<option>'+dateString.replace('_',' ')+'</option>'

        # Insert the options section
        self._htmlText = renderHtml(PAGE_HTML, [('[OPTION_SECTION]', optionText),
                          ('[API_KEY]', 'AIzaSyAlcB6oaJeUdTz3I97cL47tFLIQfSu4j58'),
                          ('[FEED_URL]', feed_url)])

        # Fetch user selection    
        dateLocString = self.request.get('date_select', 'default_date!')

        ## This should only return one URL, provided that the location is included in dateLocString
        try:
            kmlUrls = getKmlUrlsForKey(dateLocString.replace(' ', '__'))
        except:
            kmlUrls = None
        
        if not kmlUrls:
            #newText = 'No KML files were found for this date!'
            newText = dateLocString 
        else:
            # Prepare the map HTML with the data we found
            kmlUrl     = kmlUrls[0]
            info       = extractInfoFromKmlUrl(kmlUrl)
            sensorList = expandSensorsList(info['sensors'])
            newText = renderHtml(MAP_HTML, [('[EE_MAPID]',    mapid['mapid']),
                                            ('[EE_TOKEN]',    mapid['token']),
                                            ('[MAP_TITLE]',   dateLocString),
                                            ('[KML_URL]',     kmlUrl), 
                                            ('[SENSOR_LIST]', sensorList), 
                                            ('[LAT]',         str(info['lat'])), 
                                            ('[LON]',         str(info['lon']))])

        #newText = 'You selected: <pre>'+ cgi.escape(date) +'</pre>'
        #newText = MAP_HTML
        
        # Fill in the output section
        text = renderHtml(self._htmlText, [('[OUTPUT_SECTION]', newText)])
        
        # Write the output
        self.response.write(text)

app = webapp2.WSGIApplication([
    ('/',         MainPage),
    ('/selected', MapPage),
    ('/getmapdata', GetMapData)
], debug=True)


