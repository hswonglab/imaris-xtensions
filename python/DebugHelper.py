"""
Helper functions for debugging Imaris XTensions
"""

import sys

sys.path.append("C:\\Program Files\\Bitplane\\Imaris 10.2.0\\XT\\python3")

import ImarisLib

def GetServer():
    vImarisLib = ImarisLib.ImarisLib()
    vServer = vImarisLib.GetServer()
    return vServer;

def GetObjectId():
    vServer = GetServer()
    vNumberOfObjects = vServer.GetNumberOfObjects()
    for vIndex in range(vNumberOfObjects):
        vObjectId = vServer.GetObjectID(vIndex)
        return vObjectId; # work with the ID (return first one)
    return -1 # invalid id

def GetImaris():
  vServer = GetServer()
  vObjectId = GetObjectId()
  vObject = vServer.GetObject(vObjectId)
  vImarisApplication = Imaris.IApplicationPrx.checkedCast(vObject)
  return vImarisApplication