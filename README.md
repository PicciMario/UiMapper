UiMapper (temporary name)
=========================

Description
-----------
UiMapper (while waiting for a better name :-) ) is a Python class to create a complete UI for browsing a 
geographical map, built runtime with OpenStreetMap.org tiles and able to contain both points and tracks.

The utility can be used as a standalone program or be called by external python scripts, for example to show
a geographic location or a track

Requirements
------------
If you type "python" on the command line (being it windows, linux or mac) and it DOESN'T return an error,
you can skip the following two steps:

- Python 2.7 (for Windows: http://www.python.org/download/)
- add Python to your Windows PATH

Then:

- PySide (for Windows: http://developer.qt.nokia.com/wiki/PySideBinariesWindows)

Other requirements:

- The class needs a tmp/ directory to store cached tiles.

Example
-------
To start the basic UI, just type:
	
	python mapper.py

If you want to try something more interesting, you could try write and test this little sample script:

	import mapper, sys
	from PySide import QtGui

	app = QtGui.QApplication(sys.argv)
	finestra = mapper.Mapper()

	traccia = mapper.Track("sample track")
	traccia.addPoint(mapper.Point("sample point 1", 42, 10, "red"))
	traccia.addPoint(mapper.Point("sample point 2", 42.001, 10, "red"))
	finestra.addTrack(traccia)

	finestra.show()
	finestra.refresh()

	sys.exit(app.exec_())