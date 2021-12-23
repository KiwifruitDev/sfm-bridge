# SFM SOCK: Start_Server.py
# This software is licensed under the MIT License.
# Copyright (c) 2021 KiwifruitDev

# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

import sfm
# Check to make sure that this script has not been run before.
if "SFMSOCK" in globals():
    sfm.Msg("SFM SOCK is already running, this script can only be run once.\n")
else:
    # We're good to go.
    global SFMSOCK_VERSION
    SFMSOCK_VERSION = "1.0.0"

    import vs
    import vs.movieobjects
    import socket
    import os
    import json
    import sfmApp # built-in, ignore warnings
    from atexit import register
    from threading import Thread

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
    ]

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
                for i in range(attribute.count()):
                    # Recursively parse the element array.
                    if attribute.GetValue()[i-1] != None:
                        parsed[attribute.GetName()].append(ParseElement(attribute.GetValue()[i-1], attribute))
            return True
        elif attribute.GetTypeString() == "color_array" or attribute.GetTypeString() == "vector2_array" or attribute.GetTypeString() == "vector3_array" or attribute.GetTypeString() == "vector4_array" or attribute.GetTypeString() == "qangle_array" or attribute.GetTypeString() == "quaternion_array":
            if attribute.count() > 0:
                parsed[attribute.GetName()] = []
                for i in range(attribute.count()):
                    parsed[attribute.GetName()].append(ParseAttribute(attribute.GetValue()[i-1], parsed[attribute.GetName()], attribute))
            return True
        elif attribute.GetTypeString() == "string_array" or attribute.GetTypeString() == "bool_array" or attribute.GetTypeString() == "int_array" or attribute.GetTypeString() == "float_array": 
            if attribute.count() > 0:
                parsed[attribute.GetName()] = []
                for i in range(attribute.count()):
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
            self.client.connect((os.environ.get("SFMSOCK_TCP_IP") or "localhost", os.environ.get("SFMSOCK_TCP_PORT") or 9191))
            # Send a cute message to the server.
            #self.client.send(("Hello from SFM! I'm SFM SOCK version v" + SFMSOCK_VERSION + " running on SFM v" + sfmApp.Version() + ". My current project is " + sfmApp.GetMovie().GetValue("name") + " on map " + sfmApp.GetMovie().GetValue("mapname")).encode())
            # Close SFM SOCK when the script is closed.
            register(self.close)
            sfm.Msg("SFM SOCK version " + SFMSOCK_VERSION + " is now running.\n")
            self.frame()
        def close(self):
            sfm.Msg("SFM SOCK is closing...\n")
            self.client.close()
            sfm.Msg("SFM SOCK has closed.\n")
            del globals()["SFMSOCK"]
        # Frame request
        def frame(self):
            framedata = {}
            framedata["type"] = "framedata"
            framedata["version"] = SFMSOCK_VERSION
            framedata["project"] = sfmApp.GetMovie().GetValue("name")
            framedata["map"] = sfmApp.GetMovie().GetValue("mapname")
            framedata["from"] = "SFM SOCK"
            # Parse elements into something we can send.
            if sfmApp.GetMovie() is not None:
                # This gets the current clip at the playhead.
                curtime = vs.DmeTime_t(((1.0/sfmApp.GetFramesPerSecond())*sfmApp.GetHeadTimeInFrames()))
                # Parse it over.
                if sfmApp.GetMovie().FindOrCreateFilmTrack().FindFilmClipAtTime(curtime) is not None:
                    framedata["filmClip"] = ParseElement(sfmApp.GetMovie().FindOrCreateFilmTrack().FindFilmClipAtTime(curtime), None)
            # Send framedata to server via json.
            self.client.send(json.dumps(framedata).encode())

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
        # How did we get here?
        sfm.Msg("SFM SOCK is running in a different thread, exiting...\n")
