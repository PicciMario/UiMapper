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
from newTrackDialog import Ui_NewTrackDialog

class NewTrackDialog(QtGui.QDialog):

	parent = None
	
	def __init__(self, parent=None):
		QtGui.QDialog.__init__(self, parent)
		self.ui = Ui_NewTrackDialog()
		self.ui.setupUi(self)
		self.parent = parent
		
		QtCore.QObject.connect(self.ui.button_add, QtCore.SIGNAL("clicked()"), self.addButtonClicked)
		QtCore.QObject.connect(self.ui.button_cancel, QtCore.SIGNAL("clicked()"), self.cancel)


	def addButtonClicked(self):
		newTrackName = self.ui.trackName.text()

		if (len(newTrackName) == 0):
			QMessageBox.warning(self, "Error", "Point name field must not be empty")
			return		
		
		result = self.parent.addTrack(Track(newTrackName))
		
		if (result != 0):
			QMessageBox.warning(self, "Error", "Error while adding new track (maybe duplicate name?).")
			return	
		
		self.parent.updatePointsList()
		self.parent.refresh()
		self.close()
		
	def cancel(self):

		self.close()
		
class NewPointDialog(QtGui.QDialog):
	
	parent = None
	
	def __init__(self, parent=None, track = None):
		QtGui.QDialog.__init__(self, parent)
		self.ui = Ui_NewPointDialog()
		self.ui.setupUi(self)
		self.parent = parent
		self.track = track
		
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
		
		if (self.track):
			result = self.track.addPoint(Point(newPointName, newPointLat, newPointLon, newPointColor))
		else:
			result = self.parent.addPoint(Point(newPointName, newPointLat, newPointLon, newPointColor))
		
		if (result != 0):
			QMessageBox.warning(self, "Error", "Error while adding new point (maybe duplicate name?).")
			return			
		
		self.parent.updatePointsList()
		self.parent.refresh()
		
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
			return 1
		else:
			self.__pointsList.append(point)
			return 0
	
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
	
	def deletePointByID(self, pointID):
		remainingPoints = []
		for point in self.__pointsList:
			if (point.name() != pointID):
				remainingPoints.append(point)
		
		self.__pointsList = remainingPoints
	
	def visible(self):
		return self.__visible
	
	def setVisible(self, value):
		if (value == True):
			self.__visible = True
		else:
			self.__visible = False
	
	def getCenter(self):
		num = 0
		avgLat = 0
		avgLon = 0

		for point in self.__pointsList:
			num += 1
			avgLat += point.lat()
			avgLon += point.lon()
		
		avgLat = float(avgLat) / float(num)
		avgLon = float(avgLon) / float(num)

		return avgLat, avgLon

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
	
	pointsListValid = True
	
	selectionRect = None
	selectionLine = None
	selectionText = None

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
		

	def __init__(self, parent=None, zoom=None, lat=None, lon=None):
		QtGui.QMainWindow.__init__(self, parent)
		self.ui = Ui_MainWindow()
		self.ui.setupUi(self)
		
		self.points = []
		self.tracks = []

		if (zoom):
			self.ui.mapZoom.setValue(zoom)
		if (lat):
			self.ui.mapLat.setValue(lat)
		if (lon):
			self.ui.mapLon.setValue(lon)
		
		# managing upper right UI section (map initialization parameters)
		QtCore.QObject.connect(self.ui.button_rebuild, QtCore.SIGNAL("clicked()"), self.createMapButton)
		QtCore.QObject.connect(self.ui.button_center, QtCore.SIGNAL("clicked()"), self.center)
		QtCore.QObject.connect(self.ui.saveFileButton, QtCore.SIGNAL("clicked()"), self.saveToFile)
		
		# manage points list
		QtCore.QObject.connect(self.ui.button_delete_point, QtCore.SIGNAL("clicked()"), self.deleteSelectedPoint)
		QtCore.QObject.connect(self.ui.button_new_point, QtCore.SIGNAL("clicked()"), self.openNewPointWindow)
		QtCore.QObject.connect(self.ui.button_new_track, QtCore.SIGNAL("clicked()"), self.openNewTrackWindow)
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
		self.updatePointsList()

	def createMapButton(self):		
		lat = self.ui.mapLat.value()
		lon = self.ui.mapLon.value()
		zoom = self.ui.mapZoom.value()
		
		self.createMap(lat, lon, zoom)
		
		# delete previous "_center_" marker
		self.deletePointByID("_center_")
		# draw "_center_" position
		self.addPoint(Point("_center_", lat, lon, 'red'))
		
		#track = Track("prova")
		#track.addPoint(Point("one", 42.355900, 10.930400, "red"))
		#track.addPoint(Point("two", 42.355800, 10.930700, "red"))
		#track.addPoint(Point("three", 42.355600, 10.920400, "red"))
		#self.addTrack(track)
		
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
		
		progress = QProgressDialog("Downloading tiles from OpenStreetMap.org...", "Abort", 0, 12, self)
		progress.setWindowModality(Qt.WindowModal)
		progress.setMinimumDuration = 0
		
		i = 0
		tiles = []
		for deltaX in range(-1,3):
			for deltaY in range(-1,2):
			
				progress.setValue(i)
			
				tiles.append(self.getTileXY(x+deltaX, y+deltaY, zoom))
				i = i + 1
		
		progress.setValue(12);
		
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
		
		rectWidth = 2
		pen = QPen(QtCore.Qt.red, 2, QtCore.Qt.SolidLine)
		
		for point in self.points:
		
			if (point.visible() == False): continue
		
			dotX, dotY = self.gpsToXY(point.lat(), point.lon())
			
			if (dotX >= 4*256 or dotX <= 0 or dotY >= 3*256 or dotY <= 0): continue;
			
			#self.draw.ellipse(
			#	[dotX-rectWidth, dotY-rectWidth, dotX+rectWidth, dotY+rectWidth], 
			#	fill=point.color()
			#)
			
			ellipse = self.scene.addEllipse(dotX-rectWidth, dotY-rectWidth, 2*rectWidth, 2*rectWidth, pen)
			ellipse.setToolTip("%s\n%f - %f"%(point.name(), point.lat(), point.lon()))
	
		for track in self.tracks:
		
			if (track.visible() == False): continue
		
			prevX = -1
			prevY = -1
			
			for point in track.points():
				
				if (point.visible() == False): continue
			
				dotX, dotY = self.gpsToXY(point.lat(), point.lon())
				
				if (dotX >= 4*256 or dotX <= 0 or dotY >= 3*256 or dotY <= 0): continue;
				
				#self.draw.ellipse(
				#	[dotX-rectWidth, dotY-rectWidth, dotX+rectWidth, dotY+rectWidth], 
				#	fill=point.color()
				#)
				
				ellipse = self.scene.addEllipse(dotX-rectWidth, dotY-rectWidth, 2*rectWidth, 2*rectWidth, pen)
				ellipse.setToolTip("Track: %s\nPoint: %s\nLat: %f - Lon: %f"%(track.name(), point.name(), point.lat(), point.lon()))
				
				if (prevX != -1 and prevY != -1):
					self.scene.addLine(prevX, prevY, dotX, dotY)
				
				prevX = dotX
				prevY = dotY
				

		# draw image geometrical center
		# self.draw.ellipse([self.imgWidth/2-3, self.imgHeight/2-3, self.imgWidth/2+3, self.imgHeight/2+3], fill="green")

	def drawMapOnCanvas(self):	
		self.imgQ = ImageQt.ImageQt(self.completeMap)  # we need to hold reference to imgQ, or it will crash
		pixMap = QtGui.QPixmap.fromImage(self.imgQ)
		#pixMap = pixMap.scaled(100, 100, QtCore.Qt.KeepAspectRatio)
	
		self.scene = QScene(self)
		self.scene.addPixmap( pixMap )
		self.ui.graphicsView.setScene(self.scene)

	def refresh(self):
	
		# creates a scene with the downloaded map
		# and draws it on the UI
		self.drawMapOnCanvas()
	
		# recreates points and tracks on the scene
		self.recreateDrawings()
		
		# ir required updates points listing
		if (self.pointsListValid == False):
			self.updatePointsList()
			self.pointsListValid = True

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
								self.pointsListValid = False
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
							self.pointsListValid = False
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
							self.pointsListValid = False
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
		
		try:
			if (self.selectionRect):
				self.scene.removeItem(self.selectionRect)
		except:
			pass

		try:
			if (self.selectionLine):
				self.scene.removeItem(self.selectionLine)
		except:
			pass

		try:
			if (self.selectionText):
				self.scene.removeItem(self.selectionText)
		except:
			pass
	
		pen = QPen(QtCore.Qt.black, 2, QtCore.Qt.SolidLine)
		self.selectionRect = self.scene.addRect(dotX-7, dotY-7, 14, 14, pen)
		self.selectionLine = self.scene.addLine(dotX+7, dotY-7, dotX+5+20, dotY-5-20, pen)
		self.selectionText = self.scene.addSimpleText("%.5f, %.5f"%(lat, lon))
		self.selectionText.setPos(dotX+5+24, dotY-5-20-10)

	def centerOnSelectedPoint(self):
		currentSelectedPoint = self.ui.pointsList.currentItem()
		
		if (currentSelectedPoint):
			if (currentSelectedPoint.childCount() == 0):
				try:
					pointLat = float(currentSelectedPoint.text(1))		
					pointLon = float(currentSelectedPoint.text(2))	

					dotX, dotY = self.gpsToXY(pointLat, pointLon)
					if (dotX >= 4*256 or dotX <= 0 or dotY >= 3*256 or dotY <= 0): 
						pass
					else:
						self.centerCoords(pointLat, pointLon)
				except:
					pass
			
	def deleteSelectedPoint(self):
		currentSelectedPoint = self.ui.pointsList.currentItem()
		if (currentSelectedPoint):
		
			# a point
			if (currentSelectedPoint.childCount() == 0 and currentSelectedPoint.text(1) != None):
				
				pointID = currentSelectedPoint.text(0)
				
				# a point in a track
				if (currentSelectedPoint.parent()):				
					track = self.getTrackByID(currentSelectedPoint.parent().text(0))
					if (track):	
						track.deletePointByID(pointID)						
				
				# a root point
				else:		
					remainingPoints = []
					for point in self.points:
						if (point.name() != pointID):
							remainingPoints.append(point)
					
					self.points = remainingPoints
			
				self.pointsListValid = False
				self.refresh()
			
			# maybe a track?
			else:
				trackID = currentSelectedPoint.text(0)
				
				remainingTracks = []
				for track in self.tracks:
					if (track.name() != trackID):
						remainingTracks.append(track)
				
				self.tracks = remainingTracks
			
				self.pointsListValid = False
				self.refresh()					

	def clear(self):		
		#print "Clearing drawings over image..."
		del self.completeMap
		del self.draw
		self.completeMap = self.backupMap.copy()
		self.draw = ImageDraw.Draw(self.completeMap)	
	
	def saveToFile(self, filename = None):
		if (filename == None):
			filename = QtGui.QFileDialog.getSaveFileName(None, "Nome immagine", "", "Image Files (*.png)")
			filename = filename[0]

		if (len(filename) == 0):
			return
		
		outputimg = QtGui.QPixmap(self.ui.graphicsView.viewport().width(), self.ui.graphicsView.viewport().height())
		painter = QtGui.QPainter(outputimg)
		
		targetrect = sourcerect = self.ui.graphicsView.viewport().rect()
		
		self.ui.graphicsView.render(painter, targetrect, sourcerect)
		outputimg.save(filename, "PNG")

		painter.end()	
	
	
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
			trackNode.setToolTip(0, "Points in track: %i"%len(track.points()))
			
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
	
		track = None

		# if a track is currently selected, add it the new point
		currentSelectedPoint = self.ui.pointsList.currentItem()
		
		if (currentSelectedPoint):
			# a point (not a track)
			if (currentSelectedPoint.childCount() > 0 or currentSelectedPoint.text(1) != None):				
				track = self.getTrackByID(currentSelectedPoint.text(0))

		self.newPointWindow = NewPointDialog(self, track)
		
		self.newPointWindow.exec_()

	def openNewTrackWindow(self):
		self.newTrackWindow = NewTrackDialog(self)
		self.newTrackWindow.exec_()

	def addPoint(self, point):
		if (self.getPointByID(point.name())):
			return 1
		else:
			self.points.append(point)
			self.pointsListValid = False
			return 0

	def addTrack(self, track):
		if (self.getTrackByID(track.name())):
			return 1
		else:
			self.tracks.append(track)
			self.pointsListValid = False
			return 0
	
	def deletePointByID(self, id):
		survivingPoints = []
		
		for point in self.points:
			if (point.name() != id):
				survivingPoints.append(point)

		self.points = survivingPoints
		self.pointsListValid = False
	
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