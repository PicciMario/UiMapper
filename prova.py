import mapper, sys, sqlite3, time
from PySide import QtGui

app = QtGui.QApplication(sys.argv)
finestra = mapper.Mapper()

con = sqlite3.connect('nmeadata.sqlite')
con.row_factory = sqlite3.Row
cur = con.cursor()

cur.execute('SELECT time, latitude, longitude FROM nmeadata WHERE time > 1326474000 AND time < 1326495540')

traccia = mapper.Track("Concordia")

for element in cur.fetchall():
	
	if (element['time'] % 5 != 0): continue
	
	pointName = time.strftime('%H:%M:%S', time.localtime(element['time']))
	
	traccia.addPoint(mapper.Point(pointName, element['latitude'], element['longitude'], "red"))	

finestra.addTrack(traccia)


finestra.show()

finestra.refresh()

sys.exit(app.exec_())