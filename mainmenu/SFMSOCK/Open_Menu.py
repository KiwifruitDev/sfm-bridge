# SFM SOCK: Send_Update.py
# This software is licensed under the MIT License.
# Copyright (c) 2021 KiwifruitDev

# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

# This is a rewrite of the old script code into a Qt tab menu.

import sfm
import vs
import vs.movieobjects
import socket
import os
import json
import sfmApp # built-in, ignore warnings
import time
from PySide import QtGui
from PySide import QtCore
from PySide import shiboken
from atexit import register
from ast import literal_eval

global SFMSOCK_VERSION
SFMSOCK_VERSION = "1.0.1"

# Elements that are useless and cause recursion errors.
recursive_elements = [
    "trackGroups",
    "scene",
    "positionChannel",
    "orientationChannel",
    "presetGroups",
    "rootControlGroup",
    "channel",
    "phonememap",
    "rightValueChannel", # TODO: Is it both camelCase and lowercase?
    "leftValueChannel", # TODO: Is it both camelCase and lowercase?
    "rightvaluechannel",
    "leftvaluechannel",
    #"globalFlexControllers",
    "flexnames",
    "flexWeights",
    "controls", # Yes, this is bad but you should be using gameModel.children instead.
    # Just useless stuff.
    "bookmarkSets",
    "activeMonitor",
    "aviFile",
    "displayScale",
    "mapname",
    "info",
    "operators",
    "bones", # Use gameModel.children instead.
    "log",
    "overrideParent", # Parents cause recursion errors.
]

# We're good to go.
# Parse an attribute, used for JSON parsing.
def ParseAttribute(attribute, parsed, parent, lastparent):
    # Prevent recursion.
    if attribute.GetName() in recursive_elements:
        return False
    elif attribute.GetTypeString() == "element":
        # globalFlexControllers has attributes with recursive "gameModel" attributes.
        # We need to avoid that.
        if lastparent is not None and lastparent.GetName() == "globalFlexControllers":
            return False
        # Recursively parse the element.
        if attribute.GetValue() != None:
            parsed[attribute.GetName()] = ParseElement(attribute.GetValue(), attribute)
        return True
    elif attribute.GetTypeString() == "color":
        parsed[attribute.GetName()] = {
            "r": attribute.GetValue().r(),
            "g": attribute.GetValue().g(),
            "b": attribute.GetValue().b(),
            "a": attribute.GetValue().a()
        }
        return True
    elif attribute.GetTypeString() == "vector2":
        parsed[attribute.GetName()] = {
            "x": attribute.GetValue().x,
            "y": attribute.GetValue().y
        }
        return True
    elif attribute.GetTypeString() == "vector3":
        parsed[attribute.GetName()] = {
            "x": attribute.GetValue().x,
            "y": attribute.GetValue().y,
            "z": attribute.GetValue().z
        }
        return True
    elif attribute.GetTypeString() == "vector4":
        parsed[attribute.GetName()] = {
            "x": attribute.GetValue().x,
            "y": attribute.GetValue().y,
            "z": attribute.GetValue().z,
            "w": attribute.GetValue().w
        }
        return True
    elif attribute.GetTypeString() == "qangle":
        parsed[attribute.GetName()] = {
            "x": attribute.GetValue().x,
            "y": attribute.GetValue().y,
            "z": attribute.GetValue().z
        }
        return True
    elif attribute.GetTypeString() == "quaternion":
        parsed[attribute.GetName()] = {
            "x": attribute.GetValue().x,
            "y": attribute.GetValue().y,
            "z": attribute.GetValue().z,
            "w": attribute.GetValue().w
        }
        return True
    # Arrays
    elif attribute.GetTypeString() == "element_array":
        if attribute.count() > 0:
            parsed[attribute.GetName()] = []
            if attribute.GetValue() != None:
                for i in range(attribute.count()):
                    # Recursively parse the element array.
                    if attribute.GetValue()[i-1] != None:
                        parsed[attribute.GetName()].append(ParseElement(attribute.GetValue()[i-1], attribute))
        return True
    elif attribute.GetTypeString() == "color_array" or attribute.GetTypeString() == "vector2_array" or attribute.GetTypeString() == "vector3_array" or attribute.GetTypeString() == "vector4_array" or attribute.GetTypeString() == "qangle_array" or attribute.GetTypeString() == "quaternion_array":
        if attribute.count() > 0:
            if attribute.GetValue() != None:
                parsed[attribute.GetName()] = []
                print(attribute.GetName(), parent.GetName(), lastparent.GetName())
                for i in range(attribute.count()):
                    if attribute.GetValue()[i-1] != None:
                        parsed[attribute.GetName()].append(ParseAttribute(attribute.GetValue()[i-1], parsed[attribute.GetName()], attribute, parent))
        return True
    elif attribute.GetTypeString() == "string_array" or attribute.GetTypeString() == "bool_array" or attribute.GetTypeString() == "int_array" or attribute.GetTypeString() == "float_array": 
        if attribute.count() > 0:
            if attribute.GetValue() != None:
                parsed[attribute.GetName()] = []
                for i in range(attribute.count()):
                    if attribute.GetValue()[i-1] != None:
                        parsed[attribute.GetName()].append(attribute.GetValue()[i-1])
        return True
    elif attribute.GetTypeString() == "string" or attribute.GetTypeString() == "bool" or attribute.GetTypeString() == "int" or attribute.GetTypeString() == "float":
        # should pass through as is
        parsed[attribute.GetName()] = attribute.GetValue()
        return True
    else:
        # Unsupported elements:
        # binary / binary_array
        # time / time_array
        # matrix / matrix_array
        # TODO: Implement these types.
        return False

