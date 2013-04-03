import mapper, sys, sqlite3, time
from PySide import QtGui

app = QtGui.QApplication(sys.argv)
finestra = mapper.Mapper()

con = sqlite3.connect('nmeadata.sqlite')
con.row_factory = sqlite3.Row
cur = con.cursor()

#cur.execute('SELECT time, latitude, longitude FROM nmeadata WHERE time > 1326474000 AND time < 1326495540')
cur.execute('SELECT time, latitude, longitude FROM nmeadata ORDER BY time')

elements = cur.fetchall()
print len(elements)

sectionLength = 10000.0
sections = int(float(len(elements)) / sectionLength)

for section in range(sections+1):
	
	traccia = mapper.Track("Concordia %i"%section)

	for element in elements[int(sectionLength*(section)) : int(sectionLength*(section+1))]:
		
		if (element['time'] % 100 != 0): continue
		
		pointName = time.strftime('%d %b %y %H:%M:%S', time.localtime(element['time']))
		
		traccia.addPoint(mapper.Point(pointName, element['latitude'], element['longitude'], "red"))	

	finestra.addTrack(traccia)


finestra.show()

finestra.refresh()

sys.exit(app.exec_())