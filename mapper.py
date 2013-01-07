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
		
		self.parent.addPoint(newPointName, newPointLat, newPointLon, newPointColor)
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

	def deg2num(self, lat_deg, lon_deg, zoom):
		lat_rad = math.radians(lat_deg)
		n = 2.0 ** zoom
		xtile = float((lon_deg + 180.0) / 360.0 * n)
		ytile = float((1.0 - math.log(math.tan(lat_rad) + (1 / math.cos(lat_rad))) / math.pi) / 2.0 * n)
		return (xtile, ytile)

	def num2deg(self, xtile, ytile, zoom):
		n = 2.0 ** zoom
		lon_deg = xtile / n * 360.0 - 180.0
		lat_rad = math.atan(math.sinh(math.pi * (1 - 2 * ytile / n)))
		lat_deg = math.degrees(lat_rad)
		return (lat_deg, lon_deg)

	def getTile(self, lat, lon, zoom, xshift=0, yshift=0):

		(x, y) = self.deg2num(lat, lon, zoom)
		
		return self.getTileXY(x, y, zoom, xshift, yshift)
	
	def getTileXY(self, x, y, zoom, xshift=0, yshift=0):
	
		#print "Getting tile x: %i, y: %i, zoom: %i"%(x,y,zoom)
	
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
		
	def gpsToXY(self, lat, lon):
		
		xPos, yPos = self.deg2num(lat, lon, self.actualZoom)
		#print "xPos: %.2f, yPos: %.2f"%(xPos, yPos)
		
		#print "upperLeftX = %.2f"%(self.upperLeftX)
		
		tileWidth = tileHeight = 256.0
		dotX = (xPos - float(self.upperLeftX))*tileWidth
		dotY = (yPos - float(self.upperLeftY))*tileHeight
		
		#print "DotX = %.2f, dotY = %.2f"%(dotX, dotY)
		
		return dotX, dotY
		
	def xyToGps(self, x, y):
		xPos = x / 256.0 + self.upperLeftX
		yPos = y / 256.0 + self.upperLeftY
		
		lat, lon = self.num2deg(xPos, yPos, self.actualZoom)
		
		return lat, lon

	def __init__(self, parent=None):
		QtGui.QMainWindow.__init__(self, parent)
		self.ui = Ui_MainWindow()
		self.ui.setupUi(self)
		
		QtCore.QObject.connect(self.ui.button_rebuild, QtCore.SIGNAL("clicked()"), self.createMapButton)
		QtCore.QObject.connect(self.ui.button_center, QtCore.SIGNAL("clicked()"), self.center)
		QtCore.QObject.connect(self.ui.button_delete_point, QtCore.SIGNAL("clicked()"), self.deleteSelectedPoint)
		QtCore.QObject.connect(self.ui.pointsList, QtCore.SIGNAL("itemSelectionChanged()"), self.centerOnSelectedPoint)		
		
		QtCore.QObject.connect(self.ui.map_zoom_down, QtCore.SIGNAL("clicked()"), self.zoomDown)
		QtCore.QObject.connect(self.ui.map_zoom_up, QtCore.SIGNAL("clicked()"), self.zoomUp)
		
		QtCore.QObject.connect(self, QtCore.SIGNAL("centerUI()"), self.center)
		
		QtCore.QObject.connect(self.ui.button_new_point, QtCore.SIGNAL("clicked()"), self.openNewPointWindow)
		
		self.createMapButton()
	
	def zoomDown(self):
		if (self.ui.mapZoom.value() < 17):
			self.ui.mapZoom.setValue(self.ui.mapZoom.value()+1)
			self.createMapButton()
	def zoomUp(self):
		if (self.ui.mapZoom.value() > 1):
			self.ui.mapZoom.setValue(self.ui.mapZoom.value()-1)
			self.createMapButton()
			
	def doubleClickOnGraphics(self, event):
		
		newX = event.scenePos().x()
		newY = event.scenePos().y()
	
		#print "x: %i, y: %i"%(newX, newY)
		
		lat, lon = self.xyToGps(newX, newY)
		
		#print "new lat: %.6f, new lon: %.6f"%(lat, lon)
		
		self.ui.mapLat.setValue(lat)
		self.ui.mapLon.setValue(lon)
		self.createMapButton()
		
		self.center()
	
	def createMapButton(self):
		
		lat = self.ui.mapLat.value()
		lon = self.ui.mapLon.value()
		zoom = self.ui.mapZoom.value()
		
		self.createMap(lat, lon, zoom)
		
		# delete previous "_center_" marker
		self.deletePointByID("_center_")
		# draw "_center_" position
		self.addPoint("_center_", lat, lon, 'red')
		
		self.drawMapOnCanvas()
		self.updatePointsList()
	
	def center(self):
		self.ui.graphicsView.centerOn(QPointF(self.mapCenterX, self.mapCenterY))
		print "centering on %i x %i"%(self.mapCenterX, self.mapCenterY)
	
	def centerCoords(self, lat, lon):
		dotX, dotY = self.gpsToXY(lat, lon)
		self.ui.graphicsView.centerOn(QPointF(dotX, dotY))

	def centerOnSelectedPoint(self):
		currentSelectedPoint = self.ui.pointsList.currentItem()
		
		if (currentSelectedPoint):
			pointLat = float(currentSelectedPoint.text(1))		
			pointLon = float(currentSelectedPoint.text(2))		
			
			self.centerCoords(pointLat, pointLon)
			
	def deleteSelectedPoint(self):
		currentSelectedPoint = self.ui.pointsList.currentItem()
		if (currentSelectedPoint):
			pointID = currentSelectedPoint.text(0)
			
			remainingPoints = []
			for point in self.points:
				if (point[0] != pointID):
					remainingPoints.append(point)
			
			self.points = remainingPoints
			
			self.drawMapOnCanvas()
			self.updatePointsList()
			

	def clear(self):
		
		#print "Clearing drawings over image..."
		del self.completeMap
		del self.draw
		self.completeMap = self.backupMap.copy()
		self.draw = ImageDraw.Draw(self.completeMap)	
	
	def recreateDrawings(self):
		
		self.clear()
		
		for point in self.points:
			dotX, dotY = self.gpsToXY(point[1], point[2])
			rectWidth = 3
			
			self.draw.ellipse(
				[dotX-rectWidth, dotY-rectWidth, dotX+rectWidth, dotY+rectWidth], 
				fill=point[3]
			)			

		# draw image geometrical center
		# self.draw.ellipse([self.imgWidth/2-3, self.imgHeight/2-3, self.imgWidth/2+3, self.imgHeight/2+3], fill="green")

	def updatePointsList(self):
	
		self.ui.pointsList.clear()
		
		first = True
		firstElement = None

		for point in self.points:
		
			pointID = point[0]
			pointLat = point[1]
			pointLon = point[2]
			pointFill = point[3]
		
 			newElement = QtGui.QTreeWidgetItem(None)
			newElement.setText(0, pointID)
			newElement.setText(1, "%.8f"%pointLat)
			newElement.setText(2, "%.8f"%pointLon)
			self.ui.pointsList.addTopLevelItem(newElement)
			if (first == True):	
				firstElement = newElement
				first = False
		
		if (firstElement):
			self.ui.pointsList.setCurrentItem(firstElement)	
	
	
	
	
		
			
	
	def drawMapOnCanvas(self):
	
		self.recreateDrawings()
	
		self.imgQ = ImageQt.ImageQt(self.completeMap)  # we need to hold reference to imgQ, or it will crash
		pixMap = QtGui.QPixmap.fromImage(self.imgQ)
		#pixMap = pixMap.scaled(100, 100, QtCore.Qt.KeepAspectRatio)
	
		#self.scene = QtGui.QGraphicsScene()
		self.scene = QScene(self)
		#self.scene.addPixmap( QtGui.QPixmap(ImageQt.ImageQt(self.completeMap)) )
		self.scene.addPixmap( pixMap )
		self.ui.graphicsView.setScene(self.scene)

	
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
		

	def openNewPointWindow(self):
		self.newPointWindow = NewPointDialog(self)
		self.newPointWindow.exec_()

	def addPoint(self, id, lat, lon, fillcolor=None):
		
		self.points.append([id, lat, lon, fillcolor])
	
	def deletePointByID(self, id):
		
		survivingPoints = []
		
		for point in self.points:
			if (point[0] != id):
				survivingPoints.append(point)

		self.points = survivingPoints
		


if __name__ == "__main__":
    app = QtGui.QApplication(sys.argv)
    mapper = Mapper()
    mapper.show()
    sys.exit(app.exec_())