def ParseElement(dag, parent):
    dag_parsed = {}
    dag_element = dag.FirstAttribute()
    ParseAttribute(dag_element, dag_parsed, dag, parent)
    for i in range(128):
        dag_element = dag_element.NextAttribute()
        if dag_element is None:
            break
        ParseAttribute(dag_element, dag_parsed, dag, parent)
    return dag_parsed

# This class is used for other scripts to interface with SFM SOCK.
# It should never be initialized outside of this script.
class SFMSOCK_API:
    def __init__(self):
        # We only want one instance of SFM SOCK running at a time.
        if "SFMSOCK" in globals():
            sfm.Msg("Something tried to create a new SFM SOCK instance, previous instance will be used.\n")
        else:
            sfm.Msg("SFM SOCK is starting...\n")
            globals()["SFMSOCK"] = self
        # Create a client for communication.
        self.client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        # Connect to the server, likely Garry's Mod.
        if "SFMSOCK_TAB_WINDOW" in globals():
            ipport = str(SFMSOCK_TAB_WINDOW.ip.text()).split(":", 1)
            ip = ipport[0] or "localhost"
            port = int(ipport[1]) or 9191
            self.client.connect((ip, port))
        else:
            self.client.connect((os.environ.get("SFMSOCK_TCP_IP") or "localhost", os.environ.get("SFMSOCK_TCP_PORT") or 9191))
        # Send a cute message to the server.
        #self.client.send(("Hello from SFM! I'm SFM SOCK version v" + SFMSOCK_VERSION + " running on SFM v" + sfmApp.Version() + ". My current project is " + sfmApp.GetMovie().GetValue("name") + " on map " + sfmApp.GetMovie().GetValue("mapname")).encode())
        # Close SFM SOCK when the script is closed.
        register(self.close)
        sfm.Msg("SFM SOCK version " + SFMSOCK_VERSION + " is now running.\n")
        self.frame("framedata", sfmApp.GetHeadTimeInFrames())
    def close(self):
        sfm.Msg("SFM SOCK is closing...\n")
        self.client.close()
        sfm.Msg("SFM SOCK has closed.\n")
        del globals()["SFMSOCK"]
    # Frame request
    def frame(self, type, startframe): # currently supported types by protocol: framedata, framecommit
        framedata = {}
        framedata["type"] = type
        framedata["version"] = SFMSOCK_VERSION
        framedata["project"] = sfmApp.GetMovie().GetValue("name")
        framedata["map"] = sfmApp.GetMovie().GetValue("mapname")
        framedata["from"] = "SFM SOCK"
        framedata["currentFrame"] = startframe
        framedata["frameRate"] = sfmApp.GetFramesPerSecond()
        # Parse elements into something we can send.
        if sfmApp.GetMovie() is not None:
            sfmApp.SetHeadTimeInFrames(startframe)
            # This gets the current clip at the playhead.
            curtime = vs.DmeTime_t(((1.0/sfmApp.GetFramesPerSecond())*startframe))
            # Parse it over.
            if sfmApp.GetMovie().FindOrCreateFilmTrack().FindFilmClipAtTime(curtime) is not None:
                framedata["filmClip"] = ParseElement(sfmApp.GetMovie().FindOrCreateFilmTrack().FindFilmClipAtTime(curtime), None)
        # Send framedata to server via json.
        self.client.send("!START!" + json.dumps(framedata).encode() + "!END!")


