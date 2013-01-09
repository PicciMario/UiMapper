import sys, sqlite3, time, datetime, os, math, cStringIO
from PySide import QtCore, QtGui
from PySide.QtCore import *
from PySide.QtGui import *

import socket
socket.setdefaulttimeout(5)
import urllib, urllib2

import PySide
sys.modules['PyQt4'] = PySide

import PIL
from PIL import Image as PILImage
from PIL import ImageDraw
#from PIL.ImageQt import ImageQt
from PIL import ImageQt

from mainUI import Ui_MainWindow
from newPointDialog import Ui_NewPointDialog


class NewPointDialog(QtGui.QDialog):
	
	parent = None
	
	def __init__(self, parent=None):
		QtGui.QDialog.__init__(self, parent)
		self.ui = Ui_NewPointDialog()
		self.ui.setupUi(self)
		self.parent = parent
		
		QtCore.QObject.connect(self.ui.button_add, QtCore.SIGNAL("clicked()"), self.addButtonClicked)
		QtCore.QObject.connect(self.ui.button_cancel, QtCore.SIGNAL("clicked()"), self.cancel)
	
	def addButtonClicked(self):
		newPointLat = self.ui.pointLat.value()
		newPointLon = self.ui.pointLon.value()
		newPointName = self.ui.pointName.text()
		newPointColor = self.ui.pointColor.currentText()
		
		if (len(newPointName) == 0):
			QMessageBox.warning(self, "Error", "Point name field must not be empty")
			return
		
		self.parent.addPoint(Point(newPointName, newPointLat, newPointLon, newPointColor))
		self.parent.drawMapOnCanvas()
		self.parent.updatePointsList()
		
		self.close()
	
	def cancel(self):
		self.close()


class QScene(QtGui.QGraphicsScene):

	parent = None

	def __init__(self, parent, *args, **kwds):
		QtGui.QGraphicsScene.__init__(self, *args, **kwds)
		self.parent = parent
		
	def mouseDoubleClickEvent(self, ev):
		self.parent.doubleClickOnGraphics(ev)


class Track():
	
	__pointsList = []
	__name = ""
	__visible = True
	
	def __init__(self, name):
		self.__name = name
		self.__pointsList = []
	
	def addPoint(self, point):
		if (self.getPointByID(point.name())):
			print "Point name already in use"
		else:
			self.__pointsList.append(point)
	
	def points(self):
		return self.__pointsList
	
	def name(self):
		return self.__name
	
	def __str__(self):
		
		ritorno = ""
		
		ritorno = ritorno + "Track name: %s\n"%self.__name
		for point in self.__pointsList:
			ritorno = ritorno + "- " + point.__str__() + "\n"
		
		return ritorno
		
	def getPointByID(self, id):
		for point in self.__pointsList:
			if (point.name() == id):
				return point
		return None
	
	def visible(self):
		return self.__visible
	
	def setVisible(self, value):
		if (value == True):
			self.__visible = True
		else:
			self.__visible = False


class Point():

	__pointID = ""
	__lat = 0
	__lon = 0
	__color = "black"
	
	__visible = True
	
	def __init__(self, name, lat, lon, color):
		self.__pointID = name
		self.__lat = lat
		self.__lon = lon
		self.__color = color
	
	def name(self):
		return self.__pointID
	
	def lat(self):
		return self.__lat
	
	def lon(self):
		return self.__lon
	
	def color(self):
		return self.__color
	
	def __str__(self):
		return "%s: %.3f %.3f"%(self.__pointID, self.__lat, self.__lon)
	
	def visible(self):
		return self.__visible
	
	def setVisible(self, value):
		if (value == True):
			self.__visible = True
		else:
			self.__visible = False