class SfmSockWindow(QtGui.QWidget):
    def __init__(self):
        super( SfmSockWindow, self ).__init__()
        self.initUI()
        
    def initUI(self):      
        # Server IP (string input)
        self.ip = QtGui.QLineEdit(self)
        self.ip.setText("localhost:9191")
        self.ip.setPlaceholderText("localhost:9191")
        self.ip.setToolTip("The IP address of a compatible websocket server.")

        # Buttons
        self.connectButton = QtGui.QPushButton("Connect", self)
        self.connectButton.clicked.connect(self.serverConnect)
        self.connectButton.setToolTip("Connect to the server, make sure to check the Script Editor to ensure the connection was successful.")
        self.disconnectButton = QtGui.QPushButton("Disconnect", self)
        self.disconnectButton.clicked.connect(self.serverDisconnect)
        self.disconnectButton.setToolTip("Disconnect from the server, make sure to check the Script Editor to ensure the disconnection was successful.")
        self.transmitButton = QtGui.QPushButton("Transmit", self)
        self.transmitButton.clicked.connect(self.serverTransmit)
        self.transmitButton.setToolTip("Transmit the current frame to the server, used for temporary changes.")
        self.commitButton = QtGui.QPushButton("Commit", self)
        self.commitButton.clicked.connect(self.serverCommit)
        self.commitButton.setToolTip("Commit/save the current frame to the server, used to save specific movie frames.")
        self.exportButton = QtGui.QPushButton("Export (!!!)", self)
        self.exportButton.clicked.connect(self.serverExport)
        self.exportButton.setToolTip("Export a movie between the start and end frames to the server.")

        # Start and end frames
        self.startFrame = QtGui.QSpinBox(self)
        self.startFrame.setRange(-2000000000, 2000000000)
        self.startFrame.setValue(0)
        self.startFrame.setToolTip("The frame to start exporting from.")
        self.startFrame.valueChanged[int].connect(self.startFrameChanged)
        self.startFrameButton = QtGui.QPushButton("Set Start Frame", self)
        self.startFrameButton.clicked.connect(self.setStartFrame)
        self.startFrameButton.setToolTip("Set the start frame to the current frame.")
        self.endFrame = QtGui.QSpinBox(self)
        self.endFrame.setRange(-2000000000, 2000000000)
        self.endFrame.setValue(0)
        self.endFrame.setToolTip("The frame to stop exporting at.")
        self.endFrame.valueChanged[int].connect(self.endFrameChanged)
        self.endFrameButton = QtGui.QPushButton("Set End Frame", self)
        self.endFrameButton.clicked.connect(self.setEndFrame)
        self.endFrameButton.setToolTip("Set the end frame to the current frame.")

        # Frame delay
        self.frameDelay = QtGui.QDoubleSpinBox(self)
        self.frameDelay.setRange(0, 2000000000)
        self.frameDelay.setValue(0.45)
        self.frameDelay.setToolTip("The delay between frame exports/live updates in seconds.")

        # Dag multiplier
        self.dagMultiplier = QtGui.QDoubleSpinBox(self)
        self.dagMultiplier.setRange(0, 2000000000)
        self.dagMultiplier.setValue(0.01)
        self.dagMultiplier.setToolTip("This value will be added to frame delay for each animation set in the current shot.")

        # Live update checkbox
        self.liveUpdate = QtGui.QCheckBox(self)
        self.liveUpdate.setChecked(False)
        self.liveUpdate.setToolTip("If checked, the script will constantly transmit the current frame to the server. Experimental and should not be used on low-end machines.")
        self.liveUpdate.stateChanged.connect(self.liveUpdateChanged)

        # Status "bar"
        self.status = QtGui.QLabel(self)

        # Layout
        self.layout = QtGui.QFormLayout()
        self.layout.addRow("Server IP:", self.ip)
        self.layout.addWidget(self.connectButton)
        self.layout.addWidget(self.disconnectButton)
        self.layout.addWidget(self.transmitButton)
        self.layout.addWidget(self.commitButton)
        self.layout.addWidget(self.exportButton)
        self.layout.addRow("Start Frame:", self.startFrame)
        self.layout.addWidget(self.startFrameButton)
        self.layout.addRow("End Frame:", self.endFrame)
        self.layout.addWidget(self.endFrameButton)
        self.layout.addRow("Frame Delay:", self.frameDelay)
        self.layout.addRow("Dag Multiplier:", self.dagMultiplier)
        self.layout.addRow("Live Update:", self.liveUpdate)
        self.layout.addRow("Status:", self.status)
        self.setLayout(self.layout)

        # First boot
        if not "SFMSOCK" in globals():
            self.status.setText("Not connected.")
            self.connectButton.setEnabled(True)
            self.transmitButton.setEnabled(False)
            self.disconnectButton.setEnabled(False)
            self.commitButton.setEnabled(False)
            self.exportButton.setEnabled(False)
        elif "SFMSOCK" in globals():
            self.status.setText("Connected.")
            self.connectButton.setEnabled(False)
            self.transmitButton.setEnabled(True)
            self.disconnectButton.setEnabled(True)
            self.commitButton.setEnabled(True)
            self.exportButton.setEnabled(True)
        else:
            self.status.setText("Unknown error.")

    def serverConnect(self):
        # Check to make sure that this script has not been run before.
        if "SFMSOCK" in globals():
            sfm.Msg("SFM SOCK is already running, this script can only be run once.\n")
        else:
            self.status.setText("Connected.")
            SFMSOCK_TAB_WINDOW.disconnectButton.setEnabled(True)
            SFMSOCK_TAB_WINDOW.transmitButton.setEnabled(True)
            SFMSOCK_TAB_WINDOW.connectButton.setEnabled(False)
            SFMSOCK_TAB_WINDOW.commitButton.setEnabled(True)
            SFMSOCK_TAB_WINDOW.exportButton.setEnabled(True)
            # Handle connections but don't block the main thread.
            if __name__ == '__main__':
                # Check for movie.
                if sfmApp.GetMovie() is None:
                    sfm.Msg("SFM SOCK can't run without a session.\n")
                else:
                    # Create a SFM SOCK API object.
                    global SFMSOCK
                    SFMSOCK = SFMSOCK_API()
            else:
                self.status.setText("Already connected.")
                # How did we get here?
                sfm.Msg("SFM SOCK is running in a different thread, exiting...\n")
    
    def serverDisconnect(self):
        # Make sure SFMSOCK exists.
        if "SFMSOCK" in globals():
            self.status.setText("Not connected.")
            SFMSOCK_TAB_WINDOW.connectButton.setEnabled(True)
            SFMSOCK_TAB_WINDOW.transmitButton.setEnabled(False)
            SFMSOCK_TAB_WINDOW.disconnectButton.setEnabled(False)
            SFMSOCK_TAB_WINDOW.commitButton.setEnabled(False)
            SFMSOCK_TAB_WINDOW.exportButton.setEnabled(False)
            # We're good to go.
            SFMSOCK.close()
        else:
            self.status.setText("Already disconnected.")
            sfm.Msg("SFM SOCK is not running, this script can not be run.\n")

    def serverTransmit(self):
        # Make sure SFMSOCK exists.
        if "SFMSOCK" in globals():
            frame = sfmApp.GetHeadTimeInFrames()
            self.status.setText("Transmitting frame " + str(frame) + ".")
            # We're good to go.
            SFMSOCK.frame("framedata", frame)
        else:
            self.status.setText("Unable to transmit.")
            sfm.Msg("SFM SOCK is not running, this script can not be run.\n")

    def serverCommit(self):
        # Make sure SFMSOCK exists.
        if "SFMSOCK" in globals():
            frame = sfmApp.GetHeadTimeInFrames()
            self.status.setText("Committing frame " + str(frame) + ".")
            # We're good to go.
            SFMSOCK.frame("framecommit", frame)
        else:
            self.status.setText("Unable to commit.")
            sfm.Msg("SFM SOCK is not running, this script can not be run.\n")

    def serverExport(self):
        # Make sure SFMSOCK exists.
        if "SFMSOCK" in globals():
            self.transmitButton.setEnabled(False)
            self.commitButton.setEnabled(False)
            self.exportButton.setEnabled(False)
            self.status.setText("Exporting...")
            # We're good to go.
            SFMSOCK = globals()["SFMSOCK"]
            for i in range(self.startFrame.value(), self.endFrame.value() + 1):
                if SFMSOCK is not None:
                    curtime = vs.DmeTime_t(((1.0/sfmApp.GetFramesPerSecond())*i))
                    animSetMultiplier = 0
                    if sfmApp.GetMovie() is not None:
                        if sfmApp.GetMovie().FindOrCreateFilmTrack().FindFilmClipAtTime(curtime) is not None:
                            clip = sfmApp.GetMovie().FindOrCreateFilmTrack().FindFilmClipAtTime(curtime)
                            # animation set count
                            for b in range(0, clip.animationSets.count()):
                                animSetMultiplier += self.dagMultiplier.value()
                    self.status.setText("Exporting Frame " + str(i) + ".")
                    sfmApp.SetHeadTimeInFrames(i)
                    time.sleep((self.frameDelay.value() + animSetMultiplier) / 3)
                    sfmApp.ProcessEvents()
                    time.sleep((self.frameDelay.value() + animSetMultiplier) / 3)
                    SFMSOCK.frame("framecommit", i)
                    time.sleep((self.frameDelay.value() + animSetMultiplier) / 3)
                else:
                    self.transmitButton.setEnabled(True)
                    self.commitButton.setEnabled(True)
                    self.exportButton.setEnabled(True)
                    self.status.setText("Export failed.")
                    sfm.Msg("SFM SOCK could not send a frame commit, stopping.\n")
                    break # if you disconnect, stop trying to send frames.
            self.transmitButton.setEnabled(True)
            self.commitButton.setEnabled(True)
            self.exportButton.setEnabled(True)
            self.status.setText("Export complete.")
        else:
            self.status.setText("Unable to export.")
            sfm.Msg("SFM SOCK is not running, this script can not be run.\n")

    def startFrameChanged(self, value):
        self.startFrame.setValue(value)

    def endFrameChanged(self, value):
        self.endFrame.setValue(value)

    def liveUpdateChanged(self, value):
        # Make sure SFMSOCK exists.
        if value:
            self.status.setText("Live update enabled.")
            while self.liveUpdate.isChecked():
                if "SFMSOCK" in globals():
                    startframe = sfmApp.GetHeadTimeInFrames()
                    SFMSOCK.frame("framedata", startframe)
                    sfmApp.ProcessEvents()
                    curtime = vs.DmeTime_t(((1.0/sfmApp.GetFramesPerSecond())*startframe))
                    animSetMultiplier = 0
                    if sfmApp.GetMovie() is not None:
                        if sfmApp.GetMovie().FindOrCreateFilmTrack().FindFilmClipAtTime(curtime) is not None:
                            clip = sfmApp.GetMovie().FindOrCreateFilmTrack().FindFilmClipAtTime(curtime)
                            # animation set count
                            for i in range(0, clip.animationSets.count()):
                                animSetMultiplier += self.dagMultiplier.value()
                    time.sleep(self.frameDelay.value() + animSetMultiplier)
        else:
            self.status.setText("Live update disabled.")

    def setStartFrame(self):
        self.startFrame.setValue(sfmApp.GetHeadTimeInFrames())

    def setEndFrame(self):
        self.endFrame.setValue(sfmApp.GetHeadTimeInFrames())

global SFMSOCK_TAB_WINDOW
SFMSOCK_TAB_WINDOW = SfmSockWindow()

sfmApp.RegisterTabWindow("WindowSFMSOCK", "SFM SOCK", shiboken.getCppPointer( SFMSOCK_TAB_WINDOW )[0])
sfmApp.ShowTabWindow("WindowSFMSOCK")