class Mapper(QtGui.QMainWindow):
	
	# working map objects by createMap
	draw = None			# imageDraw, to draw decorations on
	completeMap = None	# PIL Image
	
	# copy of the map image (by createMap)
	backupMap = None
	
	# map objects for drawing on QGraphicsView (by drawMapOnCanvas)
	imgQ = None		# QtGui.QPixmap
	scene = None	# QtGui.QGraphicsScene
	
	# sizes of map image (by createMap)
	imgHeight = 0
	imgWidth = 0
	mapWidthMeters = 0
	pixelsPerMeter = 0
	#upperLeftLat = upperLeftLon = 0
	#upperRightLat = upperRightLon = 0
	#bottomLeftLat = bottomLeftLon = 0
	mapCenterX = mapCenterY = 0
	
	upperLeftX = 0
	upperleftY = 0
	actualZoom = 0
	
	# points database
	points = []
	tracks = []

	# Converts a gps coordinate couple into the xy coordinate of
	# the OSM tile it is on.
	def deg2num(self, lat_deg, lon_deg, zoom):
		lat_rad = math.radians(lat_deg)
		n = 2.0 ** zoom
		xtile = float((lon_deg + 180.0) / 360.0 * n)
		ytile = float((1.0 - math.log(math.tan(lat_rad) + (1 / math.cos(lat_rad))) / math.pi) / 2.0 * n)
		return (xtile, ytile)

	# Calculates the NW gps coordinate of an xy OSM tile
	def num2deg(self, xtile, ytile, zoom):
		n = 2.0 ** zoom
		lon_deg = xtile / n * 360.0 - 180.0
		lat_rad = math.atan(math.sinh(math.pi * (1 - 2 * ytile / n)))
		lat_deg = math.degrees(lat_rad)
		return (lat_deg, lon_deg)

	# Calculates the position in pixel on the current drawn map
	# of the passed coordinates
	def gpsToXY(self, lat, lon):
		xPos, yPos = self.deg2num(lat, lon, self.actualZoom)
		tileWidth = tileHeight = 256.0
		dotX = (xPos - float(self.upperLeftX))*tileWidth
		dotY = (yPos - float(self.upperLeftY))*tileHeight
		return dotX, dotY
	
	# Calculates the gps coordinates of the pixel xy in the 
	# currently drawn map
	def xyToGps(self, x, y):
		xPos = x / 256.0 + self.upperLeftX
		yPos = y / 256.0 + self.upperLeftY	
		lat, lon = self.num2deg(xPos, yPos, self.actualZoom)
		return lat, lon

	# Returns the OSM tile containing the passed gps
	# coordinate
	def getTile(self, lat, lon, zoom, xshift=0, yshift=0):
		(x, y) = self.deg2num(lat, lon, zoom)		
		return self.getTileXY(x, y, zoom, xshift, yshift)
	
	# Returns the OSM tile indicated by the xy coordinates
	# - if the tile was already cached on disk, serve the cached copy
	# - if the tile was not cached, download it
	# - if can't download, return a black square
	def getTileXY(self, x, y, zoom, xshift=0, yshift=0):
		imUrl = "http://tile.openstreetmap.org/%i/%i/%i.png"%(zoom, x+xshift, y+yshift)

		fileName = "%i-%i-%i.png"%(zoom, x+xshift, y+yshift)
		fileName = os.path.join("tmp", fileName)

		if os.path.exists(fileName):
			
			# open existing file
			dataSource = open(fileName, "rb")
			dataSourceContent = dataSource.read()
			imRead = cStringIO.StringIO(dataSourceContent)
			dataSource.close()
			
		else:
			
			try:
				# retrieve tile from tile server
				print "Downloading tile..."
				dataSource = urllib2.urlopen(imUrl)
				dataSourceContent = dataSource.read()
				imRead = cStringIO.StringIO(dataSourceContent)
				dataSource.close()
			except Exception as errorDesc:
				print "Unexpected error while downloading tile from %s: %s"%(imUrl, errorDesc)
				return PIL.Image.new('RGBA', (256, 256), (0, 0, 0, 0)) 
			
			# cache tile for future use
			cacheImage = open(fileName, "wb")
			cacheImage.write(dataSourceContent)
			cacheImage.close()
		
		return PIL.Image.open(imRead)
		

	def __init__(self, parent=None):
		QtGui.QMainWindow.__init__(self, parent)
		self.ui = Ui_MainWindow()
		self.ui.setupUi(self)
		
		self.points = []
		self.tracks = []		
		
		# managing upper right UI section (map initialization parameters)
		QtCore.QObject.connect(self.ui.button_rebuild, QtCore.SIGNAL("clicked()"), self.createMapButton)
		QtCore.QObject.connect(self.ui.button_center, QtCore.SIGNAL("clicked()"), self.center)
		
		# manage points list
		QtCore.QObject.connect(self.ui.button_delete_point, QtCore.SIGNAL("clicked()"), self.deleteSelectedPoint)
		QtCore.QObject.connect(self.ui.button_new_point, QtCore.SIGNAL("clicked()"), self.openNewPointWindow)
		QtCore.QObject.connect(self.ui.pointsList, QtCore.SIGNAL("itemSelectionChanged()"), self.centerOnSelectedPoint)	
		QtCore.QObject.connect(self.ui.pointsList, QtCore.SIGNAL("itemClicked(QTreeWidgetItem*,int)"), self.itemChangedOnPointsList)	

		self.ui.pointsList.setColumnWidth(0, 100)
		self.ui.pointsList.setColumnWidth(1, 80)
		self.ui.pointsList.setColumnWidth(2, 80)
		self.ui.pointsList.setColumnWidth(3, 30)
		
		# manage zoom buttons
		QtCore.QObject.connect(self.ui.map_zoom_down, QtCore.SIGNAL("clicked()"), self.zoomDown)
		QtCore.QObject.connect(self.ui.map_zoom_up, QtCore.SIGNAL("clicked()"), self.zoomUp)
		
		QtCore.QObject.connect(self, QtCore.SIGNAL("centerUI()"), self.center)
		
		# triggers first map redraw (with default 
		# position and zoom, as set by UI)
		self.createMapButton()

	def createMapButton(self):		
		lat = self.ui.mapLat.value()
		lon = self.ui.mapLon.value()
		zoom = self.ui.mapZoom.value()
		
		self.createMap(lat, lon, zoom)
		
		# delete previous "_center_" marker
		self.deletePointByID("_center_")
		# draw "_center_" position
		self.addPoint(Point("_center_", lat, lon, 'red'))
		
		track = Track("prova")
		track.addPoint(Point("one", 42.355900, 10.930400, "red"))
		track.addPoint(Point("two", 42.355800, 10.930700, "red"))
		track.addPoint(Point("three", 42.355600, 10.920400, "red"))
		self.addTrack(track)
		
		self.refresh()

	def createMap(self, lat, lon, zoom):
		x, y = self.deg2num(lat, lon, zoom)
		self.createMapXY(x, y, zoom)
		self.mapCenterX, self.mapCenterY = self.gpsToXY(lat, lon)
	
	def createMapXY(self, x, y, zoom):
		# salvataggio parametri mappa
		self.upperLeftX = int(x-1)
		self.upperLeftY = int(y-1)
		self.actualZoom = zoom
		
		#centerLat, centerLon = self.num2deg(x+1, y+0.5, zoom)
		#print "Centro geometrico mappa: %.3f, %.3f"%(centerLat, centerLon)

		# limiti mappa (in radianti) per calcolo larghezza
		upperLeftLat, upperLeftLon = self.num2deg(x-1, y-1, zoom)
		upperLeftLatRad = math.radians(upperLeftLat)
		upperLeftLonRad = math.radians(upperLeftLon)
		
		upperRightLat, upperRightLon = self.num2deg(x+3, y-1, zoom)
		upperRightLatRad = math.radians(upperRightLat)
		upperRightLonRad = math.radians(upperRightLon)
		
		# calcolo larghezza mappa in metri
		e = math.acos(math.sin(upperLeftLatRad)*math.sin(upperRightLatRad) + math.cos(upperLeftLatRad)*math.cos(upperRightLatRad)*math.cos(upperRightLonRad-upperLeftLonRad))
		self.mapWidthMeters =  e*6378.137*1000
		self.ui.map_width.setText("%.2f Km"%(self.mapWidthMeters/1000.0))
	
		# recupero tiles da openstreetmap
		self.ui.statusbar.showMessage("Downloading tiles from OpenStreetMap.org...")
		
		tiles = []
		for deltaX in range(-1,3):
			for deltaY in range(-1,2):
				tiles.append(self.getTileXY(x+deltaX, y+deltaY, zoom))
		
		self.ui.statusbar.showMessage("Tiles downloaded from OpenStreetMap.org")
		
		# creazione immagine contenitore
		biggerIm = PIL.Image.new("RGB", (256*4,256*3))
		
		# aggiunta tiles al contenitore
		row = 0
		col = 0
		for tile in tiles:
			biggerIm.paste(tile, (256*col, 256*row))
			row = row + 1
			if (row>2):
				row = 0
				col = col + 1	

		# oggetto su cui disegnare
		self.draw = ImageDraw.Draw(biggerIm)
		self.completeMap = biggerIm
		
		self.backupMap = biggerIm.copy()
	
		# salvataggio informazioni mappa
		self.imgWidth, self.imgHeight = biggerIm.size 
		if (self.mapWidthMeters != 0):
			self.pixelsPerMeter = float(self.imgWidth) / float(self.mapWidthMeters)
			self.ui.map_resolution.setText("%.2f m/px"%(1.0 / self.pixelsPerMeter))

	def recreateDrawings(self):
		self.clear()
		
		for point in self.points:
		
			if (point.visible() == False): continue
		
			dotX, dotY = self.gpsToXY(point.lat(), point.lon())
			rectWidth = 3
			
			self.draw.ellipse(
				[dotX-rectWidth, dotY-rectWidth, dotX+rectWidth, dotY+rectWidth], 
				fill=point.color()
			)

		for track in self.tracks:
		
			if (track.visible() == False): continue
		
			coordVector = []
			
			for point in track.points():
				
				if (point.visible() == False): continue
			
				dotX, dotY = self.gpsToXY(point.lat(), point.lon())
				rectWidth = 3
				
				self.draw.ellipse(
					[dotX-rectWidth, dotY-rectWidth, dotX+rectWidth, dotY+rectWidth], 
					fill=point.color()
				)
				
				coordVector.append(dotX)
				coordVector.append(dotY)
			
			self.draw.line(coordVector, fill="black")

		# draw image geometrical center
		# self.draw.ellipse([self.imgWidth/2-3, self.imgHeight/2-3, self.imgWidth/2+3, self.imgHeight/2+3], fill="green")

	def drawMapOnCanvas(self):	
		self.imgQ = ImageQt.ImageQt(self.completeMap)  # we need to hold reference to imgQ, or it will crash
		pixMap = QtGui.QPixmap.fromImage(self.imgQ)
		#pixMap = pixMap.scaled(100, 100, QtCore.Qt.KeepAspectRatio)
	
		#self.scene = QtGui.QGraphicsScene()
		self.scene = QScene(self)
		#self.scene.addPixmap( QtGui.QPixmap(ImageQt.ImageQt(self.completeMap)) )
		self.scene.addPixmap( pixMap )
		self.ui.graphicsView.setScene(self.scene)

	def refresh(self):
		# recovers original downloaded map (built from OSM tiles)
		# and on it recreates points and tracks
		self.recreateDrawings()
		
		# draws map+points+tracks on canvas
		self.drawMapOnCanvas()
		
		# updates points listing
		self.updatePointsList()

	def itemChangedOnPointsList(self, item, column):
		# checks just status of column 3 (visible flag)
		if (column != 3): return
		if (item):
			nodeName = item.text(0)
			
			# not a track
			if (item.childCount() == 0): 
			
				# a point belonging to a track
				if (item.parent()):
				
					trackItem = item.parent()
					trackName = trackItem.text(0)
					
					track = self.getTrackByID(trackName)
					
					if (track):
						
						point = track.getPointByID(nodeName)
						
						if (point):
							
							actualState = point.visible()
							newState = item.checkState(3)
							if (newState == Qt.Checked):
								newState = True
							else:
								newState = False
							
							if (newState != actualState):
								point.setVisible(newState)
								self.refresh()
					
				# a point not belonging to a track
				else:
					point = self.getPointByID(nodeName)
					
					if (point):
						
						actualState = point.visible()
						newState = item.checkState(3)
						if (newState == Qt.Checked):
							newState = True
						else:
							newState = False
						
						if (newState != actualState):
							point.setVisible(newState)
							self.refresh()
			
			# a track
			else:	
				track = self.getTrackByID(nodeName)
				
				if (track):

						actualState = track.visible()
						newState = item.checkState(3)
						if (newState == Qt.Checked):
							newState = True
						else:
							newState = False
						
						if (newState != actualState):
							track.setVisible(newState)
							self.refresh()				
	
	def zoomDown(self):
		if (self.ui.mapZoom.value() < 17):
			self.ui.mapZoom.setValue(self.ui.mapZoom.value()+1)
			self.createMapButton()
	def zoomUp(self):
		if (self.ui.mapZoom.value() > 1):
			self.ui.mapZoom.setValue(self.ui.mapZoom.value()-1)
			self.createMapButton()
	
	# performed when a point is doubleclicked in the map
	# sets the point coordinates in the upper right fields in the ui, 
	# and rebuilds the map
	def doubleClickOnGraphics(self, event):
		
		newX = event.scenePos().x()
		newY = event.scenePos().y()
		lat, lon = self.xyToGps(newX, newY)
		
		self.ui.mapLat.setValue(lat)
		self.ui.mapLon.setValue(lon)
		self.createMapButton()
		
		self.center()
	
	
	def center(self):
		self.ui.graphicsView.centerOn(QPointF(self.mapCenterX, self.mapCenterY))
		print "centering on %i x %i"%(self.mapCenterX, self.mapCenterY)
	
	def centerCoords(self, lat, lon):
		dotX, dotY = self.gpsToXY(lat, lon)
		self.ui.graphicsView.centerOn(QPointF(dotX, dotY))

	def centerOnSelectedPoint(self):
		currentSelectedPoint = self.ui.pointsList.currentItem()
		
		if (currentSelectedPoint):
			if (currentSelectedPoint.childCount() == 0):
				pointLat = float(currentSelectedPoint.text(1))		
				pointLon = float(currentSelectedPoint.text(2))		
				
				self.centerCoords(pointLat, pointLon)
			
	def deleteSelectedPoint(self):
		currentSelectedPoint = self.ui.pointsList.currentItem()
		if (currentSelectedPoint):
			pointID = currentSelectedPoint.text(0)
			
			remainingPoints = []
			for point in self.points:
				if (point.name() != pointID):
					remainingPoints.append(point)
			
			self.points = remainingPoints
			
			self.refresh()		

	def clear(self):		
		#print "Clearing drawings over image..."
		del self.completeMap
		del self.draw
		self.completeMap = self.backupMap.copy()
		self.draw = ImageDraw.Draw(self.completeMap)	
	
	def updatePointsList(self):	
		self.ui.pointsList.clear()
		
		first = True
		firstElement = None

		for point in self.points:
		
 			newElement = QtGui.QTreeWidgetItem(None)
			newElement.setText(0, point.name())
			newElement.setText(1, "%.8f"%point.lat())
			newElement.setText(2, "%.8f"%point.lon())
			
			if (point.visible()):
				newElement.setCheckState(3, Qt.Checked)
			else:
				newElement.setCheckState(3, Qt.Unchecked)
			
			self.ui.pointsList.addTopLevelItem(newElement)
			
			if (first == True):	
				firstElement = newElement
				first = False
		
		for track in self.tracks:
			
			trackName = track.name()
			trackNode = QtGui.QTreeWidgetItem(None)
			trackNode.setText(0, trackName)
			
			if (track.visible() == False):
				trackNode.setCheckState(3, Qt.Unchecked)
			else:
				trackNode.setCheckState(3, Qt.Checked)
			
			self.ui.pointsList.addTopLevelItem(trackNode)
			
			for point in track.points():
			
				newElement = QtGui.QTreeWidgetItem(trackNode)
				newElement.setText(0, point.name())
				newElement.setText(1, "%.8f"%point.lat())
				newElement.setText(2, "%.8f"%point.lon())

				if (point.visible()):
					newElement.setCheckState(3, Qt.Checked)
				else:
					newElement.setCheckState(3, Qt.Unchecked)
				
				self.ui.pointsList.addTopLevelItem(newElement)				
		
		if (firstElement):
			self.ui.pointsList.setCurrentItem(firstElement)	
	

	def openNewPointWindow(self):
		self.newPointWindow = NewPointDialog(self)
		self.newPointWindow.exec_()

	def addPoint(self, point):
		if (self.getPointByID(point.name())):
			print "Point name already in use"
		else:
			self.points.append(point)

	def addTrack(self, track):
		if (self.getTrackByID(track.name())):
			print "Track name already in use"
		else:
			self.tracks.append(track)
	
	def deletePointByID(self, id):
		survivingPoints = []
		
		for point in self.points:
			if (point.name() != id):
				survivingPoints.append(point)

		self.points = survivingPoints
	
	def getTrackByID(self, id):	
		for track in self.tracks:
			if (track.name() == id):
				return track
		
		return None

	def getPointByID(self, id):	
		for point in self.points:
			if (point.name() == id):
				return point
		
		return None

if __name__ == "__main__":
    app = QtGui.QApplication(sys.argv)
    mapper = Mapper()
    mapper.show()
    sys.exit(app.exec_())